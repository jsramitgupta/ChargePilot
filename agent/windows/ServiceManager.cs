using System.Diagnostics;
using System.Security.Principal;
using System.ServiceProcess;

namespace ChargePilotAgent;

internal static class ServiceManager
{
    public const string ServiceName = "ChargePilotAgent";
    public const string DisplayName = "ChargePilot Telemetry Agent";

    public static string InstalledExecutablePath => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
        "ChargePilot",
        "Agent",
        "ChargePilotAgent.exe");

    public static bool IsAdministrator()
    {
        using var identity = WindowsIdentity.GetCurrent();
        return new WindowsPrincipal(identity).IsInRole(WindowsBuiltInRole.Administrator);
    }

    public static string GetStatus()
    {
        try
        {
            using var service = new ServiceController(ServiceName);
            return service.Status.ToString();
        }
        catch (InvalidOperationException)
        {
            return "Not installed";
        }
    }

    public static void InstallOrUpdate(string sourceExecutable)
    {
        RequireAdministrator();
        EnsureEventSource();
        var existing = FindService();
        if (existing is not null)
        {
            StopAndDelete(existing);
        }

        var directory = Path.GetDirectoryName(InstalledExecutablePath)
            ?? throw new InvalidOperationException("Unable to determine the installation directory.");
        Directory.CreateDirectory(directory);
        if (!PathsEqual(sourceExecutable, InstalledExecutablePath))
        {
            var stagingPath = InstalledExecutablePath + "." + Guid.NewGuid().ToString("N") + ".tmp";
            try
            {
                File.Copy(sourceExecutable, stagingPath, overwrite: true);
                File.Move(stagingPath, InstalledExecutablePath, overwrite: true);
            }
            finally
            {
                if (File.Exists(stagingPath))
                {
                    File.Delete(stagingPath);
                }
            }
        }

        RunSc("create", ServiceName, "binPath=", $"\"{InstalledExecutablePath}\" service", "start=", "auto", "DisplayName=", DisplayName);
        RunSc("description", ServiceName, "Reports enrolled Windows device battery telemetry to ChargePilot.");

        try
        {
            RemoveLegacyScheduledTask();
            RunSc("start", ServiceName);
        }
        catch
        {
            DeleteServiceIfPresent();
            throw;
        }

    }

    public static void UpdateInstalledAgent(string sourceExecutable)
    {
        RequireAdministrator();
        if (!File.Exists(sourceExecutable) || PathsEqual(sourceExecutable, InstalledExecutablePath))
        {
            throw new InvalidOperationException("The downloaded agent executable is missing or is already installed.");
        }

        using var service = RequireService();
        var wasRunning = service.Status == ServiceControllerStatus.Running;
        if (service.Status is not ServiceControllerStatus.Running and not ServiceControllerStatus.Stopped)
        {
            throw new InvalidOperationException(
                $"The ChargePilot Agent service is {service.Status}; wait until it is running or stopped before updating.");
        }

        var directory = Path.GetDirectoryName(InstalledExecutablePath)
            ?? throw new InvalidOperationException("Unable to determine the installation directory.");
        var stagingPath = InstalledExecutablePath + "." + Guid.NewGuid().ToString("N") + ".tmp";
        var backupPath = InstalledExecutablePath + "." + Guid.NewGuid().ToString("N") + ".backup";
        var originalMoved = false;
        try
        {
            if (wasRunning)
            {
                Stop();
            }

            Directory.CreateDirectory(directory);
            File.Copy(sourceExecutable, stagingPath, overwrite: false);
            File.Move(InstalledExecutablePath, backupPath);
            originalMoved = true;
            File.Move(stagingPath, InstalledExecutablePath);
            if (wasRunning)
            {
                Start();
            }
        }
        catch (Exception updateException)
        {
            try
            {
                EnsureStopped();

                if (originalMoved)
                {
                    if (File.Exists(InstalledExecutablePath))
                    {
                        File.Delete(InstalledExecutablePath);
                    }

                    File.Move(backupPath, InstalledExecutablePath);
                }

                if (wasRunning)
                {
                    Start();
                }
            }
            catch (Exception rollbackException)
            {
                throw new AggregateException(
                    "The agent update failed and the previous executable could not be fully restored.",
                    updateException,
                    rollbackException);
            }

            throw new InvalidOperationException(
                "The agent update failed. The previous version was restored.",
                updateException);
        }
        finally
        {
            if (File.Exists(stagingPath))
            {
                File.Delete(stagingPath);
            }
        }

        if (File.Exists(backupPath))
        {
            File.Delete(backupPath);
        }
    }

    public static void Start()
    {
        RequireAdministrator();
        using var service = RequireService();
        if (service.Status == ServiceControllerStatus.Running)
        {
            return;
        }

        service.Start();
        service.WaitForStatus(ServiceControllerStatus.Running, TimeSpan.FromSeconds(30));
    }

    public static void Stop()
    {
        RequireAdministrator();
        using var service = FindService();
        if (service is null || service.Status == ServiceControllerStatus.Stopped)
        {
            return;
        }

        service.Stop();
        service.WaitForStatus(ServiceControllerStatus.Stopped, TimeSpan.FromSeconds(30));
    }

    public static void Uninstall(bool purgeConfiguration)
    {
        RequireAdministrator();
        var service = FindService();
        if (service is not null)
        {
            StopAndDelete(service);
        }

        RemoveLegacyScheduledTask();
        if (purgeConfiguration)
        {
            new ConfigurationStore().Delete();
        }
    }

    private static ServiceController RequireService() =>
        FindService() ?? throw new InvalidOperationException("The ChargePilot Agent service is not installed.");

    private static ServiceController? FindService()
    {
        foreach (var service in ServiceController.GetServices())
        {
            if (service.ServiceName.Equals(ServiceName, StringComparison.OrdinalIgnoreCase))
            {
                return service;
            }

            service.Dispose();
        }

        return null;
    }

    private static void StopAndDelete(ServiceController service)
    {
        using (service)
        {
            if (service.Status is not ServiceControllerStatus.Stopped and not ServiceControllerStatus.StopPending)
            {
                service.Stop();
            }

            service.WaitForStatus(ServiceControllerStatus.Stopped, TimeSpan.FromSeconds(30));
        }

        RunSc("delete", ServiceName);
        WaitForServiceRemoval();
    }

    private static void EnsureStopped()
    {
        using var service = RequireService();
        var deadline = DateTime.UtcNow.AddSeconds(30);
        service.Refresh();
        while (service.Status is ServiceControllerStatus.StartPending or ServiceControllerStatus.StopPending)
        {
            if (DateTime.UtcNow >= deadline)
            {
                throw new System.TimeoutException("The ChargePilot Agent service did not finish its transition during rollback.");
            }

            Thread.Sleep(250);
            service.Refresh();
        }

        if (service.Status != ServiceControllerStatus.Stopped)
        {
            service.Stop();
            service.WaitForStatus(ServiceControllerStatus.Stopped, deadline - DateTime.UtcNow);
        }
    }

    private static void DeleteServiceIfPresent()
    {
        var service = FindService();
        if (service is not null)
        {
            StopAndDelete(service);
        }
    }

    private static void WaitForServiceRemoval()
    {
        var timeout = DateTime.UtcNow.AddSeconds(15);
        while (DateTime.UtcNow < timeout)
        {
            using var service = FindService();
            if (service is null)
            {
                return;
            }

            Thread.Sleep(500);
        }

        throw new System.TimeoutException("Windows has not removed the previous ChargePilot Agent service yet.");
    }

    private static void RemoveLegacyScheduledTask()
    {
        using var query = StartProcess("schtasks.exe", "/query", "/tn", "ChargePilotBatteryAgent");
        query.WaitForExit();
        if (query.ExitCode != 0)
        {
            return;
        }

        using var end = StartProcess("schtasks.exe", "/end", "/tn", "ChargePilotBatteryAgent");
        end.WaitForExit();
        using var delete = StartProcess("schtasks.exe", "/delete", "/tn", "ChargePilotBatteryAgent", "/f");
        delete.WaitForExit();
        if (delete.ExitCode != 0)
        {
            throw new InvalidOperationException(
                "The Windows service is installed, but the old scheduled task could not be removed. Remove the ChargePilotBatteryAgent task in Task Scheduler.");
        }
    }

    private static void EnsureEventSource()
    {
        if (!System.Diagnostics.EventLog.SourceExists(DisplayName))
        {
            System.Diagnostics.EventLog.CreateEventSource(DisplayName, "Application");
        }
    }

    private static void RunSc(params string[] arguments)
    {
        using var process = StartProcess("sc.exe", arguments);
        process.WaitForExit();
        if (process.ExitCode != 0)
        {
            throw new InvalidOperationException(
                $"Windows service command failed ({string.Join(' ', arguments)}), exit code {process.ExitCode}.");
        }
    }

    private static Process StartProcess(string fileName, params string[] arguments)
    {
        var process = new Process
        {
            StartInfo = new ProcessStartInfo
            {
                FileName = fileName,
                UseShellExecute = false,
                CreateNoWindow = true,
            },
        };
        foreach (var argument in arguments)
        {
            process.StartInfo.ArgumentList.Add(argument);
        }

        process.Start();
        return process;
    }

    private static void RequireAdministrator()
    {
        if (!IsAdministrator())
        {
            throw new UnauthorizedAccessException(
                "Run ChargePilot Agent as Administrator to install, configure, or manage its Windows service.");
        }
    }

    private static bool PathsEqual(string left, string right) =>
        string.Equals(
            Path.GetFullPath(left).TrimEnd(Path.DirectorySeparatorChar),
            Path.GetFullPath(right).TrimEnd(Path.DirectorySeparatorChar),
            StringComparison.OrdinalIgnoreCase);
}
