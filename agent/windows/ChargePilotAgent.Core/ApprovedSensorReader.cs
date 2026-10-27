namespace ChargePilotAgent.Core;

public static class ApprovedSensorReader
{
    public static object Read(string sensorId)
    {
        return sensorId switch
        {
            "os_version" => Environment.OSVersion.VersionString,
            "uptime_seconds" => Math.Max(0, Environment.TickCount64 / 1000),
            "system_disk_free_bytes" => ReadSystemDiskFreeBytes(),
            _ => throw new ArgumentException("The requested sensor is not in the approved catalog.", nameof(sensorId)),
        };
    }

    private static long ReadSystemDiskFreeBytes()
    {
        var systemRoot = Path.GetPathRoot(Environment.SystemDirectory);
        if (string.IsNullOrEmpty(systemRoot))
        {
            throw new InvalidOperationException("The system volume could not be determined.");
        }

        var drive = new DriveInfo(systemRoot);
        if (!drive.IsReady)
        {
            throw new IOException("The system volume is not ready.");
        }

        return Math.Max(0, drive.AvailableFreeSpace);
    }
}
