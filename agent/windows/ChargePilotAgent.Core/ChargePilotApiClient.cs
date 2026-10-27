using System.Net.Http.Headers;
using System.Net.Http.Json;

namespace ChargePilotAgent.Core;

public sealed class ChargePilotApiClient(HttpClient httpClient)
{
    public async Task DeregisterAsync(
        Uri serverUri,
        string credential,
        CancellationToken cancellationToken = default)
    {
        EnsureSecureOrigin(serverUri);
        using var request = new HttpRequestMessage(
            HttpMethod.Post,
            new Uri(serverUri, "/api/v1/endpoint-enrollment/deregister"))
        {
            Content = JsonContent.Create(new { }),
        };
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", credential);
        using var response = await httpClient.SendAsync(request, cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            throw new HttpRequestException(
                $"Deregistration failed with HTTP {(int)response.StatusCode}. Check the server and endpoint credential.",
                null,
                response.StatusCode);
        }
    }

    public async Task<EnrollmentResponse> EnrollAsync(
        Uri serverUri,
        string enrollmentCode,
        Guid installationId,
        string hostname,
        string deviceClass,
        CancellationToken cancellationToken = default)
    {
        EnsureSecureOrigin(serverUri);
        if (string.IsNullOrWhiteSpace(enrollmentCode))
        {
            throw new ArgumentException("An enrollment token is required.", nameof(enrollmentCode));
        }

        var request = new EnrollmentRequest(
            enrollmentCode,
            "windows",
            installationId,
            hostname,
            deviceClass);
        using var response = await httpClient.PostAsJsonAsync(
            new Uri(serverUri, "/api/v1/endpoint-enrollment/exchange"),
            request,
            cancellationToken);

        if (!response.IsSuccessStatusCode)
        {
            throw new HttpRequestException(
                $"Enrollment failed with HTTP {(int)response.StatusCode}. Check the token, expiry, server URL, and enabled platform settings.",
                null,
                response.StatusCode);
        }

        var result = await response.Content.ReadFromJsonAsync<EnrollmentResponse>(
            cancellationToken: cancellationToken);
        if (result is null ||
            result.EndpointId == Guid.Empty ||
            result.InstallationId != installationId ||
            string.IsNullOrWhiteSpace(result.Credential))
        {
            throw new InvalidDataException("The server returned an incomplete endpoint credential response.");
        }

        return result;
    }

    public async Task<int> SendTelemetryAsync(
        AgentOptions options,
        TelemetryReading reading,
        CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(
            HttpMethod.Post,
            new Uri(options.ServerUri, "/api/v1/telemetry"))
        {
            Content = JsonContent.Create(TelemetryRequest.From(options, reading)),
        };
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", options.Credential);

        using var response = await httpClient.SendAsync(request, cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            throw new HttpRequestException(
                $"Telemetry was rejected with HTTP {(int)response.StatusCode}. Check the service configuration and endpoint enrollment.",
                null,
                response.StatusCode);
        }
        var result = await response.Content.ReadFromJsonAsync<TelemetryResponse>(
            cancellationToken: cancellationToken);
        return result?.ReportingIntervalSeconds is >= 300 and <= 86400
            ? result.ReportingIntervalSeconds
            : options.IntervalMinutes * 60;
    }

    public async Task<ShutdownCommand?> ClaimShutdownCommandAsync(
        AgentOptions options,
        CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(
            HttpMethod.Post,
            new Uri(options.ServerUri, "/api/v1/endpoint-commands/claim"))
        {
            Content = JsonContent.Create(new { }),
        };
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", options.Credential);
        using var response = await httpClient.SendAsync(request, cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            throw new HttpRequestException(
                $"Endpoint command check failed with HTTP {(int)response.StatusCode}.",
                null,
                response.StatusCode);
        }

        var result = await response.Content.ReadFromJsonAsync<EndpointCommandResponse>(
            cancellationToken: cancellationToken);
        if (result?.Command is not { } command)
        {
            return null;
        }
        if (command.Id == Guid.Empty ||
            command.Operation != "shutdown" ||
            command.GracePeriodSeconds is < 30 or > 120)
        {
            throw new InvalidDataException("The server returned an unsupported endpoint command.");
        }
        return command;
    }

    public async Task AcknowledgeShutdownCommandAsync(
        AgentOptions options,
        Guid commandId,
        ShutdownAcknowledgement acknowledgement,
        CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(
            HttpMethod.Post,
            new Uri(options.ServerUri, $"/api/v1/endpoint-commands/{commandId:D}/acknowledge"))
        {
            Content = JsonContent.Create(acknowledgement),
        };
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", options.Credential);
        using var response = await httpClient.SendAsync(request, cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            throw new HttpRequestException(
                $"Endpoint command acknowledgement failed with HTTP {(int)response.StatusCode}.",
                null,
                response.StatusCode);
        }
    }

    private static void EnsureSecureOrigin(Uri serverUri)
    {
        var isLocalhost = serverUri.Host.Equals("localhost", StringComparison.OrdinalIgnoreCase) ||
                          serverUri.Host.Equals("127.0.0.1", StringComparison.OrdinalIgnoreCase) ||
                          serverUri.Host.Equals("::1", StringComparison.OrdinalIgnoreCase);
        if (serverUri.Scheme != Uri.UriSchemeHttps &&
            !(serverUri.Scheme == Uri.UriSchemeHttp && isLocalhost))
        {
            throw new ArgumentException(
                "Enrollment requires HTTPS. Plain HTTP is allowed only for localhost development.",
                nameof(serverUri));
        }
    }
}
