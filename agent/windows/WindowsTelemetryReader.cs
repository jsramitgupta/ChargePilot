using System.Management;
using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
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
            DateTimeOffset.UtcNow);
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
