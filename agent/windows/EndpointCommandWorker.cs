using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
using ChargePilotAgent.Core;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace ChargePilotAgent;

internal sealed class WindowsShutdownScheduler(
    ILogger<WindowsShutdownScheduler> logger) : IShutdownScheduler
{
    private const uint PlannedApplicationMaintenanceReason = 0x80040001;
    private const uint TokenAdjustPrivileges = 0x0020;
    private const uint TokenQuery = 0x0008;
    private const uint SePrivilegeEnabled = 0x0002;
    private const int ErrorNotAllAssigned = 1300;

    [StructLayout(LayoutKind.Sequential)]
    private struct Luid
    {
        public uint LowPart;
        public int HighPart;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct LuidAndAttributes
    {
        public Luid Luid;
        public uint Attributes;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct TokenPrivileges
    {
        public uint PrivilegeCount;
        public LuidAndAttributes Privileges;
    }

    [DllImport("kernel32.dll")]
    private static extern IntPtr GetCurrentProcess();

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool OpenProcessToken(
        IntPtr processHandle,
        uint desiredAccess,
        out SafeAccessTokenHandle tokenHandle);

    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool LookupPrivilegeValue(
        string? systemName,
        string name,
        out Luid luid);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool AdjustTokenPrivileges(
        SafeAccessTokenHandle tokenHandle,
        [MarshalAs(UnmanagedType.Bool)] bool disableAllPrivileges,
        ref TokenPrivileges newState,
        uint bufferLength,
        out TokenPrivileges previousState,
        out uint returnLength);

    [DllImport(
        "advapi32.dll",
        CharSet = CharSet.Unicode,
        EntryPoint = "InitiateSystemShutdownExW",
        SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool InitiateSystemShutdownEx(
        string? machineName,
        string message,
        uint timeoutSeconds,
        [MarshalAs(UnmanagedType.Bool)] bool forceApplicationsClosed,
        [MarshalAs(UnmanagedType.Bool)] bool rebootAfterShutdown,
        uint reason);

    public Task ScheduleAsync(int gracePeriodSeconds, CancellationToken cancellationToken)
    {
        if (gracePeriodSeconds is < 30 or > 120)
        {
            throw new ArgumentOutOfRangeException(nameof(gracePeriodSeconds));
        }
        cancellationToken.ThrowIfCancellationRequested();
        if (!OpenProcessToken(
                GetCurrentProcess(),
                TokenAdjustPrivileges | TokenQuery,
                out var tokenHandle))
        {
            throw new Win32Exception(Marshal.GetLastWin32Error());
        }
        using (tokenHandle)
        {
            if (!LookupPrivilegeValue(null, "SeShutdownPrivilege", out var shutdownPrivilege))
            {
                throw new Win32Exception(Marshal.GetLastWin32Error());
            }

            var enabledPrivilege = new TokenPrivileges
            {
                PrivilegeCount = 1,
                Privileges = new LuidAndAttributes
                {
                    Luid = shutdownPrivilege,
                    Attributes = SePrivilegeEnabled,
                },
            };
            if (!AdjustTokenPrivileges(
                    tokenHandle,
                    disableAllPrivileges: false,
                    ref enabledPrivilege,
                    (uint)Marshal.SizeOf<TokenPrivileges>(),
                    out var previousPrivileges,
                    out _))
            {
                throw new Win32Exception(Marshal.GetLastWin32Error());
            }
            var enableError = Marshal.GetLastWin32Error();
            if (enableError == ErrorNotAllAssigned)
            {
                throw new Win32Exception(
                    enableError,
                    "The agent account does not have the Windows shutdown privilege.");
            }

            try
            {
                if (!InitiateSystemShutdownEx(
                        null,
                        "ChargePilot battery automation requests shutdown. Save your work. Run shutdown /a to cancel.",
                        (uint)gracePeriodSeconds,
                        forceApplicationsClosed: false,
                        rebootAfterShutdown: false,
                        PlannedApplicationMaintenanceReason))
                {
                    throw new Win32Exception(Marshal.GetLastWin32Error());
                }
            }
            finally
            {
                if (!AdjustTokenPrivileges(
                        tokenHandle,
                        disableAllPrivileges: false,
                        ref previousPrivileges,
                        (uint)Marshal.SizeOf<TokenPrivileges>(),
                        out _,
                        out _))
                {
                    logger.LogWarning(
                        new Win32Exception(Marshal.GetLastWin32Error()),
                        "Could not restore the Windows shutdown privilege state.");
                }
            }
        }
        return Task.CompletedTask;
    }
}

internal sealed class EndpointCommandWorker(
    ConfigurationStore configurationStore,
    ChargePilotApiClient apiClient,
    ShutdownCommandHandler commandHandler,
    ILogger<EndpointCommandWorker> logger) : BackgroundService
{
    private static readonly TimeSpan PollInterval = TimeSpan.FromSeconds(15);

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                var options = configurationStore.Load();
                if (options is not null)
                {
                    await ProcessNextCommandAsync(options, stoppingToken);
                }
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception exception)
            {
                logger.LogError(exception, "Endpoint shutdown command check failed.");
            }

            try
            {
                await Task.Delay(PollInterval, stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
        }
    }

    private async Task ProcessNextCommandAsync(
        AgentOptions options,
        CancellationToken cancellationToken)
    {
        var command = await apiClient.ClaimShutdownCommandAsync(options, cancellationToken);
        if (command is null)
        {
            return;
        }
        var priorState = configurationStore.GetShutdownCommandState(command.Id);
        if (priorState is not null)
        {
            await apiClient.AcknowledgeShutdownCommandAsync(
                options,
                command.Id,
                new ShutdownAcknowledgement(
                    priorState == "scheduled" ? "scheduled" : "failed",
                    priorState == "in_progress"
                        ? "The agent stopped while processing this shutdown request."
                        : priorState == "failed"
                            ? "Windows did not accept the shutdown request."
                            : null),
                cancellationToken);
            return;
        }
        if (command.ExpiresAt <= DateTimeOffset.UtcNow)
        {
            await apiClient.AcknowledgeShutdownCommandAsync(
                options,
                command.Id,
                new ShutdownAcknowledgement("failed", "The shutdown request expired before execution."),
                cancellationToken);
            return;
        }

        try
        {
            configurationStore.SaveShutdownCommandState(command.Id, "in_progress");
            await commandHandler.HandleAsync(command, cancellationToken);
            configurationStore.SaveShutdownCommandState(command.Id, "scheduled");
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception exception)
        {
            configurationStore.SaveShutdownCommandState(command.Id, "failed");
            await apiClient.AcknowledgeShutdownCommandAsync(
                options,
                command.Id,
                new ShutdownAcknowledgement("failed", "Windows did not accept the shutdown request."),
                cancellationToken);
            logger.LogError(exception, "Windows rejected a fixed shutdown request.");
            return;
        }
        await apiClient.AcknowledgeShutdownCommandAsync(
            options,
            command.Id,
            new ShutdownAcknowledgement("scheduled"),
            cancellationToken);
        logger.LogWarning(
            "A fixed shutdown request was scheduled for endpoint {EndpointId} with a {GracePeriodSeconds}-second cancellation window.",
            options.EndpointId,
            command.GracePeriodSeconds);
    }
}
