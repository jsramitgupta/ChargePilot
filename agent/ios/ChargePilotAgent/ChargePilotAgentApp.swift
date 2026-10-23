import Foundation
import Combine
import AppIntents
import Security
import SwiftUI
import UIKit

@main
struct ChargePilotAgentApp: App {
    @StateObject private var model = AgentModel()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            AgentHomeView(model: model)
                .preferredColorScheme(.light)
                .onAppear {
                    if model.isEnrolled {
                        Task { await model.sendReading() }
                    }
                }
                .onChange(of: scenePhase) { phase in
                    if phase == .active, model.isEnrolled {
                        Task { await model.sendReading() }
                    }
                }
        }
    }
}

struct ReportBatteryTelemetryIntent: AppIntent {
    static var title: LocalizedStringResource = "Report battery to ChargePilot"
    static var description = IntentDescription(
        "Send a fresh battery and charging reading to ChargePilot."
    )
    static var openAppWhenRun = false
    static var authenticationPolicy: IntentAuthenticationPolicy = .alwaysAllowed

    func perform() async throws -> some IntentResult {
        do {
            try await ShortcutTelemetryReporter.sendFreshReading()
            return .result(dialog: "Fresh battery reading sent to ChargePilot.")
        } catch {
            UserDefaults.standard.set(error.localizedDescription, forKey: "lastError")
            throw error
        }
    }
}

struct ChargePilotAppShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: ReportBatteryTelemetryIntent(),
            phrases: [
                "Report battery to \(.applicationName)",
                "Send a battery reading to \(.applicationName)"
            ],
            shortTitle: "Report battery",
            systemImageName: "battery.100percent"
        )
    }
}

@MainActor
final class AgentModel: ObservableObject {
    @Published var serverOrigin: String
    @Published var deviceLabel: String
    @Published var enrollmentToken = ""
    @Published private(set) var endpointID: String?
    @Published private(set) var batteryReading: BatteryReading?
    @Published private(set) var lastSuccessfulReport: Date?
    @Published private(set) var lastError: String?
    @Published private(set) var statusMessage: String?
    @Published private(set) var isWorking = false
    @Published var showDeregisterConfirmation = false

    private let defaults = UserDefaults.standard
    private let credentialStore = KeychainCredentialStore()
    private var installationID: UUID?

    init() {
        serverOrigin = defaults.string(forKey: "serverOrigin") ?? "https://api-chargepilot.endusercompute.in"
        deviceLabel = defaults.string(forKey: "deviceLabel")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .flatMap { $0.isEmpty ? nil : $0 }
            ?? UIDevice.current.model
        endpointID = defaults.string(forKey: "endpointID")
        if let value = defaults.string(forKey: "installationID") {
            installationID = UUID(uuidString: value)
        }
        lastSuccessfulReport = defaults.object(forKey: "lastSuccessfulReport") as? Date
        lastError = defaults.string(forKey: "lastError")
        refreshBatteryReading()
    }

    var isEnrolled: Bool {
        endpointID != nil && installationID != nil
    }

    func enroll() async {
        guard !isWorking else { return }
        let label = deviceLabel.trimmingCharacters(in: .whitespacesAndNewlines)
        let token = enrollmentToken.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !label.isEmpty, !token.isEmpty else {
            statusMessage = "Enter a device label and enrollment token."
            lastError = statusMessage
            return
        }
        do {
            let origin = try validatedOrigin(serverOrigin)
            isWorking = true
            statusMessage = "Enrolling this device…"
            lastError = nil
            enrollmentToken = ""

            let identity = UUID()
            let response = try await AgentAPI.exchangeEnrollment(
                origin: origin,
                token: token,
                installationID: identity,
                label: label,
                deviceClass: UIDevice.current.userInterfaceIdiom == .pad ? "tablet" : "phone"
            )
            guard response.installationID == identity else {
                throw AgentError.invalidResponse
            }
            try credentialStore.save(response.credential, account: identity.uuidString)
            installationID = identity
            endpointID = response.endpointID.uuidString
            deviceLabel = label
            serverOrigin = origin.absoluteString
            defaults.set(serverOrigin, forKey: "serverOrigin")
            defaults.set(deviceLabel, forKey: "deviceLabel")
            defaults.set(endpointID, forKey: "endpointID")
            defaults.set(identity.uuidString, forKey: "installationID")
            statusMessage = "Device enrolled. Sending its first reading."
            isWorking = false
            await sendReading()
        } catch {
            statusMessage = error.localizedDescription
            lastError = error.localizedDescription
            defaults.set(lastError, forKey: "lastError")
        }
        isWorking = false
    }

