import Foundation

enum Config {
    private static let infoDictionary: [String: Any] = {
        guard let path = Bundle.main.path(forResource: "Config", ofType: "plist"),
              let dict = NSDictionary(contentsOfFile: path) as? [String: Any] else {
            return [:]
        }
        return dict
    }()

    static var geminiAPIKey: String {
        infoDictionary["GEMINI_API_KEY"] as? String ?? ""
    }

    static var openAIAPIKey: String {
        infoDictionary["OPENAI_API_KEY"] as? String ?? ""
    }

    static var serpAPIKey: String {
        infoDictionary["SERPAPI_KEY"] as? String ?? ""
    }

    static var aiProvider: AIProvider {
        let value = infoDictionary["AI_PROVIDER"] as? String ?? "gemini"
        return AIProvider(rawValue: value) ?? .gemini
    }

    static var laborRatePerHour: Decimal {
        Decimal(infoDictionary["LABOR_RATE_PER_HOUR"] as? Double ?? 75.0)
    }

    static var severityReplaceThreshold: Double {
        infoDictionary["SEVERITY_REPLACE_THRESHOLD"] as? Double ?? 0.3
    }

    enum AIProvider: String {
        case gemini
        case openai
    }
}
