using System.Runtime.InteropServices;
using System.Text;
using ChargePilotAgent.Core;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace ChargePilotAgent;

internal static class Program
{
    private const int AttachParentConsole = -1;

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
                "send-once" => RunSendOnceAsync().GetAwaiter().GetResult(),
                "help" or "--help" or "-h" => ShowHelp(),
                _ => throw new ArgumentException($"Unknown command '{command}'. Run ChargePilotAgent.exe help for available commands."),
            };
        }
        catch (Exception exception)
        {
            AttachConsoleIfAvailable();
            Console.Error.WriteLine(exception.Message);
            return 1;
        }
    }

    private static int RunUi(string[] arguments)
    {
        var values = ParseOptions(arguments, "--server-url", "--agent-version");
        AttachConsoleIfAvailable();
        ApplicationConfiguration.Initialize();
        Application.Run(new SetupForm(
            values.GetValueOrDefault("--server-url") ?? string.Empty,
            values.GetValueOrDefault("--agent-version") ?? "1.0.0"));
        return 0;
    }

    private static int RunInteractiveConfiguration(string[] arguments, bool allowExisting)
    {
        AttachConsoleIfAvailable();
        var values = ParseOptions(
            arguments,
            "--server-url",
            "--name",
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

        var serverUrl = values.GetValueOrDefault("--server-url") ?? Prompt(
            "ChargePilot server URL",
            previous?.ServerUri.ToString() ?? "https://api-chargepilot.endusercompute.in");
        var deviceName = values.GetValueOrDefault("--name") ?? Prompt(
            "Device name",
            previous?.DeviceName ?? Environment.MachineName);
        var deviceClass = values.GetValueOrDefault("--class") ?? PromptChoice(
            "Device class",
            previous?.DeviceClass ?? "laptop",
            "laptop",
            "desktop");
        var interval = ParseInterval(values.GetValueOrDefault("--interval-minutes"), previous?.IntervalMinutes ?? 5);
        Console.Write("Enrollment token (leave blank to keep the current enrollment): ");
        var enrollmentToken = ReadSecret();
        var serverUri = ParseServerUri(serverUrl);

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
                "1.0.0",
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
                throw new InvalidOperationException("Enter a new enrollment token when changing the server URL.");
            }

            options = AgentOptions.Create(
                serverUri.ToString(),
                previous.Credential,
                previous.EndpointId,
                previous.InstallationId,
                deviceName,
                deviceClass,
                "1.0.0",
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
              ChargePilotAgent.exe ui [--server-url URL]
              ChargePilotAgent.exe install [--server-url URL] [--name NAME] [--class laptop|desktop] [--interval-minutes N]
              ChargePilotAgent.exe configure [--server-url URL] [--name NAME] [--class laptop|desktop] [--interval-minutes N]
              ChargePilotAgent.exe status
              ChargePilotAgent.exe start
              ChargePilotAgent.exe stop
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

    private static Uri ParseServerUri(string value)
    {
        if (!Uri.TryCreate(value.TrimEnd('/'), UriKind.Absolute, out var serverUri))
        {
            throw new ArgumentException("Enter a valid ChargePilot server URL.");
        }

        return serverUri;
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

    private static string Prompt(string label, string defaultValue)
    {
        Console.Write($"{label} [{defaultValue}]: ");
        var value = Console.ReadLine();
        return string.IsNullOrWhiteSpace(value) ? defaultValue : value.Trim();
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