    func sendReading() async {
        guard !isWorking else { return }
        guard endpointID != nil, let installationID else {
            statusMessage = "Enroll this device before sending a reading."
            return
        }
        do {
            let origin = try validatedOrigin(serverOrigin)
            refreshBatteryReading()
            guard let batteryReading else {
                throw AgentError.batteryUnavailable
            }
            let credential = try credentialStore.load(account: installationID.uuidString)
            isWorking = true
            statusMessage = "Sending a fresh battery reading…"
            lastError = nil
            try await AgentAPI.sendTelemetry(
                origin: origin,
                credential: credential,
                installationID: installationID,
                label: deviceLabel,
                deviceClass: UIDevice.current.userInterfaceIdiom == .pad ? "tablet" : "phone",
                reading: batteryReading
            )
            let now = Date()
            lastSuccessfulReport = now
            statusMessage = "Reading sent to ChargePilot."
            defaults.set(now, forKey: "lastSuccessfulReport")
            defaults.removeObject(forKey: "lastError")
        } catch {
            statusMessage = error.localizedDescription
            lastError = error.localizedDescription
            defaults.set(lastError, forKey: "lastError")
        }
        isWorking = false
    }

    func deregister() async {
        guard !isWorking, let installationID, endpointID != nil else { return }
        isWorking = true
        statusMessage = "Deregistering this device…"
        lastError = nil
        do {
            let origin = try validatedOrigin(serverOrigin)
            let credential = try credentialStore.load(account: installationID.uuidString)
            try await AgentAPI.deregister(origin: origin, credential: credential)
            self.installationID = nil
            endpointID = nil
            defaults.removeObject(forKey: "endpointID")
            defaults.removeObject(forKey: "installationID")
            defaults.removeObject(forKey: "lastSuccessfulReport")
            defaults.removeObject(forKey: "lastError")
            lastSuccessfulReport = nil
            do {
                try credentialStore.delete(account: installationID.uuidString)
                statusMessage = "Device deregistered. Enter a new enrollment token to connect again."
            } catch {
                statusMessage = "Device deregistered, but local credential cleanup failed: \(error.localizedDescription)"
                lastError = statusMessage
                defaults.set(lastError, forKey: "lastError")
            }
        } catch {
            statusMessage = error.localizedDescription
            lastError = error.localizedDescription
            defaults.set(lastError, forKey: "lastError")
        }
        isWorking = false
    }

    func refreshBatteryReading() {
        batteryReading = try? BatteryStateReader.read()
    }

    private func validatedOrigin(_ value: String) throws -> URL {
        try APIOrigin.validate(value)
    }
}

private struct AgentHomeView: View {
    @ObservedObject var model: AgentModel

