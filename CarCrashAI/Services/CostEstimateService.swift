import Foundation

// MARK: - LaborRates

enum LaborRates {
    static let hoursPerComponent: [String: Decimal] = [
        "front_bumper": 3.5,
        "rear_bumper": 3.0,
        "hood": 3.0,
        "trunk": 2.5,
        "grille": 1.0,
        "headlight_left": 1.0,
        "headlight_right": 1.0,
        "taillight_left": 0.75,
        "taillight_right": 0.75,
        "fender_front_left": 4.0,
        "fender_front_right": 4.0,
        "door_front_left": 4.5,
        "door_front_right": 4.5,
        "door_rear_left": 4.5,
        "door_rear_right": 4.5,
        "mirror_left": 0.75,
        "mirror_right": 0.75,
        "quarter_panel_left": 6.0,
        "quarter_panel_right": 6.0,
        "rocker_panel_left": 3.0,
        "rocker_panel_right": 3.0,
        "windshield_front": 2.0,
        "windshield_rear": 1.5,
        "roof": 8.0,
        "a_pillar_left": 5.0,
        "a_pillar_right": 5.0,
        "b_pillar_left": 5.0,
        "b_pillar_right": 5.0,
        "wheel_front_left": 1.0,
        "wheel_front_right": 1.0,
        "wheel_rear_left": 1.0,
        "wheel_rear_right": 1.0,
    ]

    static func hours(for component: String) -> Decimal {
        hoursPerComponent[component] ?? 2.0
    }
}

// MARK: - CostEstimateService

enum CostEstimateService {
    static func estimate(
        vehicle: Vehicle,
        damages: [DamageItem]
    ) async -> [CostEstimate] {
        var estimates: [CostEstimate] = []

        for damage in damages {
            let pricing = await fetchPrice(vehicle: vehicle, component: damage.component)
            let laborHours = LaborRates.hours(for: damage.component)
            let laborRate = Config.laborRatePerHour
            let laborCost = laborHours * laborRate

            let estimate = CostEstimate(
                component: damage.component,
                recommendation: damage.recommendation,
                partCostLow: pricing.low,
                partCostAvg: pricing.avg,
                partCostHigh: pricing.high,
                pricingMethod: pricing.method,
                laborHours: laborHours,
                laborRate: laborRate,
                laborCost: laborCost,
                totalLow: pricing.low + laborCost,
                totalAvg: pricing.avg + laborCost,
                totalHigh: pricing.high + laborCost
            )
            estimates.append(estimate)
        }

        return estimates
    }

    private static func fetchPrice(
        vehicle: Vehicle,
        component: String
    ) async -> (low: Decimal, avg: Decimal, high: Decimal, method: CostEstimate.PricingMethod) {
        do {
            return try await PriceSearchService.searchPrice(vehicle: vehicle, component: component)
        } catch {
            return (low: 100, avg: 200, high: 400, method: .defaultFallback)
        }
    }
}
