import Foundation
import UIKit
import GoogleGenerativeAI

// MARK: - AIServiceError

enum AIServiceError: Error, LocalizedError {
    case rateLimited
    case invalidResponse
    case networkError(Error)
    case invalidAPIKey
    case allProvidersRateLimited

    var errorDescription: String? {
        switch self {
        case .rateLimited: "AI provider rate limit exceeded. Please wait and try again."
        case .invalidResponse: "Received an invalid response from the AI provider."
        case .networkError(let error): "Network error: \(error.localizedDescription)"
        case .invalidAPIKey: "Invalid API key. Check your Config.plist."
        case .allProvidersRateLimited: "All AI providers are rate limited. Please try again later."
        }
    }
}

// MARK: - AIService

@MainActor
final class AIService {
    static let shared = AIService()

    private let maxRetries = 2
    private let baseRetryDelay: TimeInterval = 10

    private let session: URLSession

    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 60
        self.session = URLSession(configuration: config)
    }

    // MARK: - Public API

    func visionCompletion(prompt: String, images: [Data]) async throws -> String {
        let primary = Config.aiProvider
        let secondary: Config.AIProvider = primary == .gemini ? .openai : .gemini

        do {
            return try await callVision(provider: primary, prompt: prompt, images: images)
        } catch AIServiceError.rateLimited {
            return try await callVision(provider: secondary, prompt: prompt, images: images)
        } catch AIServiceError.invalidAPIKey where primary == .gemini {
            return try await callVision(provider: secondary, prompt: prompt, images: images)
        }
    }

    func textCompletion(prompt: String) async throws -> String {
        let primary = Config.aiProvider
        let secondary: Config.AIProvider = primary == .gemini ? .openai : .gemini

        do {
            return try await callText(provider: primary, prompt: prompt)
        } catch AIServiceError.rateLimited {
            return try await callText(provider: secondary, prompt: prompt)
        } catch AIServiceError.invalidAPIKey where primary == .gemini {
            return try await callText(provider: secondary, prompt: prompt)
        }
    }

    // MARK: - Provider Router

    private func callVision(provider: Config.AIProvider, prompt: String, images: [Data]) async throws -> String {
        switch provider {
        case .gemini:
            return try await geminiVision(prompt: prompt, images: images)
        case .openai:
            return try await openAIVision(prompt: prompt, images: images)
        }
    }

    private func callText(provider: Config.AIProvider, prompt: String) async throws -> String {
        switch provider {
        case .gemini:
            return try await geminiText(prompt: prompt)
        case .openai:
            return try await openAIText(prompt: prompt)
        }
    }

    // MARK: - Gemini

    private func geminiVision(prompt: String, images: [Data]) async throws -> String {
        let apiKey = Config.geminiAPIKey
        guard !apiKey.isEmpty else { throw AIServiceError.invalidAPIKey }

        let generationConfig = GenerationConfig(
            responseMIMEType: "application/json",
            maxOutputTokens: 16000
        )
        let model = GenerativeModel(
            name: "gemini-2.5-flash",
            apiKey: apiKey,
            generationConfig: generationConfig
        )

        var parts: [ModelContent.Part] = [.text(prompt)]
        for imageData in images {
            parts.append(.data(mimetype: "image/jpeg", imageData))
        }

        return try await retryWithBackoff { [model, parts] in
            let response = try await model.generateContent(parts)
            guard let text = response.text else {
                throw AIServiceError.invalidResponse
            }
            return text
        }
    }

    private func geminiText(prompt: String) async throws -> String {
        let apiKey = Config.geminiAPIKey
        guard !apiKey.isEmpty else { throw AIServiceError.invalidAPIKey }

        let generationConfig = GenerationConfig(
            responseMIMEType: "application/json",
            maxOutputTokens: 8000
        )
        let model = GenerativeModel(
            name: "gemini-2.5-flash",
            apiKey: apiKey,
            generationConfig: generationConfig
        )

        return try await retryWithBackoff { [model] in
            let response = try await model.generateContent(prompt)
            guard let text = response.text else {
                throw AIServiceError.invalidResponse
            }
            return text
        }
    }

    // MARK: - OpenAI

    private func openAIVision(prompt: String, images: [Data]) async throws -> String {
        let apiKey = Config.openAIAPIKey
        guard !apiKey.isEmpty else { throw AIServiceError.invalidAPIKey }

        var contentParts: [[String: Any]] = [
            ["type": "text", "text": prompt]
        ]
        for imageData in images {
            let base64 = imageData.base64EncodedString()
            contentParts.append([
                "type": "image_url",
                "image_url": ["url": "data:image/jpeg;base64,\(base64)"]
            ])
        }

        let body: [String: Any] = [
            "model": "gpt-4.1-mini",
            "messages": [
                ["role": "user", "content": contentParts]
            ],
            "max_tokens": 8000
        ]

        return try await openAIRequest(apiKey: apiKey, body: body)
    }

    private func openAIText(prompt: String) async throws -> String {
        let apiKey = Config.openAIAPIKey
        guard !apiKey.isEmpty else { throw AIServiceError.invalidAPIKey }

        let body: [String: Any] = [
            "model": "gpt-4.1-nano",
            "messages": [
                ["role": "user", "content": prompt]
            ],
            "max_tokens": 4000
        ]

        return try await openAIRequest(apiKey: apiKey, body: body)
    }

    private func openAIRequest(apiKey: String, body: [String: Any]) async throws -> String {
        var request = URLRequest(url: URL(string: "https://api.openai.com/v1/chat/completions")!)
        request.httpMethod = "POST"
        request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        return try await retryWithBackoff { [session, request] in
            let (data, response) = try await session.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else {
                throw AIServiceError.invalidResponse
            }

            if httpResponse.statusCode == 429 {
                throw AIServiceError.rateLimited
            }
            if httpResponse.statusCode == 401 || httpResponse.statusCode == 403 {
                throw AIServiceError.invalidAPIKey
            }
            guard (200...299).contains(httpResponse.statusCode) else {
                throw AIServiceError.invalidResponse
            }

            guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let choices = json["choices"] as? [[String: Any]],
                  let first = choices.first,
                  let message = first["message"] as? [String: Any],
                  let content = message["content"] as? String else {
                throw AIServiceError.invalidResponse
            }
            return content
        }
    }

    // MARK: - Retry Logic

    private func retryWithBackoff<T>(operation: @escaping () async throws -> T) async throws -> T {
        var lastError: Error = AIServiceError.invalidResponse

        for attempt in 0...maxRetries {
            do {
                return try await operation()
            } catch let error as AIServiceError where error == .rateLimited {
                lastError = error
                if attempt < maxRetries {
                    let delay = baseRetryDelay * Double(attempt + 1)
                    try await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
                }
            } catch {
                throw error
            }
        }

        throw lastError
    }
}

// MARK: - AIServiceError + Equatable

extension AIServiceError: Equatable {
    static func == (lhs: AIServiceError, rhs: AIServiceError) -> Bool {
        switch (lhs, rhs) {
        case (.rateLimited, .rateLimited): true
        case (.invalidResponse, .invalidResponse): true
        case (.invalidAPIKey, .invalidAPIKey): true
        case (.allProvidersRateLimited, .allProvidersRateLimited): true
        case (.networkError, .networkError): true
        default: false
        }
    }
}
