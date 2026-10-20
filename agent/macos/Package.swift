// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "ChargePilotAgent",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "ChargePilotAgent", targets: ["ChargePilotAgent"]),
    ],
    targets: [
        .executableTarget(name: "ChargePilotAgent"),
    ]
)
