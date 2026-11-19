import Foundation

// MARK: - DamageDetectService

enum DamageDetectService {
    static func detect(from images: [Data]) async throws -> [DamageItem] {
        let response = try await AIService.shared.visionCompletion(
            prompt: DamagePrompts.assessment,
            images: images
        )

        let jsonData = Data(response.utf8)
        let items = try JSONDecoder().decode([DamageItem].self, from: jsonData)

        return items.filter { Components.all.contains($0.component) }
    }
}
