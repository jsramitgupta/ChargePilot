namespace ChargePilotAgent.Core;

public sealed record AgentOptions(
    Uri ServerUri,
    string Credential,
    Guid EndpointId,
    Guid InstallationId,
    string DeviceName,
    string DeviceClass,
    string AgentVersion,
    int IntervalMinutes)
{
    public static AgentOptions Create(
        string serverUrl,
        string credential,
        Guid endpointId,
        Guid installationId,
        string deviceName,
        string deviceClass,
        string agentVersion,
        int intervalMinutes)
    {
        if (!Uri.TryCreate(serverUrl.TrimEnd('/'), UriKind.Absolute, out var serverUri) ||
            (serverUri.Scheme != Uri.UriSchemeHttps && !IsLocalDevelopmentUri(serverUri)))
        {
            throw new ArgumentException(
                "Use an HTTPS server URL. Plain HTTP is allowed only for localhost development.",
                nameof(serverUrl));
        }

        if (string.IsNullOrWhiteSpace(credential))
        {
            throw new ArgumentException("An enrolled endpoint credential is required.", nameof(credential));
        }

        if (endpointId == Guid.Empty || installationId == Guid.Empty)
        {
            throw new ArgumentException("Endpoint and installation IDs must be valid UUIDs.");
        }

        if (string.IsNullOrWhiteSpace(deviceName) || deviceName.Trim().Length > 160)
        {
            throw new ArgumentException("Device name must contain 1 to 160 characters.", nameof(deviceName));
        }

        if (deviceClass is not ("laptop" or "desktop"))
        {
            throw new ArgumentException("Windows device class must be laptop or desktop.", nameof(deviceClass));
        }

        if (string.IsNullOrWhiteSpace(agentVersion) || agentVersion.Length > 50)
        {
            throw new ArgumentException("Agent version must contain 1 to 50 characters.", nameof(agentVersion));
        }

        if (intervalMinutes is < 1 or > 60)
        {
            throw new ArgumentOutOfRangeException(
                nameof(intervalMinutes),
                "Reporting interval must be between 1 and 60 minutes.");
        }

        return new AgentOptions(
            new Uri(serverUri.GetLeftPart(UriPartial.Authority).TrimEnd('/')),
            credential,
            endpointId,
            installationId,
            deviceName.Trim(),
            deviceClass,
            agentVersion,
            intervalMinutes);
    }

    private static bool IsLocalDevelopmentUri(Uri uri) =>
        uri.Scheme == Uri.UriSchemeHttp &&
        (uri.Host.Equals("localhost", StringComparison.OrdinalIgnoreCase) ||
         uri.Host.Equals("127.0.0.1", StringComparison.OrdinalIgnoreCase) ||
         uri.Host.Equals("[::1]", StringComparison.OrdinalIgnoreCase) ||
         uri.Host.Equals("::1", StringComparison.OrdinalIgnoreCase));
}