    private let pine = Color(red: 0.14, green: 0.30, blue: 0.23)
    private let leaf = Color(red: 0.30, green: 0.50, blue: 0.38)
    private let copper = Color(red: 0.74, green: 0.44, blue: 0.31)
    private let ink = Color(red: 0.11, green: 0.19, blue: 0.15)
    private let muted = Color(red: 0.39, green: 0.45, blue: 0.41)

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("ChargePilot")
                        .font(.system(size: 29, weight: .bold, design: .rounded))
                        .foregroundStyle(pine)
                    Text("Battery telemetry")
                        .font(.system(size: 15))
                        .foregroundStyle(muted)
                }

                if model.isEnrolled {
                    enrolledContent
                } else {
                    enrollmentForm
                }

                Text("Automation is enabled by default. ChargePilot checks fresh reports, platform policy, and device mappings before controlling a switch.")
                    .font(.system(size: 13))
                    .foregroundStyle(muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.horizontal, 24)
            .padding(.top, 28)
            .padding(.bottom, 36)
            .frame(maxWidth: 560, alignment: .leading)
            .frame(maxWidth: .infinity)
        }
        .background(Color(red: 0.95, green: 0.97, blue: 0.94).ignoresSafeArea())
        .tint(leaf)
        .confirmationDialog(
            "Deregister this device?",
            isPresented: $model.showDeregisterConfirmation,
            titleVisibility: .visible
        ) {
            Button("Deregister", role: .destructive) {
                Task { await model.deregister() }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("This revokes the installation and stops its reports. You can enroll again here with a new workspace token.")
        }
    }

    private var enrollmentForm: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Connect this device")
                .font(.system(size: 23, weight: .semibold))
                .foregroundStyle(ink)
            Text("Use a workspace enrollment token. It expires after 24 hours and can enroll multiple devices.")
                .font(.system(size: 15))
                .foregroundStyle(muted)
                .fixedSize(horizontal: false, vertical: true)

            if let status = model.statusMessage {
                notice(status, isError: model.lastError != nil)
            }

            TextField("ChargePilot API origin", text: $model.serverOrigin)
                .textContentType(.URL)
                .keyboardType(.URL)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .textFieldStyle(.roundedBorder)

            TextField("Device label", text: $model.deviceLabel, prompt: Text("iPhone or iPad"))
                .textFieldStyle(.roundedBorder)
            Text("Uses the generic device type, not a serial number. You can change the label in the admin console.")
                .font(.system(size: 12))
                .foregroundStyle(muted)

            SecureField("24-hour enrollment token", text: $model.enrollmentToken)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .textFieldStyle(.roundedBorder)

            actionButton("Enroll this device", color: pine) {
                Task { await model.enroll() }
            }
        }
        .padding(20)
        .background(.white.opacity(0.84), in: RoundedRectangle(cornerRadius: 18))
    }

    private var enrolledContent: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .center) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(model.deviceLabel)
                        .font(.system(size: 22, weight: .semibold))
                        .foregroundStyle(ink)
                    if let endpointID = model.endpointID {
                        Text("Endpoint \(endpointID.prefix(8))")
                            .font(.system(size: 12))
                            .foregroundStyle(muted)
                    }
                    Text("iOS · enrolled")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundStyle(leaf)
                }
                Spacer()
                Button("Refresh") { model.refreshBatteryReading() }
                    .font(.system(size: 14, weight: .semibold))
            }

            VStack(alignment: .leading, spacing: 14) {
                Text("Current battery")
                    .font(.system(size: 14))
                    .foregroundStyle(Color.white.opacity(0.76))
                HStack(alignment: .lastTextBaseline, spacing: 7) {
                    Text(model.batteryReading.map { "\($0.percentage)" } ?? "—")
                        .font(.system(size: 58, weight: .light, design: .rounded))
                    Text("%")
                        .font(.system(size: 23, weight: .regular))
                        .foregroundStyle(Color.white.opacity(0.76))
                    Spacer()
                    Text(batteryDescription)
                        .font(.system(size: 14, weight: .medium))
                }
                .foregroundStyle(.white)

                GeometryReader { geometry in
                    ZStack(alignment: .leading) {
                        Capsule().fill(Color.white.opacity(0.18))
                        Capsule()
                            .fill(copper)
                            .frame(width: geometry.size.width * CGFloat(model.batteryReading?.percentage ?? 0) / 100)
                    }
                }
                .frame(height: 8)
            }
            .padding(22)
            .background(pine, in: RoundedRectangle(cornerRadius: 20))

            VStack(alignment: .leading, spacing: 5) {
                Text("Last successful report")
                    .font(.system(size: 13))
                    .foregroundStyle(muted)
                Text(model.lastSuccessfulReport.map(Self.timestamp) ?? "No report yet")
                    .font(.system(size: 16, weight: .medium))
                    .foregroundStyle(ink)
            }

            if let error = model.lastError {
                notice(error, isError: true)
            } else if let status = model.statusMessage {
                notice(status, isError: false)
            }

            actionButton("Send reading now", color: leaf) {
                Task { await model.sendReading() }
            }

            Button("Deregister this device", role: .destructive) {
                model.showDeregisterConfirmation = true
            }
            .disabled(model.isWorking)

            Text("Shortcuts can request a fresh report on battery-level or charger events. iOS may delay or skip background actions, so switch control is not guaranteed at an exact percentage.")
                .font(.system(size: 13))
                .foregroundStyle(muted)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var batteryDescription: String {
        guard let reading = model.batteryReading else { return "Reading unavailable" }
        return reading.charging ? "Charging" : "On battery"
    }

    @ViewBuilder
    private func actionButton(_ title: String, color: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 10) {
                if model.isWorking {
                    ProgressView().tint(.white)
                }
                Text(model.isWorking ? "Working…" : title)
                    .font(.system(size: 16, weight: .semibold))
            }
            .frame(maxWidth: .infinity)
            .frame(height: 52)
            .foregroundStyle(.white)
            .background(color, in: RoundedRectangle(cornerRadius: 12))
        }
        .disabled(model.isWorking)
    }

    private func notice(_ text: String, isError: Bool) -> some View {
        Text(text)
            .font(.system(size: 14))
            .foregroundStyle(isError ? Color(red: 0.57, green: 0.20, blue: 0.17) : pine)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(13)
            .background(
                isError ? Color(red: 0.99, green: 0.92, blue: 0.89) : Color(red: 0.89, green: 0.93, blue: 0.88),
                in: RoundedRectangle(cornerRadius: 10)
            )
    }

    private static func timestamp(_ date: Date) -> String {
        date.formatted(date: .abbreviated, time: .shortened)
    }
}

