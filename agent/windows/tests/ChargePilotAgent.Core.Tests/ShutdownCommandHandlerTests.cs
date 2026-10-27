using ChargePilotAgent.Core;
using Xunit;

namespace ChargePilotAgent.Core.Tests;

public sealed class ShutdownCommandHandlerTests
{
    [Fact]
    public async Task HandlesOnlyUnexpiredFixedShutdownRequests()
    {
        var scheduler = new FakeShutdownScheduler();
        var handler = new ShutdownCommandHandler(scheduler);
        var command = new ShutdownCommand(
            Guid.NewGuid(),
            "shutdown",
            60,
            DateTimeOffset.UtcNow.AddMinutes(2));

        await handler.HandleAsync(command);

        Assert.Equal(60, scheduler.GracePeriodSeconds);
    }

    [Theory]
    [InlineData("shell")]
    [InlineData("restart")]
    public async Task RejectsUnknownOperations(string operation)
    {
        var scheduler = new FakeShutdownScheduler();
        var handler = new ShutdownCommandHandler(scheduler);
        var command = new ShutdownCommand(
            Guid.NewGuid(),
            operation,
            60,
            DateTimeOffset.UtcNow.AddMinutes(2));

        await Assert.ThrowsAsync<InvalidDataException>(() => handler.HandleAsync(command));
        Assert.Null(scheduler.GracePeriodSeconds);
    }

    [Fact]
    public async Task RejectsExpiredRequests()
    {
        var scheduler = new FakeShutdownScheduler();
        var handler = new ShutdownCommandHandler(scheduler);
        var command = new ShutdownCommand(
            Guid.NewGuid(),
            "shutdown",
            60,
            DateTimeOffset.UtcNow.AddSeconds(-1));

        await Assert.ThrowsAsync<InvalidDataException>(() => handler.HandleAsync(command));
        Assert.Null(scheduler.GracePeriodSeconds);
    }

    private sealed class FakeShutdownScheduler : IShutdownScheduler
    {
        public int? GracePeriodSeconds { get; private set; }

        public Task ScheduleAsync(int gracePeriodSeconds, CancellationToken cancellationToken)
        {
            GracePeriodSeconds = gracePeriodSeconds;
            return Task.CompletedTask;
        }
    }
}
