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
}
