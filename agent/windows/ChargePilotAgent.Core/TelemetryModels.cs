using System.Text.Json.Serialization;

namespace ChargePilotAgent.Core;

public sealed record TelemetryReading(
    string Hostname,
    string? IpAddress,
    int BatteryPercentage,
    bool Charging,
    bool AcConnected,
    DateTimeOffset Timestamp,
    SystemMetrics? SystemMetrics = null);

public sealed record DiskUsage(
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("used_bytes")] long UsedBytes,
    [property: JsonPropertyName("total_bytes")] long TotalBytes);

public sealed record SystemMetrics(
    [property: JsonPropertyName("cpu_usage_percent")] double? CpuUsagePercent,
    [property: JsonPropertyName("gpu_usage_percent")] double? GpuUsagePercent,
    [property: JsonPropertyName("memory_used_bytes")] long? MemoryUsedBytes,
    [property: JsonPropertyName("memory_total_bytes")] long? MemoryTotalBytes,
    [property: JsonPropertyName("disks")] IReadOnlyList<DiskUsage> Disks);

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
    [property: JsonPropertyName("device_class")] string DeviceClass,
    [property: JsonPropertyName("system_metrics")] SystemMetrics? SystemMetrics)
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
            options.DeviceClass,
            reading.SystemMetrics);
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
    [property: JsonPropertyName("message")] string Message,
    [property: JsonPropertyName("reporting_interval_seconds")] int ReportingIntervalSeconds = 300);

public sealed record EndpointCommandResponse(
    [property: JsonPropertyName("command")] ShutdownCommand? Command);

public sealed record ShutdownCommand(
    [property: JsonPropertyName("id")] Guid Id,
    [property: JsonPropertyName("operation")] string Operation,
    [property: JsonPropertyName("grace_period_seconds")] int GracePeriodSeconds,
    [property: JsonPropertyName("expires_at")] DateTimeOffset ExpiresAt);

public sealed record ShutdownAcknowledgement(
    [property: JsonPropertyName("outcome")] string Outcome,
    [property: JsonPropertyName("error")] string? Error = null);

public sealed record SensorClaimEnvelope(
    [property: JsonPropertyName("sensor")] SensorClaim? Sensor);

public sealed record SensorClaim(
    [property: JsonPropertyName("id")] Guid Id,
    [property: JsonPropertyName("sensor_id")] string SensorId,
    [property: JsonPropertyName("claim_token")] string ClaimToken);

public sealed record SensorReport(
    [property: JsonPropertyName("claim_token")] string ClaimToken,
    [property: JsonPropertyName("value")] object? Value,
    [property: JsonPropertyName("error")] string? Error = null);
