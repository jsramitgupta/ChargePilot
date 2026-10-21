using System.Text.Json;
using ChargePilotAgent.Core;
using Xunit;

namespace ChargePilotAgent.Core.Tests;

public sealed class AgentOptionsTests
{
    [Theory]
    [InlineData("https://api.example.test", true)]
    [InlineData("http://localhost:8000", true)]
    [InlineData("http://127.0.0.1:8000", true)]
    [InlineData("http://api.example.test", false)]
    public void CreateRequiresHttpsOutsideLocalDevelopment(string serverUrl, bool valid)
    {
        if (valid)
        {
            var options = Create(serverUrl);
            Assert.Equal(serverUrl.TrimEnd('/'), options.ServerUri.ToString().TrimEnd('/'));
        }
        else
        {
            Assert.Throws<ArgumentException>(() => Create(serverUrl));
        }
    }

    [Theory]
    [InlineData(0)]
    [InlineData(61)]
    public void CreateRejectsUnsupportedIntervals(int interval)
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => Create(intervalMinutes: interval));
    }

    [Theory]
    [InlineData("phone")]
    [InlineData("tablet")]
    [InlineData("server")]
    public void CreateRejectsUnsupportedWindowsDeviceClasses(string deviceClass)
    {
        Assert.Throws<ArgumentException>(() => Create(deviceClass: deviceClass));
    }

    [Fact]
    public void TelemetryRequestUsesEnrolledIdentityAndLeavesSwitchStateToBackend()
    {
        var options = Create();
        var timestamp = new DateTimeOffset(2026, 10, 21, 10, 30, 0, TimeSpan.FromHours(5.5));
        var reading = new TelemetryReading(
            "WORKSTATION-7",
            "192.168.1.7",
            73,
            true,
            true,
            timestamp);

        var payload = TelemetryRequest.From(options, reading);

        Assert.Equal(options.InstallationId, payload.InstallationId);
        Assert.Equal(options.DeviceClass, payload.DeviceClass);
        Assert.Equal("windows", payload.Platform);
        Assert.Null(payload.SwitchState);
        Assert.Equal(timestamp.ToUniversalTime(), payload.Timestamp);
    }

    [Fact]
    public void TelemetryRequestSerializesTheBackendContract()
    {
        var options = Create();
        var reading = new TelemetryReading(
            "WORKSTATION-7",
            "192.168.1.7",
            73,
            true,
            true,
            DateTimeOffset.Parse("2026-10-21T05:00:00Z"));

        using var document = JsonDocument.Parse(JsonSerializer.Serialize(TelemetryRequest.From(options, reading)));
        var payload = document.RootElement;

        Assert.Equal(11, payload.EnumerateObject().Count());
        Assert.Equal("WORKSTATION-7", payload.GetProperty("hostname").GetString());
        Assert.Equal("192.168.1.7", payload.GetProperty("ip_address").GetString());
        Assert.Equal(73, payload.GetProperty("battery_percentage").GetInt32());
        Assert.True(payload.GetProperty("charging").GetBoolean());
        Assert.True(payload.GetProperty("ac_connected").GetBoolean());
        Assert.Equal(JsonValueKind.Null, payload.GetProperty("switch_state").ValueKind);
        Assert.Equal(options.InstallationId, payload.GetProperty("installation_id").GetGuid());
        Assert.Equal("windows", payload.GetProperty("platform").GetString());
        Assert.Equal("laptop", payload.GetProperty("device_class").GetString());
        Assert.Equal("1.0.0", payload.GetProperty("agent_version").GetString());
    }

    private static AgentOptions Create(
        string serverUrl = "https://api.example.test",
        int intervalMinutes = 5,
        string deviceClass = "laptop") =>
        AgentOptions.Create(
            serverUrl,
            "credential-for-tests-only",
            Guid.NewGuid(),
            Guid.NewGuid(),
            "Workstation",
            deviceClass,
            "1.0.0",
            intervalMinutes);
}
