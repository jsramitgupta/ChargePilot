import Darwin
import Foundation
import IOKit.ps
import Security

private let agentVersion = "0.1.0"
private let reportingInterval = Duration.seconds(300)
private let keychainService = "in.chargepilot.telemetry"

private struct LocalConfiguration: Codable {
    let serverURL: String
    let installationID: UUID
    let label: String
}

private struct EnrollmentRequest: Encodable {
    let code: String
    let platform = "macos"
    let installationID: UUID
    let hostname: String
    let deviceClass = "laptop"

    enum CodingKeys: String, CodingKey {
        case code
        case platform
        case installationID = "installation_id"
        case hostname
        case deviceClass = "device_class"
    }
}

private struct EnrollmentResponse: Decodable {
    let endpointID: UUID
    let installationID: UUID
    let credential: String

    enum CodingKeys: String, CodingKey {
        case endpointID = "endpoint_id"
        case installationID = "installation_id"
        case credential
    }
}

private struct TelemetryRequest: Encodable {
    let hostname: String
    let installationID: UUID
    let platform = "macos"
    let deviceClass = "laptop"
    let batteryPercentage: Int
    let charging: Bool
    let acConnected: Bool?
    let timestamp: String
    let agentVersion: String

    enum CodingKeys: String, CodingKey {
        case hostname
        case installationID = "installation_id"
        case platform
        case deviceClass = "device_class"
        case batteryPercentage = "battery_percentage"
        case charging
        case acConnected = "ac_connected"
        case timestamp
        case agentVersion = "agent_version"
    }
}

private struct BatteryReading {
    let percentage: Int
    let charging: Bool
    let acConnected: Bool?
}

@main
private struct ChargePilotAgent {
    static func main() async {
        do {
            let arguments = Array(CommandLine.arguments.dropFirst())
            guard let command = arguments.first else {
                throw AgentError.usage
            }
            switch command {
            case "enroll":
                try await enroll(arguments: Array(arguments.dropFirst()))
            case "run":
                try await run()
            default:
                throw AgentError.usage
            }
        } catch {
            fputs("ChargePilot agent: \(error.localizedDescription)\n", stderr)
            exit(EXIT_FAILURE)
        }
    }

    private static func enroll(arguments: [String]) async throws {
        let options = parseOptions(arguments)
        guard let rawServerURL = options["--server-url"],
              let label = options["--label"]?.trimmingCharacters(in: .whitespacesAndNewlines),
              !label.isEmpty
        else {
            throw AgentError.usage
        }
        let serverURL = try validatedServerURL(rawServerURL)
        let installationID = UUID()
        let configuration = LocalConfiguration(
            serverURL: serverURL.absoluteString,
            installationID: installationID,
            label: label
        )
        try saveConfiguration(configuration)

        fputs("Enrollment code: ", stderr)
        let code = try readHiddenLine()
        guard !code.isEmpty else {
            throw AgentError.invalidEnrollmentCode
        }

        let requestBody = EnrollmentRequest(
            code: code,
            installationID: installationID,
            hostname: label
        )
        let response: EnrollmentResponse = try await post(
            to: serverURL.appendingPathComponent("api/v1/endpoint-enrollment/exchange"),
            body: requestBody
        )
        guard response.installationID == installationID else {
            throw AgentError.invalidServerResponse
        }
        try storeCredential(response.credential, installationID: installationID)
        print("Enrolled endpoint \(response.endpointID). Credential saved to Keychain.")
        print("Run `swift run -c release ChargePilotAgent run` to start telemetry.")
    }

    private static func run() async throws {
        let configuration = try loadConfiguration()
        let credential = try loadCredential(installationID: configuration.installationID)
        let serverURL = try validatedServerURL(configuration.serverURL)
        let endpoint = serverURL.appendingPathComponent("api/v1/telemetry")

        while true {
            do {
                let reading = try readBattery()
                let body = TelemetryRequest(
                    hostname: configuration.label,
                    installationID: configuration.installationID,
                    batteryPercentage: reading.percentage,
                    charging: reading.charging,
                    acConnected: reading.acConnected,
                    timestamp: ISO8601DateFormatter().string(from: Date()),
                    agentVersion: agentVersion
                )
                try await postAccepted(to: endpoint, body: body, credential: credential)
                print("Reported battery at \(reading.percentage)% (\(Date())).")
            } catch {
                fputs("Telemetry was not accepted: \(error.localizedDescription)\n", stderr)
            }
            try await Task.sleep(for: reportingInterval)
        }
    }

    private static func readBattery() throws -> BatteryReading {
        guard let information = IOPSCopyPowerSourcesInfo()?.takeRetainedValue(),
              let sourceList = IOPSCopyPowerSourcesList(information)?.takeRetainedValue() as? [CFTypeRef]
        else {
            throw AgentError.batteryUnavailable
        }

        for source in sourceList {
            guard let description = IOPSGetPowerSourceDescription(information, source)?
                .takeUnretainedValue() as? [String: Any],
                let current = description[kIOPSCurrentCapacityKey as String] as? NSNumber,
                let maximum = description[kIOPSMaxCapacityKey as String] as? NSNumber,
                maximum.intValue > 0,
                let charging = description[kIOPSIsChargingKey as String] as? Bool
            else {
                continue
            }

            let sourceState = description[kIOPSPowerSourceStateKey as String] as? String
            let acConnected = sourceState.map { $0 == (kIOPSACPowerValue as String) }
            let percentage = Int((Double(current.intValue) / Double(maximum.intValue) * 100).rounded())
            return BatteryReading(
                percentage: min(100, max(0, percentage)),
                charging: charging,
                acConnected: acConnected
            )
        }
        throw AgentError.batteryUnavailable
    }

