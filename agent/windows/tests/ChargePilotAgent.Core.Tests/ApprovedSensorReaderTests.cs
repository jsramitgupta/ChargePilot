using ChargePilotAgent.Core;
using Xunit;

namespace ChargePilotAgent.Core.Tests;

public sealed class ApprovedSensorReaderTests
{
    [Fact]
    public void ReadsOnlyFixedReadOnlySensorIds()
    {
        Assert.False(string.IsNullOrWhiteSpace((string)ApprovedSensorReader.Read("os_version")));
        Assert.True((long)ApprovedSensorReader.Read("uptime_seconds") >= 0);
        Assert.Throws<ArgumentException>(() => ApprovedSensorReader.Read("powershell"));
    }

    [Fact]
    public void ReadsSystemVolumeFreeSpace()
    {
        Assert.True((long)ApprovedSensorReader.Read("system_disk_free_bytes") >= 0);
    }
}
