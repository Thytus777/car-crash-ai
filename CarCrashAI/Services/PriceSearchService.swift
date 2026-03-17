import Foundation

// MARK: - PriceSearchService

enum PriceSearchService {
    private static let cachePrefix = "price_cache_"
    private static let cacheTTL: TimeInterval = 24 * 60 * 60 // 24 hours

    // MARK: - Public API

    static func searchPrice(
        vehicle: Vehicle,
        component: String
    ) async throws -> (low: Decimal, avg: Decimal, high: Decimal, method: CostEstimate.PricingMethod) {
        // Check cache first
        if let cached = loadCachedPrice(vehicle: vehicle, component: component) {
            return cached
        }

        // Try live search via SerpAPI
        if !Config.serpAPIKey.isEmpty {
            if let live = try? await liveSearch(vehicle: vehicle, component: component) {
                cachePrice(vehicle: vehicle, component: component, result: live)
                return live
            }
        }

        // Try AI-based price estimation
        if let aiEstimate = try? await aiPriceEstimate(vehicle: vehicle, component: component) {
            cachePrice(vehicle: vehicle, component: component, result: aiEstimate)
            return aiEstimate
        }

        // Fall back to static CSV
        if let csvPrice = staticLookup(vehicle: vehicle, component: component) {
            return csvPrice
        }

        // Default fallback
        return (low: 100, avg: 200, high: 400, method: .defaultFallback)
    }

    // MARK: - Live Search (SerpAPI)

    private static func liveSearch(
        vehicle: Vehicle,
        component: String
    ) async throws -> (low: Decimal, avg: Decimal, high: Decimal, method: CostEstimate.PricingMethod) {
        let query = "\(vehicle.year) \(vehicle.make) \(vehicle.model) \(Components.displayName(component)) price buy"
        guard let encodedQuery = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed),
              let url = URL(string: "https://serpapi.com/search.json?q=\(encodedQuery)&api_key=\(Config.serpAPIKey)&engine=google") else {
            throw AIServiceError.invalidResponse
        }

        let (data, _) = try await URLSession.shared.data(from: url)
        guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let results = json["organic_results"] as? [[String: Any]] else {
            throw AIServiceError.invalidResponse
        }

        let snippets = results.prefix(5).compactMap { $0["snippet"] as? String }
        guard !snippets.isEmpty else { throw AIServiceError.invalidResponse }

        let snippetText = snippets.joined(separator: "\n---\n")
        let extractionPrompt = DamagePrompts.priceExtraction(vehicle: vehicle, component: component)
            + "\n\nText:\n---\n\(snippetText)\n---"

        let priceResponse = try await AIService.shared.textCompletion(prompt: extractionPrompt)
        let priceData = Data(priceResponse.utf8)
        let priceResult = try JSONDecoder().decode(PriceResult.self, from: priceData)

        guard let price = priceResult.price, priceResult.confidence >= 0.5 else {
            throw AIServiceError.invalidResponse
        }

        let variance: Decimal = price * Decimal(0.25)
        return (
            low: price - variance,
            avg: price,
            high: price + variance,
            method: .liveSearch
        )
    }

    // MARK: - AI Price Estimation

    private static func aiPriceEstimate(
        vehicle: Vehicle,
        component: String
    ) async throws -> (low: Decimal, avg: Decimal, high: Decimal, method: CostEstimate.PricingMethod) {
        let prompt = DamagePrompts.aiPriceEstimate(vehicle: vehicle, component: component)
        let response = try await AIService.shared.textCompletion(prompt: prompt)
        let data = Data(response.utf8)

        guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let low = json["price_low"] as? Double,
              let avg = json["price_avg"] as? Double,
              let high = json["price_high"] as? Double else {
            throw AIServiceError.invalidResponse
        }

        return (
            low: Decimal(low),
            avg: Decimal(avg),
            high: Decimal(high),
            method: .aiEstimate
        )
    }

    // MARK: - Static CSV Lookup

    private static func staticLookup(
        vehicle: Vehicle,
        component: String
    ) -> (low: Decimal, avg: Decimal, high: Decimal, method: CostEstimate.PricingMethod)? {
        guard let url = Bundle.main.url(forResource: "parts_prices", withExtension: "csv"),
              let content = try? String(contentsOf: url, encoding: .utf8) else {
            return nil
        }

        let lines = content.components(separatedBy: .newlines).dropFirst() // skip header
        for line in lines {
            let cols = line.components(separatedBy: ",")
            guard cols.count >= 6 else { continue }

            let make = cols[0]
            let model = cols[1]
            let yearStart = Int(cols[2]) ?? 0
            let yearEnd = Int(cols[3]) ?? 0
            let comp = cols[4]
            let avgPrice = Decimal(string: cols[5]) ?? 0

            if make.lowercased() == vehicle.make.lowercased(),
               model.lowercased() == vehicle.model.lowercased(),
               vehicle.year >= yearStart && vehicle.year <= yearEnd,
               comp == component {
                let variance = avgPrice * Decimal(0.2)
                return (
                    low: avgPrice - variance,
                    avg: avgPrice,
                    high: avgPrice + variance,
                    method: .staticReference
                )
            }
        }
        return nil
    }

    // MARK: - Cache

    private static func cacheKey(vehicle: Vehicle, component: String) -> String {
        "\(cachePrefix)\(vehicle.make)_\(vehicle.model)_\(vehicle.year)_\(component)"
    }

    private static func cachePrice(
        vehicle: Vehicle,
        component: String,
        result: (low: Decimal, avg: Decimal, high: Decimal, method: CostEstimate.PricingMethod)
    ) {
        let entry: [String: Any] = [
            "low": NSDecimalNumber(decimal: result.low).doubleValue,
            "avg": NSDecimalNumber(decimal: result.avg).doubleValue,
            "high": NSDecimalNumber(decimal: result.high).doubleValue,
            "method": result.method.rawValue,
            "timestamp": Date().timeIntervalSince1970
        ]
        UserDefaults.standard.set(entry, forKey: cacheKey(vehicle: vehicle, component: component))
    }

    private static func loadCachedPrice(
        vehicle: Vehicle,
        component: String
    ) -> (low: Decimal, avg: Decimal, high: Decimal, method: CostEstimate.PricingMethod)? {
        guard let entry = UserDefaults.standard.dictionary(forKey: cacheKey(vehicle: vehicle, component: component)),
              let timestamp = entry["timestamp"] as? TimeInterval,
              Date().timeIntervalSince1970 - timestamp < cacheTTL,
              let low = entry["low"] as? Double,
              let avg = entry["avg"] as? Double,
              let high = entry["high"] as? Double,
              let methodRaw = entry["method"] as? String,
              let method = CostEstimate.PricingMethod(rawValue: methodRaw) else {
            return nil
        }
        return (low: Decimal(low), avg: Decimal(avg), high: Decimal(high), method: method)
    }
}
