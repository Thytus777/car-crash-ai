---
name: running-xcode-tests
description: "Runs and manages XCTest test suites for the iOS app. Use when asked to run tests, debug test failures, or check test coverage."
---

## Running Tests

- **Xcode**: Cmd+U to run all tests, Cmd+Shift+U to build tests only.
- **Command line**:
  ```bash
  xcodebuild test -scheme CarCrashAI -destination 'platform=iOS Simulator,name=iPhone 16'
  ```
- **Note**: Tests can only run on a Mac with Xcode installed. They cannot run on Windows.

## Test Structure

Tests live in the `CarCrashAITests/` directory. Test files mirror the source structure:

- `Services/AIService.swift` → `AIServiceTests.swift`
- `Models/Vehicle.swift` → `ModelTests.swift`

## Writing Tests

- Subclass `XCTestCase`.
- Test methods must start with `test`.
- Async tests: `func testFoo() async throws`.
- Assertions: `XCTAssertEqual`, `XCTAssertTrue`, `XCTAssertThrowsError`, `XCTAssertNil`.

## Mocking Network

- Create a `URLProtocol` subclass (`MockURLProtocol`).
- Register it in `setUp`.
- Set mock response data and status code on the mock protocol.
- Unregister in `tearDown`.

## Test Fixtures

- Sample JSON responses are stored in the test bundle.
- Sample images are stored in test assets.

## Async Testing

- XCTest has native async test support.
- Use `async throws` on test methods.
- No special annotation needed (unlike pytest-asyncio).

## Debugging Failures

- Use the **Test navigator** in Xcode to see pass/fail status.
- Set **breakpoints** directly in test methods.
- Check **test logs** in the Report navigator for detailed output.
