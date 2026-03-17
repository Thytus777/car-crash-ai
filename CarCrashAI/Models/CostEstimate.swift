import Foundation

struct CostEstimate: Codable, Identifiable {
    let component: String
    let recommendation: Recommendation
    let partCostLow: Decimal
    let partCostAvg: Decimal
    let partCostHigh: Decimal
    let pricingMethod: PricingMethod
    let laborHours: Decimal
    let laborRate: Decimal
    let laborCost: Decimal
    let totalLow: Decimal
    let totalAvg: Decimal
    let totalHigh: Decimal

    var id: String { component }

    enum Recommendation: String, Codable {
        case repair
        case replace
    }

    enum PricingMethod: String, Codable {
        case liveSearch = "live_search"
        case staticReference = "static_reference"
        case aiEstimate = "ai_estimate"
        case defaultFallback = "default_fallback"
    }

    enum CodingKeys: String, CodingKey {
        case component, recommendation
        case partCostLow = "part_cost_low"
        case partCostAvg = "part_cost_avg"
        case partCostHigh = "part_cost_high"
        case pricingMethod = "pricing_method"
        case laborHours = "labor_hours"
        case laborRate = "labor_rate"
        case laborCost = "labor_cost"
        case totalLow = "total_low"
        case totalAvg = "total_avg"
        case totalHigh = "total_high"
    }
}

struct PriceResult: Codable {
    let price: Decimal?
    let currency: String
    let partType: String
    let confidence: Double

    enum CodingKeys: String, CodingKey {
        case price, currency, confidence
        case partType = "part_type"
    }
}
