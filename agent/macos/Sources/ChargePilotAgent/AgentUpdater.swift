import AppKit
import Darwin
import Foundation

struct AgentReleaseInfo {
    let version: String
    let downloadURL: URL
}

enum AgentUpdater {
    private static let releaseAPI = URL(string: "https://api.github.com/repos/jsramitgupta/ChargePilot/releases/latest")!

    private struct ReleaseResponse: Decodable {
        let tagName: String
        let assets: [ReleaseAsset]

        enum CodingKeys: String, CodingKey {
            case tagName = "tag_name"
            case assets
        }
    }

    private struct ReleaseAsset: Decodable {
        let name: String
        let browserDownloadURL: URL

        enum CodingKeys: String, CodingKey {
            case name
            case browserDownloadURL = "browser_download_url"
        }
    }

    static func latestRelease() async throws -> AgentReleaseInfo {
        var request = URLRequest(url: releaseAPI)
        request.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
        request.setValue("ChargePilotAgentUpdater", forHTTPHeaderField: "User-Agent")
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse,
              (200..<300).contains(httpResponse.statusCode)
        else {
            throw AgentUpdateError.releaseLookupFailed((response as? HTTPURLResponse)?.statusCode ?? 0)
        }

        let release = try JSONDecoder().decode(ReleaseResponse.self, from: data)
        guard release.tagName.hasPrefix("agents-v") else {
            throw AgentUpdateError.invalidRelease
        }
        let version = String(release.tagName.dropFirst("agents-v".count))
        guard versionParts(version) != nil,
              let asset = release.assets.first(where: { $0.name == "ChargePilotAgent-\(version).dmg" }),
              asset.browserDownloadURL.scheme == "https",
              asset.browserDownloadURL.host == "github.com"
        else {
            throw AgentUpdateError.invalidRelease
        }
        return AgentReleaseInfo(version: version, downloadURL: asset.browserDownloadURL)
    }

    static func hasUpdate(current: String, latest: String) -> Bool {
        guard let currentParts = versionParts(current),
              let latestParts = versionParts(latest)
        else {
            return false
        }
        return currentParts.lexicographicallyPrecedes(latestParts)
    }

    static func downloadAndStartUpdate(release: AgentReleaseInfo, targetApp: URL) async throws {
        let fileManager = FileManager.default
        let root = fileManager.temporaryDirectory
            .appendingPathComponent("ChargePilotAgent-update-\(UUID().uuidString)", isDirectory: true)
        let mount = root.appendingPathComponent("volume", isDirectory: true)
        try fileManager.createDirectory(at: mount, withIntermediateDirectories: true)

        do {
            let (download, response) = try await URLSession.shared.download(from: release.downloadURL)
            guard let httpResponse = response as? HTTPURLResponse,
                  (200..<300).contains(httpResponse.statusCode)
            else {
                throw AgentUpdateError.downloadFailed((response as? HTTPURLResponse)?.statusCode ?? 0)
            }

            let diskImage = root.appendingPathComponent("ChargePilotAgent.dmg")
            try fileManager.moveItem(at: download, to: diskImage)
            try run("/usr/bin/hdiutil", arguments: ["verify", diskImage.path])
            try run("/usr/bin/hdiutil", arguments: [
                "attach", "-nobrowse", "-readonly", "-mountpoint", mount.path, diskImage.path,
            ])

            let sourceApp = mount.appendingPathComponent("ChargePilotAgent.app", isDirectory: true)
            guard let sourceVersion = Bundle(url: sourceApp)?.infoDictionary?["CFBundleShortVersionString"] as? String,
                  sourceVersion == release.version,
                  fileManager.fileExists(
                    atPath: sourceApp.appendingPathComponent("Contents/MacOS/ChargePilotAgent").path
                  )
            else {
                throw AgentUpdateError.invalidRelease
            }

            let updaterExecutable = root.appendingPathComponent("ChargePilotAgentUpdater")
            try fileManager.copyItem(
                at: sourceApp.appendingPathComponent("Contents/MacOS/ChargePilotAgent"),
                to: updaterExecutable
            )
            try fileManager.setAttributes([.posixPermissions: 0o755], ofItemAtPath: updaterExecutable.path)

            let process = Process()
            process.executableURL = updaterExecutable
            process.arguments = [
                "update",
                "--source-app", sourceApp.path,
                "--target-app", targetApp.path,
                "--mount-root", root.path,
                "--wait-for-process", String(ProcessInfo.processInfo.processIdentifier),
            ]
            try process.run()
        } catch {
            let updateError = error
            var cleanupErrors: [String] = []
            do {
                try run("/usr/bin/hdiutil", arguments: ["detach", mount.path, "-force"])
            } catch {
                cleanupErrors.append(error.localizedDescription)
            }
            do {
                if fileManager.fileExists(atPath: root.path) {
                    try fileManager.removeItem(at: root)
                }
            } catch {
                cleanupErrors.append(error.localizedDescription)
            }
            guard cleanupErrors.isEmpty else {
                throw AgentUpdateError.cleanupFailed(
                    update: updateError.localizedDescription,
                    cleanup: cleanupErrors.joined(separator: "; ")
                )
            }
            throw updateError
        }
    }