struct BatteryReading {
    let percentage: Int
    let charging: Bool
}

private struct EnrollmentRequest: Encodable {
    let code: String
    let platform = "ios"
    let installationID: UUID
    let hostname: String
    let deviceClass: String

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
    let platform = "ios"
    let deviceClass: String
    let batteryPercentage: Int
    let charging: Bool
    let timestamp: String
    let agentVersion = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0.1.2"

    enum CodingKeys: String, CodingKey {
        case hostname
        case installationID = "installation_id"
        case platform
        case deviceClass = "device_class"
        case batteryPercentage = "battery_percentage"
        case charging
        case timestamp
        case agentVersion = "agent_version"
    }
}

@MainActor
private enum ShortcutTelemetryReporter {
    static func sendFreshReading() async throws {
        let defaults = UserDefaults.standard
        guard
            let endpointID = defaults.string(forKey: "endpointID"),
            !endpointID.isEmpty,
            let installationValue = defaults.string(forKey: "installationID"),
            let installationID = UUID(uuidString: installationValue),
            let label = defaults.string(forKey: "deviceLabel"),
            !label.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
            let serverOrigin = defaults.string(forKey: "serverOrigin")
        else {
            throw AgentError.notEnrolled
        }

        let origin = try APIOrigin.validate(serverOrigin)
        let reading = try BatteryStateReader.read()
        let credential = try KeychainCredentialStore().load(account: installationID.uuidString)
        let deviceClass = UIDevice.current.userInterfaceIdiom == .pad ? "tablet" : "phone"
        try await AgentAPI.sendTelemetry(
            origin: origin,
            credential: credential,
            installationID: installationID,
            label: label,
            deviceClass: deviceClass,
            reading: reading
        )

        let now = Date()
        defaults.set(now, forKey: "lastSuccessfulReport")
        defaults.removeObject(forKey: "lastError")
    }
}

private enum AgentAPI {
    static func exchangeEnrollment(
        origin: URL,
        token: String,
        installationID: UUID,
        label: String,
        deviceClass: String
    ) async throws -> EnrollmentResponse {
        let body = EnrollmentRequest(
            code: token,
            installationID: installationID,
            hostname: label,
            deviceClass: deviceClass
        )
        return try await post(
            origin: origin,
            path: ["api", "v1", "endpoint-enrollment", "exchange"],
            body: body,
            expected: EnrollmentResponse.self
        )
    }

    static func sendTelemetry(
        origin: URL,
        credential: String,
        installationID: UUID,
        label: String,
        deviceClass: String,
        reading: BatteryReading
    ) async throws {
        let formatter = ISO8601DateFormatter()
        let body = TelemetryRequest(
            hostname: label,
            installationID: installationID,
            deviceClass: deviceClass,
            batteryPercentage: reading.percentage,
            charging: reading.charging,
            timestamp: formatter.string(from: Date())
        )
        var request = try makeRequest(
            origin: origin,
            path: ["api", "v1", "telemetry"],
            body: body
        )
        request.setValue("Bearer \(credential)", forHTTPHeaderField: "Authorization")
        try await send(request)
    }

