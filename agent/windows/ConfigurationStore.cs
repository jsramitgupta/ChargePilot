using System.Diagnostics;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Text.Json;
using ChargePilotAgent.Core;

namespace ChargePilotAgent;

internal sealed class ConfigurationStore
{
    private const string Entropy = "ChargePilot Windows Agent configuration v1";
    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };

    public string ConfigurationPath => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
        "ChargePilot",
        "Agent",
        "config.json");

    public AgentOptions? Load()
    {
        if (!File.Exists(ConfigurationPath))
        {
            return null;
        }

        var stored = JsonSerializer.Deserialize<StoredConfiguration>(
            File.ReadAllText(ConfigurationPath),
            JsonOptions) ?? throw new InvalidDataException("The ChargePilot service configuration is empty.");
        if (stored.SchemaVersion != 1)
        {
            throw new InvalidDataException("The ChargePilot service configuration version is not supported.");
        }

        var encryptedCredential = Convert.FromBase64String(stored.ProtectedCredential);
        var credentialBytes = ProtectedData.Unprotect(
            encryptedCredential,
            Encoding.UTF8.GetBytes(Entropy),
            DataProtectionScope.LocalMachine);
        try
        {
            return AgentOptions.Create(
                stored.ServerUrl,
                Encoding.UTF8.GetString(credentialBytes),
                Guid.Parse(stored.EndpointId),
                Guid.Parse(stored.InstallationId),
                stored.DeviceName,
                stored.DeviceClass,
                stored.AgentVersion,
                stored.IntervalMinutes);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(credentialBytes);
        }
    }

    public void Save(AgentOptions options)
    {
        var directory = Path.GetDirectoryName(ConfigurationPath)
            ?? throw new InvalidOperationException("Unable to determine the configuration directory.");
        Directory.CreateDirectory(directory);
        RestrictDirectoryAccess(directory);

        var credentialBytes = Encoding.UTF8.GetBytes(options.Credential);
        try
        {
            var protectedCredential = ProtectedData.Protect(
                credentialBytes,
                Encoding.UTF8.GetBytes(Entropy),
                DataProtectionScope.LocalMachine);
            var stored = new StoredConfiguration(
                1,
                options.ServerUri.ToString().TrimEnd('/'),
                options.EndpointId.ToString("D"),
                options.InstallationId.ToString("D"),
                options.DeviceName,
                options.DeviceClass,
                options.AgentVersion,
                options.IntervalMinutes,
                Convert.ToBase64String(protectedCredential));
            var temporaryPath = ConfigurationPath + "." + Guid.NewGuid().ToString("N") + ".tmp";
            try
            {
                File.WriteAllText(temporaryPath, JsonSerializer.Serialize(stored, JsonOptions), new UTF8Encoding(false));
                RestrictDirectoryAccess(directory);
                File.Move(temporaryPath, ConfigurationPath, overwrite: true);
            }
            finally
            {
                if (File.Exists(temporaryPath))
                {
                    File.Delete(temporaryPath);
                }
            }
        }
        finally
        {
            CryptographicOperations.ZeroMemory(credentialBytes);
        }
    }

    public AgentOptions? ImportLegacyUserConfiguration()
    {
        var legacyPath = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "ChargePilot",
            "agent-config.json");
        if (!File.Exists(legacyPath))
        {
            return null;
        }

        using var document = JsonDocument.Parse(File.ReadAllText(legacyPath));
        var root = document.RootElement;
        var serverUrl = ReadString(root, "serverUrl");
        var endpointId = ReadGuid(root, "endpointId");
        var installationId = ReadGuid(root, "installationId");
        var deviceName = ReadString(root, "hostname");
        if (string.IsNullOrWhiteSpace(deviceName))
        {
            deviceName = Environment.MachineName;
        }

        var deviceClass = ReadString(root, "deviceClass");
        if (deviceClass is not ("laptop" or "desktop"))
        {
            deviceClass = "laptop";
        }

        var agentVersion = ReadString(root, "agentVersion");
        if (string.IsNullOrWhiteSpace(agentVersion))
        {
            agentVersion = "1.0.0";
        }

        var protectedToken = ReadString(root, "protectedEndpointToken");
        string? credential;
        if (!string.IsNullOrWhiteSpace(protectedToken))
        {
            var bytes = Convert.FromHexString(protectedToken);
            var plaintext = ProtectedData.Unprotect(bytes, null, DataProtectionScope.CurrentUser);
            try
            {
                using var secure = new System.Security.SecureString();
                foreach (var character in Encoding.Unicode.GetString(plaintext))
                {
                    secure.AppendChar(character);
                }

                secure.MakeReadOnly();
                var pointer = System.Runtime.InteropServices.Marshal.SecureStringToBSTR(secure);
                try
                {
                    credential = System.Runtime.InteropServices.Marshal.PtrToStringBSTR(pointer);
                }
                finally
                {
                    System.Runtime.InteropServices.Marshal.ZeroFreeBSTR(pointer);
                }
            }
            finally
            {
                CryptographicOperations.ZeroMemory(plaintext);
            }
        }
        else
        {
            credential = ReadString(root, "endpointToken");
        }

        if (string.IsNullOrWhiteSpace(serverUrl) ||
            endpointId == Guid.Empty ||
            installationId == Guid.Empty ||
            string.IsNullOrWhiteSpace(credential))
        {
            throw new InvalidDataException(
                "The old Windows agent configuration is incomplete. Enter a fresh enrollment token to connect this device.");
        }

        return AgentOptions.Create(
            serverUrl,
            credential,
            endpointId,
            installationId,
            deviceName,
            deviceClass,
            agentVersion,
            intervalMinutes: 5);
    }

    public void Delete()
    {
        if (File.Exists(ConfigurationPath))
        {
            File.Delete(ConfigurationPath);
        }
    }

    private static string ReadString(JsonElement root, string propertyName) =>
        root.TryGetProperty(propertyName, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString() ?? string.Empty
            : string.Empty;

    private static Guid ReadGuid(JsonElement root, string propertyName) =>
        Guid.TryParse(ReadString(root, propertyName), out var value) ? value : Guid.Empty;

    private static void RestrictDirectoryAccess(string directory)
    {
        using var process = new Process
        {
            StartInfo = new ProcessStartInfo
            {
                FileName = "icacls.exe",
                UseShellExecute = false,
                CreateNoWindow = true,
            },
        };
        process.StartInfo.ArgumentList.Add(directory);
        process.StartInfo.ArgumentList.Add("/inheritance:r");
        process.StartInfo.ArgumentList.Add("/grant:r");
        process.StartInfo.ArgumentList.Add("*S-1-5-18:(OI)(CI)F");
        process.StartInfo.ArgumentList.Add("*S-1-5-32-544:(OI)(CI)F");
        process.Start();
        process.WaitForExit();
        if (process.ExitCode != 0)
        {
            throw new InvalidOperationException("Could not restrict access to the Windows agent configuration directory.");
        }
    }

    private sealed record StoredConfiguration(
        int SchemaVersion,
        string ServerUrl,
        string EndpointId,
        string InstallationId,
        string DeviceName,
        string DeviceClass,
        string AgentVersion,
        int IntervalMinutes,
        string ProtectedCredential);
}
