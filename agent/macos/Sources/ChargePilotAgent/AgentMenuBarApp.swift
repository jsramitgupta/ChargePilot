import AppKit
import ServiceManagement
import SwiftUI

@MainActor
enum ChargePilotAgentMenuBar {
    static func launch() {
        let application = NSApplication.shared
        application.setActivationPolicy(.accessory)
        let delegate = ChargePilotMenuBarDelegate()
        application.delegate = delegate
        application.run()
    }
}

@MainActor
private final class ChargePilotMenuBarDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private let popover = NSPopover()
    private let model = AgentStatusModel()

    func applicationDidFinishLaunching(_ notification: Notification) {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem = item
        item.button?.image = NSImage(
            systemSymbolName: "battery.100percent",
            accessibilityDescription: "ChargePilot"
        )
        item.button?.target = self
        item.button?.action = #selector(togglePopover)
        item.button?.toolTip = "ChargePilot battery telemetry"

        popover.behavior = .transient
        popover.contentSize = NSSize(width: 360, height: 560)
        popover.contentViewController = NSHostingController(
            rootView: AgentMenuView(model: model)
        )
        model.startIfEnrolled()
        model.checkForUpdates()
        if !model.isEnrolled {
            showPopover()
        }
    }

    @objc private func togglePopover() {
        if popover.isShown {
            popover.performClose(nil)
        } else {
            showPopover()
        }
    }

    private func showPopover() {
        guard let button = statusItem.button else { return }
        popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
    }
}

@MainActor
private final class AgentStatusModel: ObservableObject {
    @Published private(set) var configuration: LocalConfiguration?
    @Published var enrollmentCode = ""
    @Published private(set) var isReporting = false
    @Published private(set) var isWorking = false
    @Published private(set) var batteryPercentage: Int?
    @Published private(set) var reportingIntervalSeconds = 300
    @Published private(set) var lastReport: Date?
    @Published private(set) var statusMessage = "Connect this Mac to begin."
    @Published private(set) var statusIsError = false
    @Published private(set) var launchesAtLogin = SMAppService.mainApp.status == .enabled
    @Published var showDeregisterConfirmation = false
    @Published private(set) var latestReleaseVersion: String?
    @Published private(set) var isCheckingForUpdates = false
    @Published private(set) var updateMessage = "Checking for updates…"
    @Published private(set) var updateMessageIsError = false
    @Published private(set) var currentVersion =
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "Unknown"

    private var reportingTask: Task<Void, Never>?

    var isEnrolled: Bool { configuration != nil }
    var updateAvailable: Bool {
        guard let latestReleaseVersion else { return false }
        return AgentUpdater.hasUpdate(current: currentVersion, latest: latestReleaseVersion)
    }
    var canUpdate: Bool {
        Bundle.main.bundleURL.pathExtension == "app" &&
            !Bundle.main.bundleURL.path.hasPrefix("/Volumes/")
    }
    var updateButtonTitle: String {
        updateAvailable ? "Update to \(latestReleaseVersion ?? "")" : "Check for updates"
    }

    init() {
        if !canUpdate {
            updateMessage = "Move the app to Applications before updating."
        }
        do {
            guard let saved = try ChargePilotAgent.currentConfiguration() else { return }
            configuration = saved
            statusMessage = "This Mac is connected to ChargePilot."
        } catch {
            statusMessage = error.localizedDescription
            statusIsError = true
        }
    }

    func startIfEnrolled() {
        guard configuration != nil else { return }
        startReporting()
    }

    func checkForUpdates() {
        guard !isCheckingForUpdates else { return }
        isCheckingForUpdates = true
        updateMessage = "Checking for updates…"
        updateMessageIsError = false
        Task {
            defer { isCheckingForUpdates = false }
            do {
                let release = try await AgentUpdater.latestRelease()
                latestReleaseVersion = release.version
                if !canUpdate {
                    updateMessage = "Move the app to Applications before updating."
                } else {
                    updateMessage = updateAvailable
                        ? "Version \(release.version) is available."
                        : "You’re up to date."
                }
            } catch {
                updateMessage = "Could not check for updates: \(error.localizedDescription)"
                updateMessageIsError = true
            }
        }
    }

    func updateAgent() {
        guard !isWorking, canUpdate else { return }
        isWorking = true
        Task {
            defer { isWorking = false }
            do {
                let release = try await AgentUpdater.latestRelease()
                latestReleaseVersion = release.version
                guard AgentUpdater.hasUpdate(current: currentVersion, latest: release.version) else {
                    updateMessage = "You’re up to date."
                    updateMessageIsError = false
                    return
                }

                let alert = NSAlert()
                alert.messageText = "Update ChargePilot Agent?"
                alert.informativeText =
                    "Install version \(release.version). ChargePilot will quit and reopen after the update. The release may be unsigned; macOS security checks remain in effect."
                alert.addButton(withTitle: "Update")
                alert.addButton(withTitle: "Cancel")
                guard alert.runModal() == .alertFirstButtonReturn else { return }

                updateMessage = "Downloading version \(release.version)…"
                updateMessageIsError = false
                try await AgentUpdater.downloadAndStartUpdate(
                    release: release,
                    targetApp: Bundle.main.bundleURL
                )
                NSApplication.shared.terminate(nil)
            } catch {
                updateMessage = "Could not update the app: \(error.localizedDescription)"
                updateMessageIsError = true
            }
        }
    }

