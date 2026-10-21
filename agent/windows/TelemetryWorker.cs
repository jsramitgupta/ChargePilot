using ChargePilotAgent.Core;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace ChargePilotAgent;

internal sealed class TelemetryWorker(
    ConfigurationStore configurationStore,
    WindowsTelemetryReader telemetryReader,
    ChargePilotApiClient apiClient,
    ILogger<TelemetryWorker> logger) : BackgroundService
{
    private static readonly TimeSpan ConfigurationRetryInterval = TimeSpan.FromMinutes(1);

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            TimeSpan nextInterval = ConfigurationRetryInterval;
            try
            {
                var options = configurationStore.Load();
                if (options is null)
                {
                    logger.LogError("Windows agent is not configured. Open ChargePilot Agent and connect this device.");
                }
                else
                {
                    nextInterval = TimeSpan.FromMinutes(options.IntervalMinutes);
                    var reading = telemetryReader.Read(options.DeviceName);
                    await apiClient.SendTelemetryAsync(options, reading, stoppingToken);
                    logger.LogInformation(
                        "Telemetry accepted for endpoint {EndpointId} at {Timestamp}.",
                        options.EndpointId,
                        reading.Timestamp);
                }
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception exception)
            {
                logger.LogError(exception, "Windows telemetry report failed.");
            }

            try
            {
                await Task.Delay(nextInterval, stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
        }
    }
}
