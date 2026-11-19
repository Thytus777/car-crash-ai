import Foundation
import UIKit

// MARK: - AnalysisPhase

enum AnalysisPhase: String {
    case idle = "Ready"
    case identifyingVehicle = "Identifying vehicle..."
    case detectingDamage = "Detecting damage..."
    case estimatingCosts = "Estimating costs..."
    case complete = "Analysis complete"
    case failed = "Analysis failed"
}

// MARK: - AnalysisViewModel

@MainActor
@Observable
final class AnalysisViewModel {
    var selectedImages: [UIImage] = []
    var phase: AnalysisPhase = .idle
    var report: AssessmentReport?
    var errorMessage: String?
    var showError = false

    var isAnalyzing: Bool {
        switch phase {
        case .identifyingVehicle, .detectingDamage, .estimatingCosts:
            true
        default:
            false
        }
    }

    var hasImages: Bool { !selectedImages.isEmpty }

    // MARK: - Image Management

    func addImage(_ image: UIImage) {
        selectedImages.append(image)
    }

    func removeImage(at index: Int) {
        guard selectedImages.indices.contains(index) else { return }
        selectedImages.remove(at: index)
    }

    func clearImages() {
        selectedImages.removeAll()
    }

    // MARK: - Analysis

    func analyze() async {
        guard hasImages else { return }

        report = nil
        errorMessage = nil

        do {
            let imageData = try ImageProcessor.processMultiple(selectedImages)

            // Step 1: Identify vehicle
            phase = .identifyingVehicle
            let vehicle = try await VehicleIDService.identify(from: imageData)

            // Step 2: Detect damage
            phase = .detectingDamage
            let damages = try await DamageDetectService.detect(from: imageData)

            // Step 3: Estimate costs
            phase = .estimatingCosts
            let estimates = await CostEstimateService.estimate(vehicle: vehicle, damages: damages)

            // Build report
            report = AssessmentReport(vehicle: vehicle, damages: damages, estimates: estimates)
            phase = .complete

        } catch {
            phase = .failed
            errorMessage = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            showError = true
        }
    }

    func reset() {
        selectedImages.removeAll()
        phase = .idle
        report = nil
        errorMessage = nil
        showError = false
    }
}
