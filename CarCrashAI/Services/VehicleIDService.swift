import Foundation

// MARK: - VehicleIDService

enum VehicleIDService {
    static let confidenceThreshold = 0.7

    static func identify(from images: [Data]) async throws -> Vehicle {
        let response = try await AIService.shared.visionCompletion(
            prompt: VehiclePrompts.identification,
            images: images
        )

        let jsonData = Data(response.utf8)
        let vehicle = try JSONDecoder().decode(Vehicle.self, from: jsonData)
        return vehicle
    }

    static func needsManualEntry(_ vehicle: Vehicle) -> Bool {
        vehicle.confidence < confidenceThreshold
    }
}
