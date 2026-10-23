using System.Runtime.InteropServices;
using System.Text;
using ChargePilotAgent.Core;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace ChargePilotAgent;

internal static class AgentBuildInfo
{
    public static string Version { get; } =
        typeof(AgentBuildInfo).Assembly.GetName().Version?.ToString(3) ?? "0.1.2";
}

internal static class Program
{
    private const int AttachParentConsole = -1;
    private const string ServerUrl = "https://api-chargepilot.endusercompute.in";

    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            var command = args.Length == 0 ? "ui" : args[0].ToLowerInvariant();
            var commandArguments = args.Skip(args.Length == 0 ? 0 : 1).ToArray();
            return command switch
            {
                "service" => RunServiceAsync().GetAwaiter().GetResult(),
                "ui" => RunUi(commandArguments),
                "install" => RunInteractiveConfiguration(commandArguments, allowExisting: true),
                "configure" => RunInteractiveConfiguration(commandArguments, allowExisting: true),
                "status" => RunStatus(),
                "start" => RunServiceControl(ServiceManager.Start),
                "stop" => RunServiceControl(ServiceManager.Stop),
                "uninstall" => RunUninstall(commandArguments),
                "update" => RunUpdate(commandArguments),
                "deregister" => RunDeregisterAsync().GetAwaiter().GetResult(),
                "send-once" => RunSendOnceAsync().GetAwaiter().GetResult(),
                "help" or "--help" or "-h" => ShowHelp(),
                _ => throw new ArgumentException($"Unknown command '{command}'. Run ChargePilotAgent.exe help for available commands."),
            };
        }
        catch (Exception exception)
        {
            AttachConsoleIfAvailable();
            if (args.FirstOrDefault()?.Equals("update", StringComparison.OrdinalIgnoreCase) == true)
            {
                MessageBox.Show(
                    exception.Message,
                    "ChargePilot Agent update failed",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
            else
            {
                Console.Error.WriteLine(exception.Message);
            }
            return 1;
        }
    }

    private static int RunUi(string[] arguments)
    {
        var values = ParseOptions(arguments, "--agent-version");
        AttachConsoleIfAvailable();
        ApplicationConfiguration.Initialize();
        Application.Run(new SetupForm(
            string.IsNullOrWhiteSpace(values.GetValueOrDefault("--agent-version"))
                ? AgentBuildInfo.Version
                : values["--agent-version"]));
        return 0;
    }

    private static int RunInteractiveConfiguration(string[] arguments, bool allowExisting)
    {
        AttachConsoleIfAvailable();
        var values = ParseOptions(
            arguments,
            "--class",
            "--interval-minutes");
        if (!ServiceManager.IsAdministrator())
        {
            throw new UnauthorizedAccessException(
                "Open PowerShell with Run as administrator before using the install or configure commands.");
        }

        var store = new ConfigurationStore();
        var previous = store.Load() ?? store.ImportLegacyUserConfiguration();
        if (!allowExisting)
        {
            previous = null;
        }

        var deviceName = Environment.MachineName;
        var deviceClass = values.GetValueOrDefault("--class") ?? PromptChoice(
            "Device class",
            previous?.DeviceClass ?? "laptop",
            "laptop",
            "desktop");
        var interval = ParseInterval(values.GetValueOrDefault("--interval-minutes"), previous?.IntervalMinutes ?? 5);
        Console.Write("Enrollment token (leave blank to keep the current enrollment): ");
        var enrollmentToken = ReadSecret();
        var serverUri = new Uri(ServerUrl);

        AgentOptions options;
        if (!string.IsNullOrEmpty(enrollmentToken))
        {
            var installationId = Guid.NewGuid();
            using var httpClient = new HttpClient { Timeout = TimeSpan.FromSeconds(30) };
            var api = new ChargePilotApiClient(httpClient);
            var enrollment = api.EnrollAsync(
                    serverUri,
                    enrollmentToken,
                    installationId,
                    deviceName,
                    deviceClass)
                .GetAwaiter()
                .GetResult();
            options = AgentOptions.Create(
                serverUri.ToString(),
                enrollment.Credential,
                enrollment.EndpointId,
                installationId,
                deviceName,
                deviceClass,
                AgentBuildInfo.Version,
                interval);
        }
        else
        {
            if (previous is null)
            {
                throw new InvalidOperationException("Enter an enrollment token to connect this device.");
            }

            if (previous.ServerUri != serverUri)
            {
                throw new InvalidOperationException(
                    "The saved enrollment uses a different server. Enter a token to connect to this ChargePilot server.");
            }

            options = AgentOptions.Create(
                serverUri.ToString(),
                previous.Credential,
                previous.EndpointId,
                previous.InstallationId,
                deviceName,
                deviceClass,
                AgentBuildInfo.Version,
                interval);
        }

        store.Save(options);
        ServiceManager.InstallOrUpdate(Environment.ProcessPath
            ?? throw new InvalidOperationException("Unable to locate the ChargePilot Agent executable."));
        Console.WriteLine($"ChargePilot Agent service installed and started for '{options.DeviceName}'.");
        return 0;
    }

    private static int RunStatus()
    {
        AttachConsoleIfAvailable();
        Console.WriteLine($"ChargePilot Agent service: {ServiceManager.GetStatus()}");
        var options = new ConfigurationStore().Load();
        Console.WriteLine(options is null
            ? "Device configuration: not configured"
            : $"Device configuration: {options.DeviceName} ({options.ServerUri})");
        return 0;
    }

    private static int RunServiceControl(Action action)
    {
        AttachConsoleIfAvailable();
        action();
        Console.WriteLine($"ChargePilot Agent service: {ServiceManager.GetStatus()}");
        return 0;
    }

    private static int RunUninstall(string[] arguments)
    {
        AttachConsoleIfAvailable();
        var values = ParseOptions(arguments, "--purge-config");
        var purgeConfiguration = values.ContainsKey("--purge-config");
        ServiceManager.Uninstall(purgeConfiguration);
        Console.WriteLine(purgeConfiguration
            ? "ChargePilot Agent service removed. Local configuration and credentials were deleted."
            : "ChargePilot Agent service removed. Local configuration is retained; use --purge-config to delete it.");
        return 0;
    }

    private static int RunUpdate(string[] arguments)
    {
        AttachConsoleIfAvailable();
        var values = ParseOptions(arguments, "--wait-for-process");
        if (!ServiceManager.IsAdministrator())
        {
            throw new UnauthorizedAccessException("Updating the Windows agent requires an elevated administrator process.");
        }

        if (values.TryGetValue("--wait-for-process", out var processIdText))
        {
            if (!int.TryParse(processIdText, out var processId) || processId <= 0)
            {
                throw new ArgumentException("The updater received an invalid parent process ID.");
            }

            try
            {
                using var parent = System.Diagnostics.Process.GetProcessById(processId);
                if (!parent.WaitForExit(TimeSpan.FromMinutes(2)))
                {
                    throw new TimeoutException("The setup window did not close, so the update was cancelled.");
                }
            }
            catch (ArgumentException)
            {
                // The setup window may already have exited.
            }
        }

        _ = new ConfigurationStore().Load()
            ?? throw new InvalidOperationException("The Windows agent has no saved enrollment to preserve.");
        if (ServiceManager.GetStatus() == "Not installed")
        {
            throw new InvalidOperationException("The Windows agent service is not installed.");
        }

        ServiceManager.UpdateInstalledAgent(Environment.ProcessPath
            ?? throw new InvalidOperationException("Unable to locate the downloaded agent executable."));
        System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
        {
            FileName = ServiceManager.InstalledExecutablePath,
            UseShellExecute = false,
            ArgumentList = { "ui" },
        });
        return 0;
    }

    private static async Task<int> RunDeregisterAsync()
    {
        AttachConsoleIfAvailable();
        if (!ServiceManager.IsAdministrator())
        {
            throw new UnauthorizedAccessException("Deregistering the Windows service requires an elevated administrator terminal.");
        }

        var store = new ConfigurationStore();
        var options = store.Load()
            ?? throw new InvalidOperationException("The Windows agent has no saved enrollment.");
        var serviceWasRunning = ServiceManager.GetStatus() == "Running";
        if (serviceWasRunning)
        {
            ServiceManager.Stop();
        }

        var credentialRevoked = false;
        try
        {
            using var httpClient = new HttpClient { Timeout = TimeSpan.FromSeconds(30) };
            await new ChargePilotApiClient(httpClient).DeregisterAsync(options.ServerUri, options.Credential);
            credentialRevoked = true;
            store.Delete();
        }
        catch
        {
            if (serviceWasRunning && !credentialRevoked)
            {
                ServiceManager.Start();
            }
            throw;
        }

        Console.WriteLine("Device deregistered. Enter a new enrollment token in the setup UI to connect it again.");
        return 0;
    }

    private static async Task<int> RunSendOnceAsync()
    {
        AttachConsoleIfAvailable();
        var store = new ConfigurationStore();
        var options = store.Load()
            ?? throw new InvalidOperationException("The Windows agent has not been configured.");
        using var httpClient = new HttpClient { Timeout = TimeSpan.FromSeconds(30) };
        var api = new ChargePilotApiClient(httpClient);
        var reading = new WindowsTelemetryReader().Read(options.DeviceName);
        await api.SendTelemetryAsync(options, reading);
        Console.WriteLine($"Telemetry accepted for '{options.DeviceName}' at {reading.Timestamp:O}.");
        return 0;
    }

    private static async Task<int> RunServiceAsync()
    {
        var builder = Host.CreateApplicationBuilder();
        builder.Services.AddWindowsService(options => options.ServiceName = ServiceManager.DisplayName);
        builder.Logging.ClearProviders();
        builder.Logging.AddEventLog(options => options.SourceName = ServiceManager.DisplayName);
        builder.Services.AddSingleton(new HttpClient { Timeout = TimeSpan.FromSeconds(30) });
        builder.Services.AddSingleton<ConfigurationStore>();
        builder.Services.AddSingleton<WindowsTelemetryReader>();
        builder.Services.AddSingleton<ChargePilotApiClient>();
        builder.Services.AddHostedService<TelemetryWorker>();
        await builder.Build().RunAsync();
        return 0;
    }

    private static int ShowHelp()
    {
        AttachConsoleIfAvailable();
        Console.WriteLine("""
            ChargePilot Windows telemetry agent

            Commands:
              ChargePilotAgent.exe ui
              ChargePilotAgent.exe install [--class laptop|desktop] [--interval-minutes N]
              ChargePilotAgent.exe configure [--class laptop|desktop] [--interval-minutes N]
              ChargePilotAgent.exe status
              ChargePilotAgent.exe start
              ChargePilotAgent.exe stop
              ChargePilotAgent.exe deregister
              ChargePilotAgent.exe send-once
              ChargePilotAgent.exe uninstall [--purge-config]

            Install and configure require an elevated administrator terminal. Enter the enrollment token
            at the hidden prompt; never pass it as a command-line argument.
            """);
        return 0;
    }

    private static Dictionary<string, string> ParseOptions(string[] arguments, params string[] allowedOptions)
    {
        var allowed = allowedOptions.ToHashSet(StringComparer.OrdinalIgnoreCase);
        var values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        for (var index = 0; index < arguments.Length; index++)
        {
            var key = arguments[index];
            if (!allowed.Contains(key))
            {
                throw new ArgumentException($"Unknown option '{key}'.");
            }

            if (key == "--purge-config")
            {
                values.Add(key, string.Empty);
                continue;
            }

            if (++index >= arguments.Length || arguments[index].StartsWith("--", StringComparison.Ordinal))
            {
                throw new ArgumentException($"Option '{key}' requires a value.");
            }

            values.Add(key, arguments[index]);
        }

        return values;
    }

    private static int ParseInterval(string? value, int fallback)
    {
        if (value is null)
        {
            return fallback;
        }

        return int.TryParse(value, out var interval)
            ? interval
            : throw new ArgumentException("Reporting interval must be a whole number of minutes.");
    }

    private static string PromptChoice(string label, string defaultValue, params string[] choices)
    {
        Console.Write($"{label} ({string.Join("/", choices)}) [{defaultValue}]: ");
        var value = Console.ReadLine();
        var choice = string.IsNullOrWhiteSpace(value) ? defaultValue : value.Trim().ToLowerInvariant();
        if (!choices.Contains(choice, StringComparer.OrdinalIgnoreCase))
        {
            throw new ArgumentException($"{label} must be one of: {string.Join(", ", choices)}.");
        }

        return choice;
    }

    private static string ReadSecret()
    {
        var secret = new StringBuilder();
        while (true)
        {
            var key = Console.ReadKey(intercept: true);
            if (key.Key == ConsoleKey.Enter)
            {
                Console.WriteLine();
                return secret.ToString();
            }

            if (key.Key == ConsoleKey.Backspace)
            {
                if (secret.Length > 0)
                {
                    secret.Length--;
                    Console.Write("\b \b");
                }

                continue;
            }

            if (!char.IsControl(key.KeyChar))
            {
                secret.Append(key.KeyChar);
                Console.Write('*');
            }
        }
    }

    private static void AttachConsoleIfAvailable()
    {
        if (AttachConsole(AttachParentConsole))
        {
            Console.SetOut(new StreamWriter(Console.OpenStandardOutput()) { AutoFlush = true });
            Console.SetError(new StreamWriter(Console.OpenStandardError()) { AutoFlush = true });
            Console.SetIn(new StreamReader(Console.OpenStandardInput()));
        }
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool AttachConsole(int processId);
}
