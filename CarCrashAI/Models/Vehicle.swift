import Foundation

struct Vehicle: Codable, Equatable {
    let make: String
    let model: String
    let year: Int
    let bodyStyle: String?
    let color: String?
    let confidence: Double

    enum CodingKeys: String, CodingKey {
        case make, model, year, color, confidence
        case bodyStyle = "body_style"
    }

    init(make: String, model: String, year: Int, bodyStyle: String? = nil, color: String? = nil, confidence: Double = 1.0) {
        self.make = make
        self.model = model
        self.year = year
        self.bodyStyle = bodyStyle
        self.color = color
        self.confidence = min(max(confidence, 0.0), 1.0)
    }
}
