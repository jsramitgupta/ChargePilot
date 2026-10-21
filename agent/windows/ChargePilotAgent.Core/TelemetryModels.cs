using System.Text.Json.Serialization;

namespace ChargePilotAgent.Core;

public sealed record TelemetryReading(
    string Hostname,
    string? IpAddress,
    int BatteryPercentage,
    bool Charging,
    bool AcConnected,
    DateTimeOffset Timestamp);

public sealed record TelemetryRequest(
    [property: JsonPropertyName("hostname")] string Hostname,
    [property: JsonPropertyName("ip_address")] string? IpAddress,
    [property: JsonPropertyName("battery_percentage")] int BatteryPercentage,
    [property: JsonPropertyName("charging")] bool Charging,
    [property: JsonPropertyName("ac_connected")] bool AcConnected,
    [property: JsonPropertyName("switch_state")] bool? SwitchState,
    [property: JsonPropertyName("timestamp")] DateTimeOffset Timestamp,
    [property: JsonPropertyName("agent_version")] string AgentVersion,
    [property: JsonPropertyName("installation_id")] Guid InstallationId,
    [property: JsonPropertyName("platform")] string Platform,
    [property: JsonPropertyName("device_class")] string DeviceClass)
{
    public static TelemetryRequest From(AgentOptions options, TelemetryReading reading) =>
        new(
            reading.Hostname,
            reading.IpAddress,
            reading.BatteryPercentage,
            reading.Charging,
            reading.AcConnected,
            null,
            reading.Timestamp.ToUniversalTime(),
            options.AgentVersion,
            options.InstallationId,
            "windows",
            options.DeviceClass);
}

public sealed record EnrollmentRequest(
    [property: JsonPropertyName("code")] string Code,
    [property: JsonPropertyName("platform")] string Platform,
    [property: JsonPropertyName("installation_id")] Guid InstallationId,
    [property: JsonPropertyName("hostname")] string Hostname,
    [property: JsonPropertyName("device_class")] string DeviceClass);

public sealed record EnrollmentResponse(
    [property: JsonPropertyName("endpoint_id")] Guid EndpointId,
    [property: JsonPropertyName("installation_id")] Guid InstallationId,
    [property: JsonPropertyName("platform")] string Platform,
    [property: JsonPropertyName("credential")] string Credential);

public sealed record TelemetryResponse(
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("message")] string Message);
