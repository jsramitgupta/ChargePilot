import Darwin
import Foundation
import IOKit.ps
import Security

private let agentVersion = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0.1.2"
private let keychainService = "in.chargepilot.telemetry"
private let chargePilotAPIOrigin = "https://api-chargepilot.endusercompute.in"

struct LocalConfiguration: Codable {
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

private struct EmptyRequest: Encodable {}

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
    let systemMetrics: SystemMetrics

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
        case systemMetrics = "system_metrics"
    }
}

struct BatteryReading {
    let percentage: Int
    let charging: Bool
    let acConnected: Bool?
    let reportingIntervalSeconds: Int
}

struct SystemMetrics: Encodable {
    let cpuUsagePercent: Double?
    let gpuUsagePercent: Double?
    let memoryUsedBytes: UInt64?
    let memoryTotalBytes: UInt64?
    let disks: [DiskUsage]

    enum CodingKeys: String, CodingKey {
        case cpuUsagePercent = "cpu_usage_percent"
        case gpuUsagePercent = "gpu_usage_percent"
        case memoryUsedBytes = "memory_used_bytes"
        case memoryTotalBytes = "memory_total_bytes"
        case disks
    }
}

struct DiskUsage: Encodable {
    let name: String
    let usedBytes: UInt64
    let totalBytes: UInt64

    enum CodingKeys: String, CodingKey {
        case name
        case usedBytes = "used_bytes"
        case totalBytes = "total_bytes"
    }
}

private struct TelemetryResponse: Decodable {
    let reportingIntervalSeconds: Int

    enum CodingKeys: String, CodingKey {
        case reportingIntervalSeconds = "reporting_interval_seconds"
    }
}

struct EndpointCommandEnvelope: Decodable {
    let command: ShutdownCommand?
}

struct ShutdownCommand: Decodable {
    let id: UUID
    let operation: String
    let gracePeriodSeconds: Int
    let expiresAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case operation
        case gracePeriodSeconds = "grace_period_seconds"
        case expiresAt = "expires_at"
    }

    func validate() throws {
        guard id.uuidString != "00000000-0000-0000-0000-000000000000",
              operation == "shutdown",
              (30...120).contains(gracePeriodSeconds),
              expiresAt > Date()
        else {
            throw AgentError.invalidServerResponse
        }
    }
}

struct ShutdownAcknowledgement: Encodable {
    let outcome: String
    let error: String?
}

struct SensorClaimEnvelope: Decodable {
    let sensor: SensorClaim?
}

struct SensorClaim: Decodable {
    let id: UUID
    let sensorID: String
    let claimToken: String

    enum CodingKeys: String, CodingKey {
        case id
        case sensorID = "sensor_id"
        case claimToken = "claim_token"
    }

    func validate() throws {
        guard id.uuidString != "00000000-0000-0000-0000-000000000000",
              (32...128).contains(claimToken.count),
              ["os_version", "uptime_seconds", "system_disk_free_bytes"].contains(sensorID)
        else {
            throw AgentError.invalidServerResponse
        }
    }
}

enum SensorValue: Encodable {
    case string(String)
    case integer(Int64)

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case let .string(value):
            try container.encode(value)
        case let .integer(value):
            try container.encode(value)
        }
    }
}

private struct SensorReport: Encodable {
    let claimToken: String
    let value: SensorValue?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case claimToken = "claim_token"
        case value
        case error
    }
}

struct CPUTickSnapshot {
    let user: UInt64
    let system: UInt64
    let idle: UInt64
    let nice: UInt64

    static func fromMachTicks(_ values: [UInt64]) -> Self? {
        guard values.count == 4 else { return nil }
        return Self(user: values[0], system: values[1], idle: values[2], nice: values[3])
    }

    func utilization(since previous: Self) -> Double? {
        let total = (user &- previous.user)
            &+ (system &- previous.system)
            &+ (idle &- previous.idle)
            &+ (nice &- previous.nice)
        guard total > 0 else { return nil }
        let idleDelta = idle &- previous.idle
        return min(100, max(0, Double(total &- idleDelta) / Double(total) * 100))
    }
}

enum SystemMetricsReader {
    static func read() -> SystemMetrics {
        let memory = readMemory()
        return SystemMetrics(
            cpuUsagePercent: readCPUUsage(),
            gpuUsagePercent: nil,
            memoryUsedBytes: memory.used,
            memoryTotalBytes: memory.total,
            disks: readDiskUsage()
        )
    }

    private static func readCPUUsage() -> Double? {
        guard let first = cpuTicks() else { return nil }
        usleep(100_000)
        guard let second = cpuTicks() else { return nil }
        return second.utilization(since: first)
    }