    static func deregister(origin: URL, credential: String) async throws {
        var request = try makeRequest(
            origin: origin,
            path: ["api", "v1", "endpoint-enrollment", "deregister"],
            body: EmptyRequest()
        )
        request.setValue("Bearer \(credential)", forHTTPHeaderField: "Authorization")
        try await send(request)
    }

    private static func post<ResponseBody: Decodable, Body: Encodable>(
        origin: URL,
        path: [String],
        body: Body,
        expected: ResponseBody.Type
    ) async throws -> ResponseBody {
        let request = try makeRequest(origin: origin, path: path, body: body)
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw AgentError.invalidResponse
        }
        guard (200..<300).contains(http.statusCode) else {
            throw AgentError.requestRejected(http.statusCode)
        }
        do {
            return try JSONDecoder().decode(expected, from: data)
        } catch {
            throw AgentError.invalidResponse
        }
    }

    private static func makeRequest<Body: Encodable>(
        origin: URL,
        path: [String],
        body: Body
    ) throws -> URLRequest {
        let url = path.reduce(origin) { $0.appendingPathComponent($1) }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 15
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(body)
        return request
    }

    private static func send(_ request: URLRequest) async throws {
        let (_, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw AgentError.invalidResponse
        }
        guard (200..<300).contains(http.statusCode) else {
            throw AgentError.requestRejected(http.statusCode)
        }
    }
}

private enum APIOrigin {
    static func validate(_ value: String) throws -> URL {
        guard
            let components = URLComponents(
                string: value.trimmingCharacters(in: .whitespacesAndNewlines)
            ),
            let scheme = components.scheme?.lowercased(),
            let host = components.host?.lowercased(),
            components.path.isEmpty || components.path == "/",
            components.query == nil,
            components.fragment == nil,
            scheme == "https",
            let url = components.url
        else {
            throw AgentError.invalidOrigin
        }
        return url
    }
}

@MainActor
private enum BatteryStateReader {
    static func read() throws -> BatteryReading {
        UIDevice.current.isBatteryMonitoringEnabled = true
        let level = UIDevice.current.batteryLevel
        let state = UIDevice.current.batteryState
        guard level >= 0, state != .unknown else {
            throw AgentError.batteryUnavailable
        }
        return BatteryReading(
            percentage: min(100, max(0, Int((level * 100).rounded()))),
            charging: state == .charging
        )
    }
}

private struct KeychainCredentialStore {
    private let service = "in.chargepilot.telemetry.ios"

    func save(_ credential: String, account: String) throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(query as CFDictionary)
        var item = query
        item[kSecValueData as String] = Data(credential.utf8)
        item[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        guard SecItemAdd(item as CFDictionary, nil) == errSecSuccess else {
            throw AgentError.keychainUnavailable
        }
    }

    func load(account: String) throws -> String {
        let identity: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        var query = identity
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        guard
            SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
            let data = result as? Data,
            let credential = String(data: data, encoding: .utf8)
        else {
            throw AgentError.keychainUnavailable
        }
        let update = [
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        ] as CFDictionary
        guard SecItemUpdate(identity as CFDictionary, update) == errSecSuccess else {
            throw AgentError.keychainUnavailable
        }
        return credential
    }

    func delete(account: String) throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw AgentError.keychainUnavailable
        }
    }
}

private enum AgentError: LocalizedError {
    case invalidOrigin
    case invalidResponse
    case requestRejected(Int)
    case batteryUnavailable
    case keychainUnavailable
    case notEnrolled

    var errorDescription: String? {
        switch self {
        case .invalidOrigin:
            return "Use an HTTPS API origin without a path, query, or fragment."
        case .invalidResponse:
            return "ChargePilot returned an invalid response."
        case .requestRejected(let status):
            return "ChargePilot rejected the request (HTTP \(status)). Check the token, server, or endpoint credential."
        case .batteryUnavailable:
            return "A usable battery reading is unavailable; no sample was sent."
        case .keychainUnavailable:
            return "The per-install credential could not be read or prepared for background access. Open ChargePilot after unlocking; if the problem persists, revoke this endpoint before enrolling again."
        case .notEnrolled:
            return "Open ChargePilot and enroll this device before using the battery shortcut."
        }
    }
}
