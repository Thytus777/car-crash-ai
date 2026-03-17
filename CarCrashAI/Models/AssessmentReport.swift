import Foundation

struct AssessmentReport: Codable {
    let vehicle: Vehicle
    let damages: [DamageItem]
    let estimates: [CostEstimate]
    let totals: Totals

    struct Totals: Codable {
        let partsTotal: Decimal
        let laborTotal: Decimal
        let grandTotal: Decimal

        enum CodingKeys: String, CodingKey {
            case partsTotal = "parts_total"
            case laborTotal = "labor_total"
            case grandTotal = "grand_total"
        }
    }

    init(vehicle: Vehicle, damages: [DamageItem], estimates: [CostEstimate]) {
        self.vehicle = vehicle
        self.damages = damages
        self.estimates = estimates

        let partsTotal = estimates.reduce(Decimal.zero) { $0 + $1.partCostAvg }
        let laborTotal = estimates.reduce(Decimal.zero) { $0 + $1.laborCost }
        self.totals = Totals(
            partsTotal: partsTotal,
            laborTotal: laborTotal,
            grandTotal: partsTotal + laborTotal
        )
    }
}