    private static func cpuTicks() -> CPUTickSnapshot? {
        var load = host_cpu_load_info_data_t()
        var count = mach_msg_type_number_t(
            MemoryLayout<host_cpu_load_info_data_t>.stride / MemoryLayout<integer_t>.stride
        )
        let result = withUnsafeMutablePointer(to: &load) { pointer in
            pointer.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                host_statistics(mach_host_self(), HOST_CPU_LOAD_INFO, $0, &count)
            }
        }
        guard result == KERN_SUCCESS else { return nil }
        let values = load.cpu_ticks
        return CPUTickSnapshot.fromMachTicks([
            UInt64(values.0),
            UInt64(values.1),
            UInt64(values.2),
            UInt64(values.3),
        ])
    }

    private static func readMemory() -> (used: UInt64?, total: UInt64?) {
        var statistics = vm_statistics64()
        var count = mach_msg_type_number_t(
            MemoryLayout<vm_statistics64_data_t>.stride / MemoryLayout<integer_t>.stride
        )
        let result = withUnsafeMutablePointer(to: &statistics) { pointer in
            pointer.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                host_statistics64(mach_host_self(), HOST_VM_INFO64, $0, &count)
            }
        }
        guard result == KERN_SUCCESS else { return (nil, nil) }
        let total = ProcessInfo.processInfo.physicalMemory
        let pageSize = UInt64(vm_page_size)
        let available = (UInt64(statistics.free_count) + UInt64(statistics.inactive_count)) * pageSize
        return (total > available ? total - available : 0, total)
    }

    private static func readDiskUsage() -> [DiskUsage] {
        guard let attributes = try? FileManager.default.attributesOfFileSystem(
            forPath: NSHomeDirectory()
        ),
        let total = (attributes[.systemSize] as? NSNumber)?.uint64Value,
        let free = (attributes[.systemFreeSize] as? NSNumber)?.uint64Value,
        total > 0
        else {
            return []
        }
        return [DiskUsage(name: "System volume", usedBytes: total > free ? total - free : 0, totalBytes: total)]
    }
}

@main
struct ChargePilotAgent {
    static func main() async {
        do {
            let arguments = Array(CommandLine.arguments.dropFirst())
            switch arguments.first {
            case nil, "app":
                ChargePilotAgentMenuBar.launch()
            case "help", "--help", "-h":
                print(AgentError.usage.localizedDescription)
            case "enroll":
                try await enroll(arguments: Array(arguments.dropFirst()))
            case "run":
                try await run()
            case "check":
                try checkBattery()
            case "update":
                let updateArguments = Array(arguments.dropFirst())
                do {
                    try AgentUpdater.install(arguments: updateArguments)
                } catch {
                    AgentUpdater.showUpdateError(error, arguments: updateArguments)
                    exit(EXIT_FAILURE)
                }
            case "cleanup":
                try AgentUpdater.cleanup(arguments: Array(arguments.dropFirst()))
            default:
                throw AgentError.usage
            }
        } catch {
            fputs("ChargePilot agent: \(error.localizedDescription)\n", stderr)
            exit(EXIT_FAILURE)
        }
    }

    static func currentConfiguration() throws -> LocalConfiguration? {
        guard FileManager.default.fileExists(atPath: configurationURL.path) else {
            return nil
        }
        do {
            let saved = try JSONDecoder().decode(
                LocalConfiguration.self,
                from: Data(contentsOf: configurationURL)
            )
            return LocalConfiguration(
                serverURL: chargePilotAPIOrigin,
                installationID: saved.installationID,
                label: Host.current().localizedName ?? "Mac"
            )
        } catch {
            throw AgentError.invalidConfiguration
        }
    }

    static func enrollFromUI(code: String) async throws -> LocalConfiguration {
        let serverURL = try validatedServerURL(chargePilotAPIOrigin)
        let cleanLabel = Host.current().localizedName ?? "Mac"
        let cleanCode = code.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleanCode.isEmpty else {
            throw AgentError.invalidEnrollmentCode
        }
        let configuration = LocalConfiguration(
            serverURL: serverURL.absoluteString,
            installationID: UUID(),
            label: cleanLabel
        )
        let response: EnrollmentResponse = try await post(
            to: serverURL.appendingPathComponent("api/v1/endpoint-enrollment/exchange"),
            body: EnrollmentRequest(
                code: cleanCode,
                installationID: configuration.installationID,
                hostname: cleanLabel
            )
        )
        guard response.installationID == configuration.installationID else {
            throw AgentError.invalidServerResponse
        }
        try storeCredential(response.credential, installationID: configuration.installationID)
        try saveConfiguration(configuration)
        return configuration
    }

