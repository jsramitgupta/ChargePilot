import XCTest
@testable import ChargePilotAgent

final class CPUTickSnapshotTests: XCTestCase {
    func testMachIdleTicksAreReadFromThirdCounter() throws {
        let previous = try XCTUnwrap(CPUTickSnapshot.fromMachTicks([100, 100, 700, 100]))
        let current = try XCTUnwrap(CPUTickSnapshot.fromMachTicks([150, 130, 1_550, 170]))
        let usage = try XCTUnwrap(current.utilization(since: previous))

        XCTAssertEqual(usage, 15, accuracy: 0.001)
    }

    func testMachTickParserRejectsUnexpectedCounterCount() {
        XCTAssertNil(CPUTickSnapshot.fromMachTicks([1, 2, 3]))
    }

    func testOnlyFixedUnexpiredShutdownCommandsValidate() throws {
        let command = ShutdownCommand(
            id: UUID(uuidString: "30f111ca-99ed-472c-a815-93e6581c5f7c")!,
            operation: "shutdown",
            gracePeriodSeconds: 60,
            expiresAt: Date().addingTimeInterval(120)
        )

        XCTAssertNoThrow(try command.validate())
    }

    func testExpiredOrUnknownShutdownCommandIsRejected() throws {
        let command = ShutdownCommand(
            id: UUID(uuidString: "30f111ca-99ed-472c-a815-93e6581c5f7c")!,
            operation: "shell",
            gracePeriodSeconds: 60,
            expiresAt: Date(timeIntervalSince1970: 0)
        )

        XCTAssertThrowsError(try command.validate())
    }
}