    func enroll() {
        guard !isWorking else { return }
        isWorking = true
        statusMessage = "Connecting to ChargePilot…"
        statusIsError = false
        let code = enrollmentCode
        Task {
            defer { isWorking = false }
            do {
                let saved = try await ChargePilotAgent.enrollFromUI(
                    code: code
                )
                configuration = saved
                enrollmentCode = ""
                statusMessage = "This Mac is connected. Sending its first report…"
                startReporting()
            } catch {
                statusMessage = error.localizedDescription
                statusIsError = true
            }
        }
    }

    func startReporting() {
        guard !isReporting, let configuration else { return }
        isReporting = true
        reportingTask = Task {
            while !Task.isCancelled {
                await sendReport(configuration: configuration)
                do {
                    try await Task.sleep(for: .seconds(reportingIntervalSeconds))
                } catch {
                    break
                }
            }
        }
    }

    func stopReporting() {
        reportingTask?.cancel()
        reportingTask = nil
        isReporting = false
        statusMessage = "Reporting is paused."
        statusIsError = false
    }

    func sendReportNow() {
        guard let configuration, !isWorking else { return }
        Task {
            await sendReport(configuration: configuration)
        }
    }

    func deregister() {
        guard !isWorking, let configuration else { return }
        let wasReporting = isReporting
        reportingTask?.cancel()
        reportingTask = nil
        isReporting = false
        isWorking = true
        statusMessage = "Deregistering this Mac…"
        statusIsError = false
        Task {
            defer { isWorking = false }
            do {
                try await ChargePilotAgent.deregisterFromServer(configuration: configuration)
                self.configuration = nil
                lastReport = nil
                batteryPercentage = nil
                do {
                    try ChargePilotAgent.clearLocalEnrollment(configuration: configuration)
                    statusMessage = "Mac deregistered. Enter a new enrollment token to connect again."
                    statusIsError = false
                } catch {
                    statusMessage = "Mac deregistered, but local credential cleanup failed: \(error.localizedDescription)"
                    statusIsError = true
                }
            } catch {
                statusMessage = error.localizedDescription
                statusIsError = true
                if wasReporting {
                    startReporting()
                }
            }
        }
    }

    func setLaunchAtLogin(_ enabled: Bool) {
        do {
            if enabled {
                try SMAppService.mainApp.register()
            } else {
                try SMAppService.mainApp.unregister()
            }
            launchesAtLogin = SMAppService.mainApp.status == .enabled
            statusMessage = launchesAtLogin
                ? "ChargePilot will open when you sign in."
                : "ChargePilot will not open automatically."
            statusIsError = false
        } catch {
            launchesAtLogin = SMAppService.mainApp.status == .enabled
            statusMessage = "Could not update the login setting: \(error.localizedDescription)"
            statusIsError = true
        }
    }

    private func sendReport(configuration: LocalConfiguration) async {
        guard !isWorking else { return }
        isWorking = true
        defer { isWorking = false }
        do {
            let reading = try await ChargePilotAgent.sendTelemetry(configuration: configuration)
            batteryPercentage = reading.percentage
            reportingIntervalSeconds = reading.reportingIntervalSeconds
            lastReport = Date()
            statusMessage = "Last report accepted by ChargePilot."
            statusIsError = false
        } catch {
            statusMessage = error.localizedDescription
            statusIsError = true
        }
    }
}