    static func sendTelemetry(configuration: LocalConfiguration) async throws -> BatteryReading {
        let reading = try readBattery()
        let credential = try loadCredential(installationID: configuration.installationID)
        let serverURL = try validatedServerURL(configuration.serverURL)
        let body = TelemetryRequest(
            hostname: configuration.label,
            installationID: configuration.installationID,
            batteryPercentage: reading.percentage,
            charging: reading.charging,
            acConnected: reading.acConnected,
            timestamp: ISO8601DateFormatter().string(from: Date()),
            agentVersion: agentVersion,
            systemMetrics: SystemMetricsReader.read()
        )
        let responseData = try await postAccepted(
            to: serverURL.appendingPathComponent("api/v1/telemetry"),
            body: body,
            credential: credential
        )
        let response = try JSONDecoder().decode(TelemetryResponse.self, from: responseData)
        guard (300...86_400).contains(response.reportingIntervalSeconds) else {
            throw AgentError.invalidServerResponse
        }
        return BatteryReading(
            percentage: reading.percentage,
            charging: reading.charging,
            acConnected: reading.acConnected,
            reportingIntervalSeconds: response.reportingIntervalSeconds
        )
    }

    static func deregisterFromServer(configuration: LocalConfiguration) async throws {
        let credential = try loadCredential(installationID: configuration.installationID)
        let serverURL = try validatedServerURL(configuration.serverURL)
        _ = try await postAccepted(
            to: serverURL.appendingPathComponent("api/v1/endpoint-enrollment/deregister"),
            body: EmptyRequest(),
            credential: credential
        )
    }

    static func claimShutdownCommand(
        configuration: LocalConfiguration
    ) async throws -> ShutdownCommand? {
        let credential = try loadCredential(installationID: configuration.installationID)
        let serverURL = try validatedServerURL(configuration.serverURL)
        let data = try await postAccepted(
            to: serverURL.appendingPathComponent("api/v1/endpoint-commands/claim"),
            body: EmptyRequest(),
            credential: credential
        )
        let envelope: EndpointCommandEnvelope
        do {
            envelope = try endpointCommandDecoder.decode(
                EndpointCommandEnvelope.self,
                from: data
            )
        } catch {
            throw AgentError.invalidServerResponse
        }
        guard let command = envelope.command else { return nil }
        try command.validate()
        return command
    }

    static func acknowledgeShutdownCommand(
        _ command: ShutdownCommand,
        outcome: String,
        error: String? = nil,
        configuration: LocalConfiguration
    ) async throws {
        guard ["scheduled", "cancelled", "failed"].contains(outcome) else {
            throw AgentError.invalidServerResponse
        }
        let credential = try loadCredential(installationID: configuration.installationID)
        let serverURL = try validatedServerURL(configuration.serverURL)
        _ = try await postAccepted(
            to: serverURL.appendingPathComponent(
                "api/v1/endpoint-commands/\(command.id.uuidString)/acknowledge"
            ),
            body: ShutdownAcknowledgement(outcome: outcome, error: error),
            credential: credential
        )
    }

    static func claimSensorExecution(
        configuration: LocalConfiguration
    ) async throws -> SensorClaim? {
        let credential = try loadCredential(installationID: configuration.installationID)
        let serverURL = try validatedServerURL(configuration.serverURL)
        let data = try await postAccepted(
            to: serverURL.appendingPathComponent("api/v1/endpoint-sensors/claim"),
            body: EmptyRequest(),
            credential: credential
        )
        let envelope: SensorClaimEnvelope
        do {
            envelope = try JSONDecoder().decode(SensorClaimEnvelope.self, from: data)
        } catch {
            throw AgentError.invalidServerResponse
        }
        guard let claim = envelope.sensor else { return nil }
        try claim.validate()
        return claim
    }

    static func reportSensorExecution(
        _ claim: SensorClaim,
        value: SensorValue?,
        error: String? = nil,
        configuration: LocalConfiguration
    ) async throws {
        switch (value, error) {
        case (.some, .none), (.none, .some):
            break
        default:
            throw AgentError.invalidServerResponse
        }
        let credential = try loadCredential(installationID: configuration.installationID)
        let serverURL = try validatedServerURL(configuration.serverURL)
        _ = try await postAccepted(
            to: serverURL.appendingPathComponent(
                "api/v1/endpoint-sensors/\(claim.id.uuidString)/report"
            ),
            body: SensorReport(
                claimToken: claim.claimToken,
                value: value,
                error: error.map { String($0.prefix(255)) }
            ),
            credential: credential
        )
    }

    static func readApprovedSensor(_ sensorID: String) throws -> SensorValue {
        switch sensorID {
        case "os_version":
            return .string(ProcessInfo.processInfo.operatingSystemVersionString)
        case "uptime_seconds":
            return .integer(Int64(max(0, ProcessInfo.processInfo.systemUptime)))
        case "system_disk_free_bytes":
            guard let attributes = try? FileManager.default.attributesOfFileSystem(forPath: "/"),
                  let freeBytes = (attributes[.systemFreeSize] as? NSNumber)?.int64Value,
                  freeBytes >= 0
            else {
                throw AgentError.sensorUnavailable
            }
            return .integer(freeBytes)
        default:
            throw AgentError.invalidServerResponse
        }
    }

