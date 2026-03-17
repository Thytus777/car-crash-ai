import SwiftUI
import PhotosUI

// MARK: - HomeView

struct HomeView: View {
    @State private var selectedImages: [UIImage] = []
    @State private var photoPickerItems: [PhotosPickerItem] = []
    @State private var showCamera = false
    @State private var isAnalyzing = false
    @State private var analysisResult: AssessmentReport?
    @State private var errorMessage: String?
    @State private var showError = false

    private let columns = [
        GridItem(.adaptive(minimum: 100, maximum: 150), spacing: 8)
    ]

    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                if selectedImages.isEmpty {
                    emptyState
                } else {
                    photoGrid
                }

                actionButtons

                if isAnalyzing {
                    ProgressView("Preparing analysis...")
                        .padding()
                }
            }
            .padding()
            .navigationTitle("Car Crash AI")
            .navigationDestination(item: $analysisResult) { report in
                ReportView(report: report)
            }
            .sheet(isPresented: $showCamera) {
                CameraView { image in
                    selectedImages.append(image)
                }
            }
            .onChange(of: photoPickerItems) {
                Task { await loadPickerItems() }
            }
            .alert("Error", isPresented: $showError) {
                Button("OK") { }
            } message: {
                Text(errorMessage ?? "An unknown error occurred.")
            }
        }
    }

    // MARK: - Subviews

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "car.side")
                .font(.system(size: 60))
                .foregroundStyle(.secondary)
            Text("Add photos of vehicle damage")
                .font(.headline)
            Text("Take new photos or select from your library to start an AI damage assessment.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding(.vertical, 40)
        .accessibilityElement(children: .combine)
    }

    private var photoGrid: some View {
        ScrollView {
            LazyVGrid(columns: columns, spacing: 8) {
                ForEach(Array(selectedImages.enumerated()), id: \.offset) { index, image in
                    Image(uiImage: image)
                        .resizable()
                        .scaledToFill()
                        .frame(minHeight: 100)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                        .overlay(alignment: .topTrailing) {
                            Button {
                                selectedImages.remove(at: index)
                            } label: {
                                Image(systemName: "xmark.circle.fill")
                                    .font(.title3)
                                    .foregroundStyle(.white)
                                    .shadow(radius: 2)
                            }
                            .padding(4)
                            .accessibilityLabel("Remove photo \(index + 1)")
                        }
                }
            }
        }
    }

    private var actionButtons: some View {
        VStack(spacing: 12) {
            HStack(spacing: 12) {
                Button {
                    showCamera = true
                } label: {
                    Label("Camera", systemImage: "camera")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .disabled(isAnalyzing || selectedImages.count >= 10)

                PhotosPicker(
                    selection: $photoPickerItems,
                    maxSelectionCount: 10 - selectedImages.count,
                    matching: .images
                ) {
                    Label("Library", systemImage: "photo.on.rectangle")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .disabled(isAnalyzing || selectedImages.count >= 10)
            }

            Button {
                Task { await analyzeImages() }
            } label: {
                Label("Analyze Damage", systemImage: "sparkles")
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 4)
            }
            .buttonStyle(.borderedProminent)
            .disabled(selectedImages.isEmpty || isAnalyzing)
            .accessibilityLabel("Analyze damage in \(selectedImages.count) photos")
        }
    }

    // MARK: - Actions

    private func loadPickerItems() async {
        for item in photoPickerItems {
            if let data = try? await item.loadTransferable(type: Data.self),
               let image = UIImage(data: data) {
                selectedImages.append(image)
            }
        }
        photoPickerItems.removeAll()
    }

    private func analyzeImages() async {
        isAnalyzing = true
        defer { isAnalyzing = false }

        do {
            let imageData = try ImageProcessor.processMultiple(selectedImages)

            let vehicle = try await VehicleIDService.identify(from: imageData)
            let damages = try await DamageDetectService.detect(from: imageData)
            let estimates = await CostEstimateService.estimate(vehicle: vehicle, damages: damages)

            analysisResult = AssessmentReport(vehicle: vehicle, damages: damages, estimates: estimates)
        } catch {
            errorMessage = error.localizedDescription
            showError = true
        }
    }
}

// MARK: - AssessmentReport + Hashable

extension AssessmentReport: @retroactive Hashable {
    static func == (lhs: AssessmentReport, rhs: AssessmentReport) -> Bool {
        lhs.vehicle == rhs.vehicle
    }

    func hash(into hasher: inout Hasher) {
        hasher.combine(vehicle.make)
        hasher.combine(vehicle.model)
        hasher.combine(vehicle.year)
    }
}