    private static func post<Body: Encodable, ResponseBody: Decodable>(
        to url: URL,
        body: Body
    ) async throws -> ResponseBody {
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(body)
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse,
              (200..<300).contains(httpResponse.statusCode)
        else {
            throw AgentError.httpRejected((response as? HTTPURLResponse)?.statusCode ?? 0)
        }
        do {
            return try JSONDecoder().decode(ResponseBody.self, from: data)
        } catch {
            throw AgentError.invalidServerResponse
        }
    }

    private static func postAccepted<Body: Encodable>(
        to url: URL,
        body: Body,
        credential: String
    ) async throws {
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(credential)", forHTTPHeaderField: "Authorization")
        request.httpBody = try JSONEncoder().encode(body)
        let (_, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse,
              (200..<300).contains(httpResponse.statusCode)
        else {
            throw AgentError.httpRejected((response as? HTTPURLResponse)?.statusCode ?? 0)
        }
    }

    private static func validatedServerURL(_ value: String) throws -> URL {
        guard let components = URLComponents(string: value),
              let scheme = components.scheme?.lowercased(),
              let host = components.host,
              components.user == nil,
              components.password == nil,
              components.query == nil,
              components.fragment == nil,
              components.path.isEmpty || components.path == "/",
              scheme == "https" || (scheme == "http" && ["localhost", "127.0.0.1"].contains(host))
        else {
            throw AgentError.invalidServerURL
        }
        guard let url = components.url else {
            throw AgentError.invalidServerURL
        }
        return url
    }

    private static func parseOptions(_ arguments: [String]) -> [String: String] {
        var result: [String: String] = [:]
        var index = 0
        while index + 1 < arguments.count {
            result[arguments[index]] = arguments[index + 1]
            index += 2
        }
        return result
    }

    private static var supportDirectory: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/ChargePilot", isDirectory: true)
    }

    private static var configurationURL: URL {
        supportDirectory.appendingPathComponent("agent.json")
    }

    private static func saveConfiguration(_ configuration: LocalConfiguration) throws {
        try FileManager.default.createDirectory(
            at: supportDirectory,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700]
        )
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o700],
            ofItemAtPath: supportDirectory.path
        )
        let data = try JSONEncoder().encode(configuration)
        try data.write(to: configurationURL, options: .atomic)
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o600],
            ofItemAtPath: configurationURL.path
        )
    }

    private static func loadConfiguration() throws -> LocalConfiguration {
        do {
            return try JSONDecoder().decode(
                LocalConfiguration.self,
                from: Data(contentsOf: configurationURL)
            )
        } catch {
            throw AgentError.notEnrolled
        }
    }

    private static func storeCredential(_ credential: String, installationID: UUID) throws {
        let account = installationID.uuidString
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(query as CFDictionary)
        var item = query
        item[kSecValueData as String] = Data(credential.utf8)
        item[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        guard SecItemAdd(item as CFDictionary, nil) == errSecSuccess else {
            throw AgentError.keychainUnavailable
        }
    }

    private static func loadCredential(installationID: UUID) throws -> String {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: installationID.uuidString,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data,
              let credential = String(data: data, encoding: .utf8)
        else {
            throw AgentError.keychainUnavailable
        }
        return credential
    }

    private static func readHiddenLine() throws -> String {
        var original = termios()
        guard tcgetattr(STDIN_FILENO, &original) == 0 else {
            throw AgentError.terminalUnavailable
        }
        var hidden = original
        hidden.c_lflag &= ~tcflag_t(ECHO)
        guard tcsetattr(STDIN_FILENO, TCSANOW, &hidden) == 0 else {
            throw AgentError.terminalUnavailable
        }
        defer {
            tcsetattr(STDIN_FILENO, TCSANOW, &original)
            fputc(10, stderr)
        }
        guard let line = readLine() else {
            throw AgentError.invalidEnrollmentCode
        }
        return line.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

private enum AgentError: LocalizedError {
    case usage
    case invalidServerURL
    case invalidEnrollmentCode
    case invalidServerResponse
    case batteryUnavailable
    case httpRejected(Int)
    case notEnrolled
    case keychainUnavailable
    case terminalUnavailable

    var errorDescription: String? {
        switch self {
        case .usage:
            return "Usage: ChargePilotAgent enroll --server-url URL --label LABEL | ChargePilotAgent run"
        case .invalidServerURL:
            return "Use an HTTPS API origin (HTTP is allowed only for localhost development)."
        case .invalidEnrollmentCode:
            return "The enrollment code is missing."
        case .invalidServerResponse:
            return "The server returned an invalid enrollment response."
        case .batteryUnavailable:
            return "A usable battery reading is unavailable; no sample was sent."
        case let .httpRejected(statusCode):
            return "The server rejected the request with HTTP \(statusCode)."
        case .notEnrolled:
            return "This Mac is not enrolled. Run the enroll command first."
        case .keychainUnavailable:
            return "The per-install credential could not be read from or saved to Keychain."
        case .terminalUnavailable:
            return "Enrollment requires an interactive terminal to hide the one-time code."
        }
    }
}