    static func requestSystemShutdown() throws {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        process.arguments = [
            "-e",
            "tell application \"System Events\" to shut down",
        ]
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        try process.run()
        process.waitUntilExit()
        guard process.terminationStatus == 0 else {
            throw AgentError.shutdownRejected
        }
    }

    static func clearLocalEnrollment(configuration: LocalConfiguration) throws {
        if FileManager.default.fileExists(atPath: configurationURL.path) {
            try FileManager.default.removeItem(at: configurationURL)
        }
        try deleteCredential(installationID: configuration.installationID)
    }

    private static func enroll(arguments: [String]) async throws {
        guard arguments.isEmpty else {
            throw AgentError.usage
        }
        let label = Host.current().localizedName ?? "Mac"
        let serverURL = try validatedServerURL(chargePilotAPIOrigin)
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

    private static func checkBattery() throws {
        let reading = try readBattery()
        let powerSource = reading.acConnected.map { $0 ? "AC power" : "battery" } ?? "unknown"
        print("Battery: \(reading.percentage)%")
        print("Charging: \(reading.charging ? "yes" : "no")")
        print("Power source: \(powerSource)")
        print("Local check only; no enrollment or network request was performed.")
    }

    private static func run() async throws {
        let configuration = try loadConfiguration()
        while true {
            var intervalSeconds = 300
            do {
                let reading = try await sendTelemetry(configuration: configuration)
                intervalSeconds = reading.reportingIntervalSeconds
                print("Reported battery at \(reading.percentage)% (\(Date())).")
            } catch {
                fputs("Telemetry was not accepted: \(error.localizedDescription)\n", stderr)
            }
            do {
                try await collectOneSensor(configuration: configuration)
            } catch {
                fputs("Sensor collection was not accepted: \(error.localizedDescription)\n", stderr)
            }
            try await Task.sleep(for: .seconds(intervalSeconds))
        }
    }

    private static func collectOneSensor(configuration: LocalConfiguration) async throws {
        guard let claim = try await claimSensorExecution(configuration: configuration) else { return }
        let value: SensorValue
        do {
            value = try readApprovedSensor(claim.sensorID)
        } catch {
            try await reportSensorExecution(
                claim,
                value: nil,
                error: error.localizedDescription,
                configuration: configuration
            )
            return
        }
        try await reportSensorExecution(claim, value: value, configuration: configuration)
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
                acConnected: acConnected,
                reportingIntervalSeconds: 300
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
    ) async throws -> Data {
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(credential)", forHTTPHeaderField: "Authorization")
        request.httpBody = try JSONEncoder().encode(body)
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse,
              (200..<300).contains(httpResponse.statusCode)
        else {
            throw AgentError.httpRejected((response as? HTTPURLResponse)?.statusCode ?? 0)
        }

        return data
    }

    private static let endpointCommandDecoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }()

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
        guard let configuration = try currentConfiguration() else {
            throw AgentError.notEnrolled
        }
        return configuration
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

    private static func deleteCredential(installationID: UUID) throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: installationID.uuidString,
        ]
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw AgentError.keychainUnavailable
        }
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
    case sensorUnavailable
    case shutdownRejected
    case httpRejected(Int)
    case notEnrolled
    case invalidConfiguration
    case keychainUnavailable
    case terminalUnavailable

    var errorDescription: String? {
        switch self {
        case .usage:
            return """
            Usage:
              ChargePilotAgent check
              ChargePilotAgent enroll
              ChargePilotAgent run
            """
        case .invalidServerURL:
            return "Use an HTTPS API origin (HTTP is allowed only for localhost development)."
        case .invalidEnrollmentCode:
            return "The enrollment code is missing."
        case .invalidServerResponse:
            return "The server returned an invalid enrollment response."
        case .batteryUnavailable:
            return "A usable battery reading is unavailable; no sample was sent."
        case .sensorUnavailable:
            return "The requested system sensor is unavailable on this Mac."
        case .shutdownRejected:
            return "macOS did not accept the shutdown request. Check Automation permissions for ChargePilot Agent."
        case let .httpRejected(statusCode):
            return "The server rejected the request with HTTP \(statusCode)."
        case .notEnrolled:
            return "This Mac is not enrolled. Run the enroll command first."
        case .invalidConfiguration:
            return "The saved agent configuration could not be read. Re-enroll this Mac."
        case .keychainUnavailable:
            return "The per-install credential could not be read from or saved to Keychain."
        case .terminalUnavailable:
            return "Enrollment requires an interactive terminal to hide the one-time code."
        }
    }
}
