namespace ChargePilotAgent.Core;

public interface IShutdownScheduler
{
    Task ScheduleAsync(int gracePeriodSeconds, CancellationToken cancellationToken);
}

public sealed class ShutdownCommandHandler(IShutdownScheduler scheduler)
{
    public Task HandleAsync(ShutdownCommand command, CancellationToken cancellationToken = default)
    {
        if (command.Operation != "shutdown" ||
            command.Id == Guid.Empty ||
            command.GracePeriodSeconds is < 30 or > 120 ||
            command.ExpiresAt <= DateTimeOffset.UtcNow)
        {
            throw new InvalidDataException("The endpoint command is not a supported shutdown request.");
        }

        return scheduler.ScheduleAsync(command.GracePeriodSeconds, cancellationToken);
    }
}
