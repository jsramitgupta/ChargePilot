using ChargePilotAgent.Core;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace ChargePilotAgent;

internal sealed class SensorWorker(
    ConfigurationStore configurationStore,
    ChargePilotApiClient apiClient,
    ILogger<SensorWorker> logger) : BackgroundService
{
    private static readonly TimeSpan PollInterval = TimeSpan.FromMinutes(1);

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                var options = configurationStore.Load();
                if (options is not null)
                {
                    await CollectOneAsync(options, stoppingToken);
                }
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception exception)
            {
                logger.LogWarning(exception, "Windows sensor polling failed.");
            }

            try
            {
                await Task.Delay(PollInterval, stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
        }
    }

    private async Task CollectOneAsync(AgentOptions options, CancellationToken cancellationToken)
    {
        var claim = await apiClient.ClaimSensorAsync(options, cancellationToken);
        if (claim is null)
        {
            return;
        }

        object? value;
        try
        {
            value = ApprovedSensorReader.Read(claim.SensorId);
        }
        catch (Exception exception)
        {
            await apiClient.ReportSensorAsync(
                options,
                claim,
                new SensorReport(claim.ClaimToken, null, exception.Message[..Math.Min(255, exception.Message.Length)]),
                cancellationToken);
            return;
        }

        await apiClient.ReportSensorAsync(
            options,
            claim,
            new SensorReport(claim.ClaimToken, value),
            cancellationToken);
    }
}
