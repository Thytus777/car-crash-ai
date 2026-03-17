import SwiftUI

// MARK: - AnalysisView

struct AnalysisView: View {
    let stage: AnalysisStage

    var body: some View {
        VStack(spacing: 24) {
            ProgressView()
                .scaleEffect(1.5)

            Text(stage.message)
                .font(.headline)

            Text(stage.detail)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding(40)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Analysis in progress. \(stage.message)")
    }
}

// MARK: - AnalysisStage

enum AnalysisStage {
    case identifyingVehicle
    case detectingDamage
    case estimatingCosts

    var message: String {
        switch self {
        case .identifyingVehicle: "Identifying vehicle..."
        case .detectingDamage: "Detecting damage..."
        case .estimatingCosts: "Estimating costs..."
        }
    }

    var detail: String {
        switch self {
        case .identifyingVehicle: "Analyzing photos to determine make, model, and year."
        case .detectingDamage: "Scanning for damaged components and assessing severity."
        case .estimatingCosts: "Looking up part prices and calculating repair costs."
        }
    }
}