@MainActor
private struct AgentMenuView: View {
    @ObservedObject var model: AgentStatusModel

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            updateRow
            Divider().padding(.vertical, 16)
            if model.isEnrolled {
                connectedContent
            } else {
                setupContent
            }
            Spacer(minLength: 12)
            statusLine
            Divider().padding(.top, 12)
            footer
        }
        .padding(20)
        .frame(width: 360, height: 560, alignment: .topLeading)
        .background(Color(nsColor: .windowBackgroundColor))
        .task { model.startIfEnrolled() }
        .confirmationDialog(
            "Deregister this Mac?",
            isPresented: $model.showDeregisterConfirmation,
            titleVisibility: .visible
        ) {
            Button("Deregister", role: .destructive) {
                model.deregister()
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("This revokes the installation and stops its reports. You can enroll again here with a new workspace token.")
        }
    }

    private var updateRow: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("Version \(model.currentVersion)")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(.secondary)
                Spacer()
                Button(model.updateButtonTitle) {
                    model.updateAgent()
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(model.isWorking || model.isCheckingForUpdates || !model.canUpdate)
            }
            Text(model.updateMessage)
                .font(.system(size: 10))
                .foregroundStyle(model.updateMessageIsError ? Color.red : Color.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.top, 12)
    }

    private var header: some View {
        HStack(spacing: 12) {
            Image(systemName: "battery.100percent")
                .font(.system(size: 22, weight: .medium))
                .foregroundStyle(Color(red: 0.10, green: 0.58, blue: 0.48))
                .frame(width: 42, height: 42)
                .background(Color(red: 0.10, green: 0.58, blue: 0.48).opacity(0.12))
                .clipShape(RoundedRectangle(cornerRadius: 11))
            VStack(alignment: .leading, spacing: 3) {
                Text("ChargePilot")
                    .font(.system(size: 18, weight: .semibold))
                Text("Mac battery agent")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if model.isEnrolled {
                Circle()
                    .fill(model.isReporting ? Color.green : Color.orange)
                    .frame(width: 8, height: 8)
                Text(model.isReporting ? "Active" : "Paused")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var connectedContent: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                Text(model.batteryPercentage.map(String.init) ?? "—")
                    .font(.system(size: 48, weight: .light, design: .rounded))
                    .contentTransition(.numericText())
                if model.batteryPercentage != nil {
                    Text("%")
                        .font(.system(size: 20, weight: .regular))
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Image(systemName: "bolt.fill")
                    .font(.system(size: 14))
                    .foregroundStyle(Color(red: 0.10, green: 0.58, blue: 0.48))
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel("Battery \(model.batteryPercentage.map { "\($0) percent" } ?? "reading unavailable")")

            VStack(alignment: .leading, spacing: 5) {
                Text(model.configuration?.label ?? "")
                    .font(.system(size: 14, weight: .medium))
                Text(model.configuration?.serverURL ?? "")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }

            HStack(spacing: 10) {
                Button(model.isReporting ? "Pause reports" : "Resume reports") {
                    model.isReporting ? model.stopReporting() : model.startReporting()
                }
                .buttonStyle(.borderedProminent)
                .tint(Color(red: 0.10, green: 0.48, blue: 0.41))
                Button("Send now") {
                    model.sendReportNow()
                }
                .buttonStyle(.bordered)
                .disabled(model.isWorking)
            }

            Toggle("Open when I sign in", isOn: Binding(
                get: { model.launchesAtLogin },
                set: { model.setLaunchAtLogin($0) }
            ))
            .font(.system(size: 12))
            .toggleStyle(.switch)
            .controlSize(.small)

            Button("Deregister this Mac", role: .destructive) {
                model.showDeregisterConfirmation = true
            }
            .disabled(model.isWorking)

            if let lastReport = model.lastReport {
                Text("Last accepted \(lastReport.formatted(date: .abbreviated, time: .shortened))")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var setupContent: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Connect this Mac")
                .font(.system(size: 20, weight: .semibold))
            Text("Use an enrollment code from ChargePilot’s Set up a device page. The code is used once and is not saved here.")
                .font(.system(size: 12))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            VStack(alignment: .leading, spacing: 8) {
                Text("Server: https://api-chargepilot.endusercompute.in")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
                Text("This Mac’s computer name is used. Serial numbers are not collected.")
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)

                Text("Enrollment code")
                    .font(.system(size: 12, weight: .medium))
                SecureField("Paste the one-time code", text: $model.enrollmentCode)
                    .textFieldStyle(.roundedBorder)
            }

            Button {
                model.enroll()
            } label: {
                HStack {
                    Spacer()
                    if model.isWorking {
                        ProgressView().controlSize(.small)
                        Text("Connecting…")
                    } else {
                        Text("Connect this Mac")
                    }
                    Spacer()
                }
            }
            .buttonStyle(.borderedProminent)
            .tint(Color(red: 0.10, green: 0.48, blue: 0.41))
            .disabled(model.isWorking || model.enrollmentCode.isEmpty)
        }
    }

    private var statusLine: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: model.statusIsError ? "exclamationmark.circle.fill" : "checkmark.circle.fill")
                .foregroundStyle(model.statusIsError ? Color.red : Color(red: 0.10, green: 0.58, blue: 0.48))
            Text(model.statusMessage)
                .font(.system(size: 11))
                .foregroundStyle(model.statusIsError ? Color.red : Color.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var footer: some View {
        HStack {
            Text("Reports every 5 minutes while awake")
                .font(.system(size: 10))
                .foregroundStyle(.secondary)
            Spacer()
            Button("Quit") {
                NSApplication.shared.terminate(nil)
            }
            .buttonStyle(.plain)
            .font(.system(size: 11, weight: .medium))
        }
        .padding(.top, 10)
    }
}
