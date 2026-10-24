using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Management;
using ChargePilotAgent.Core;

namespace ChargePilotAgent;

internal sealed class WindowsTelemetryReader
{
    public TelemetryReading Read(string deviceName)
    {
        var battery = ReadBattery();
        return new TelemetryReading(
            deviceName,
            ReadIpAddress(),
            battery.BatteryPercentage,
            battery.Charging,
            battery.AcConnected,
            DateTimeOffset.UtcNow,
            ReadSystemMetrics());
    }

    private static SystemMetrics ReadSystemMetrics()
    {
        var memory = ReadMemoryUsage();
        return new(
            ReadCpuUsage(),
            ReadGpuUsage(),
            memory.UsedBytes,
            memory.TotalBytes,
            ReadDiskUsage());
    }

    private static double? ReadCpuUsage()
    {
        try
        {
            using var searcher = new ManagementObjectSearcher(
                "SELECT LoadPercentage FROM Win32_Processor");
            using var results = searcher.Get();
            var readings = results.Cast<ManagementObject>()
                .Select(processor =>
                {
                    using (processor)
                    {
                        return Convert.ToDouble(processor["LoadPercentage"]);
                    }
                })
                .ToArray();
            return readings.Length == 0 ? null : readings.Average();
        }
        catch (ManagementException)
        {
            return null;
        }
    }

    private static double? ReadGpuUsage()
    {
        try
        {
            using var searcher = new ManagementObjectSearcher(
                "SELECT UtilizationPercentage FROM Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine");
            using var results = searcher.Get();
            var readings = results.Cast<ManagementObject>()
                .Select(engine =>
                {
                    using (engine)
                    {
                        return Convert.ToDouble(engine["UtilizationPercentage"]);
                    }
                })
                .ToArray();
            return readings.Length == 0 ? null : Math.Clamp(readings.Max(), 0, 100);
        }
        catch (ManagementException)
        {
            return null;
        }
    }

    private static (long? UsedBytes, long? TotalBytes) ReadMemoryUsage()
    {
        try
        {
            using var searcher = new ManagementObjectSearcher(
                "SELECT TotalVisibleMemorySize, FreePhysicalMemory FROM Win32_OperatingSystem");
            using var results = searcher.Get();
            var operatingSystem = results.Cast<ManagementObject>().FirstOrDefault();
            if (operatingSystem is null)
            {
                return (null, null);
            }

            using (operatingSystem)
            {
                var total = Convert.ToInt64(operatingSystem["TotalVisibleMemorySize"]) * 1024;
                var free = Convert.ToInt64(operatingSystem["FreePhysicalMemory"]) * 1024;
                return (Math.Max(0, total - free), total);
            }
        }
        catch (ManagementException)
        {
            return (null, null);
        }
    }

    private static IReadOnlyList<DiskUsage> ReadDiskUsage()
    {
        try
        {
            using var searcher = new ManagementObjectSearcher(
                "SELECT DeviceID, Size, FreeSpace FROM Win32_LogicalDisk WHERE DriveType = 3");
            using var results = searcher.Get();
            return results.Cast<ManagementObject>()
                .Select(disk =>
                {
                    using (disk)
                    {
                        var total = Convert.ToInt64(disk["Size"]);
                        var free = Convert.ToInt64(disk["FreeSpace"]);
                        return new DiskUsage(
                            Convert.ToString(disk["DeviceID"]) ?? "Local disk",
                            Math.Max(0, total - free),
                            total);
                    }
                })
                .Where(disk => disk.TotalBytes > 0)
                .Take(16)
                .ToArray();
        }
        catch (ManagementException)
        {
            return [];
        }
    }

    private static (int BatteryPercentage, bool Charging, bool AcConnected) ReadBattery()
    {
        using var searcher = new ManagementObjectSearcher(
            "SELECT EstimatedChargeRemaining, BatteryStatus FROM Win32_Battery");
        using var results = searcher.Get();
        var battery = results.Cast<ManagementObject>().FirstOrDefault();
        if (battery is null)
        {
            return (100, false, false);
        }

        using (battery)
        {
            var percentage = Convert.ToInt32(battery["EstimatedChargeRemaining"] ?? 100);
            var status = Convert.ToInt32(battery["BatteryStatus"] ?? 0);
            return (
                Math.Clamp(percentage, 0, 100),
                status is >= 6 and <= 9,
                status is 2 or 3 or >= 6 and <= 9);
        }
    }

    private static string? ReadIpAddress()
    {
        return NetworkInterface.GetAllNetworkInterfaces()
            .Where(adapter =>
                adapter.OperationalStatus == OperationalStatus.Up &&
                adapter.NetworkInterfaceType != NetworkInterfaceType.Loopback)
            .SelectMany(adapter => adapter.GetIPProperties().UnicastAddresses)
            .Select(address => address.Address)
            .FirstOrDefault(address =>
                address.AddressFamily == AddressFamily.InterNetwork &&
                !IPAddress.IsLoopback(address) &&
                !address.ToString().StartsWith("169.254.", StringComparison.Ordinal))
            ?.ToString();
    }
}