    static func install(arguments: [String]) throws {
        let values = try parseOptions(arguments, allowed: [
            "--source-app", "--target-app", "--mount-root", "--wait-for-process",
        ])
        guard let sourcePath = values["--source-app"],
              let targetPath = values["--target-app"],
              let mountRoot = values["--mount-root"],
              let processID = Int32(values["--wait-for-process"] ?? ""),
              processID > 0
        else {
            throw AgentUpdateError.invalidArguments
        }

        try waitForExit(processID)
        let sourceApp = URL(fileURLWithPath: sourcePath, isDirectory: true)
        let targetApp = URL(fileURLWithPath: targetPath, isDirectory: true)
        guard let sourceVersion = Bundle(url: sourceApp)?.infoDictionary?["CFBundleShortVersionString"] as? String,
              let currentVersion = Bundle(url: targetApp)?.infoDictionary?["CFBundleShortVersionString"] as? String,
              hasUpdate(current: currentVersion, latest: sourceVersion)
        else {
            throw AgentUpdateError.invalidRelease
        }

        try replaceApp(source: sourceApp, target: targetApp)
        guard let installedVersion = Bundle(url: targetApp)?.infoDictionary?["CFBundleShortVersionString"] as? String,
              installedVersion == sourceVersion
        else {
            throw AgentUpdateError.installFailed
        }

        let cleanup = Process()
        cleanup.executableURL = URL(fileURLWithPath: mountRoot)
            .appendingPathComponent("ChargePilotAgentUpdater")
        cleanup.arguments = [
            "cleanup",
            "--mount-root", mountRoot,
            "--wait-for-process", String(ProcessInfo.processInfo.processIdentifier),
        ]
        try cleanup.run()
        guard NSWorkspace.shared.open(targetApp) else {
            throw AgentUpdateError.launchFailed
        }
    }

    static func cleanup(arguments: [String]) throws {
        let values = try parseOptions(arguments, allowed: ["--mount-root", "--wait-for-process"])
        guard let rootPath = values["--mount-root"],
              let processID = Int32(values["--wait-for-process"] ?? ""),
              processID > 0
        else {
            throw AgentUpdateError.invalidArguments
        }

        try waitForExit(processID)
        let root = URL(fileURLWithPath: rootPath, isDirectory: true)
        let mount = root.appendingPathComponent("volume", isDirectory: true)
        try run("/usr/bin/hdiutil", arguments: ["detach", mount.path, "-force"])
        try FileManager.default.removeItem(at: root)
    }

    static func showUpdateError(_ error: Error, arguments: [String]) {
        let targetPath = (try? parseOptions(arguments, allowed: [
            "--source-app", "--target-app", "--mount-root", "--wait-for-process",
        ]))?["--target-app"]
        let alert = NSAlert(error: error)
        alert.messageText = "ChargePilot Agent could not be updated"
        alert.runModal()
        if let targetPath {
            NSWorkspace.shared.open(URL(fileURLWithPath: targetPath, isDirectory: true))
        }
    }

