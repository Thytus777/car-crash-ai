import Foundation

struct DamageItem: Codable, Identifiable {
    let component: String
    let damageType: String
    let severity: Double
    let description: String

    var id: String { component }

    enum CodingKeys: String, CodingKey {
        case component, severity, description
        case damageType = "damage_type"
    }

    var recommendation: CostEstimate.Recommendation {
        severity > Config.severityReplaceThreshold ? .replace : .repair
    }
}

struct DamageAssessment: Codable {
    let damages: [DamageItem]
}
