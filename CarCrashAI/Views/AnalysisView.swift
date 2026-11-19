import SwiftUI

// MARK: - AnalysisView

struct AnalysisView: View {
    @Bindable var viewModel: AnalysisViewModel
    let onComplete: () -> Void

    var body: some View {
        VStack(spacing: 32) {
            Spacer()

            Image(systemName: phaseIcon)
                .font(.system(size: 56))
                .foregroundStyle(.blue)
                .symbolEffect(.pulse, isActive: viewModel.isAnalyzing)
                .accessibilityHidden(true)

            VStack(spacing: 12) {
                Text(viewModel.phase.rawValue)
                    .font(.title2.bold())

                if viewModel.isAnalyzing {
                    ProgressView()
                        .controlSize(.large)
                }
            }

            Spacer()
        }
        .frame(maxWidth: .infinity)
        .padding()
        .navigationTitle("Analyzing")
        .navigationBarBackButtonHidden(viewModel.isAnalyzing)
        .task {
            await viewModel.analyze()
            if viewModel.phase == .complete {
                onComplete()
            }
        }
        .alert("Analysis Failed", isPresented: $viewModel.showError) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(viewModel.errorMessage ?? "An unknown error occurred.")
        }
    }

    private var phaseIcon: String {
        switch viewModel.phase {
        case .idle: "sparkles"
        case .identifyingVehicle: "car.fill"
        case .detectingDamage: "magnifyingglass"
        case .estimatingCosts: "dollarsign.circle.fill"
        case .complete: "checkmark.circle.fill"
        case .failed: "exclamationmark.triangle.fill"
        }
    }
}