    private static func replaceApp(source: URL, target: URL) throws {
        let parent = target.deletingLastPathComponent()
        let suffix = UUID().uuidString
        let staging = parent.appendingPathComponent(".ChargePilotAgent-update-\(suffix).app", isDirectory: true)
        let backup = parent.appendingPathComponent(".ChargePilotAgent-backup-\(suffix).app", isDirectory: true)

        let shell = "/usr/bin/ditto --rsrc --extattr --acl \(shellQuote(source.path)) \(shellQuote(staging.path))" +
            " && /bin/mv \(shellQuote(target.path)) \(shellQuote(backup.path))" +
            " && { /bin/mv \(shellQuote(staging.path)) \(shellQuote(target.path))" +
            " && /bin/rm -rf \(shellQuote(backup.path))" +
            " || { /bin/mv \(shellQuote(backup.path)) \(shellQuote(target.path)); exit 1; }; }"

        if FileManager.default.isWritableFile(atPath: parent.path) {
            try run("/bin/sh", arguments: ["-c", shell])
        } else {
            let appleScript = "do shell script \"\(appleScriptQuote(shell))\" with administrator privileges"
            try run("/usr/bin/osascript", arguments: ["-e", appleScript])
        }
    }

    private static func run(_ executable: String, arguments: [String]) throws {
        let process = Process()
        let output = Pipe()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = arguments
        process.standardOutput = output
        process.standardError = output
        try process.run()
        process.waitUntilExit()
        guard process.terminationStatus == 0 else {
            let data = output.fileHandleForReading.readDataToEndOfFile()
            let detail = String(data: data, encoding: .utf8)?
                .trimmingCharacters(in: .whitespacesAndNewlines)
            throw AgentUpdateError.commandFailed(detail?.isEmpty == false ? detail ?? executable : executable)
        }
    }

    private static func waitForExit(_ processID: Int32) throws {
        let deadline = Date().addingTimeInterval(120)
        while kill(processID, 0) == 0 || errno == EPERM {
            guard Date() < deadline else {
                throw AgentUpdateError.parentDidNotExit
            }
            Thread.sleep(forTimeInterval: 0.2)
        }
        guard errno == ESRCH else {
            throw AgentUpdateError.parentDidNotExit
        }
    }

    private static func versionParts(_ value: String) -> [Int]? {
        let components = value.split(separator: ".", omittingEmptySubsequences: false)
        guard components.count == 3,
              components.allSatisfy({ !$0.isEmpty && $0.allSatisfy { $0.isNumber } })
        else {
            return nil
        }
        var numbers: [Int] = []
        for component in components {
            guard let number = Int(component), number >= 0 else { return nil }
            numbers.append(number)
        }
        return numbers
    }

    private static func parseOptions(_ arguments: [String], allowed: Set<String>) throws -> [String: String] {
        var result: [String: String] = [:]
        var index = 0
        while index < arguments.count {
            let key = arguments[index]
            guard allowed.contains(key), index + 1 < arguments.count else {
                throw AgentUpdateError.invalidArguments
            }
            result[key] = arguments[index + 1]
            index += 2
        }
        return result
    }

    private static func shellQuote(_ value: String) -> String {
        "'" + value.replacingOccurrences(of: "'", with: "'\\''") + "'"
    }

    private static func appleScriptQuote(_ value: String) -> String {
        value.replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")
    }
}

private enum AgentUpdateError: LocalizedError {
    case releaseLookupFailed(Int)
    case downloadFailed(Int)
    case invalidRelease
    case invalidArguments
    case installFailed
    case parentDidNotExit
    case commandFailed(String)
    case cleanupFailed(update: String, cleanup: String)
    case launchFailed

    var errorDescription: String? {
        switch self {
        case .releaseLookupFailed(let status):
            "Could not check the latest release (HTTP \(status))."
        case .downloadFailed(let status):
            "Could not download the update (HTTP \(status))."
        case .invalidRelease:
            "The latest release does not contain a valid macOS update."
        case .invalidArguments:
            "The updater received invalid arguments."
        case .installFailed:
            "The updated app could not be verified after installation."
        case .parentDidNotExit:
            "ChargePilot did not quit, so the update was cancelled."
        case .commandFailed(let detail):
            "Update command failed: \(detail)"
        case .cleanupFailed(let update, let cleanup):
            "\(update) Cleanup also failed: \(cleanup)"
        case .launchFailed:
            "The update was installed, but macOS could not reopen ChargePilot Agent."
        }
    }
}
