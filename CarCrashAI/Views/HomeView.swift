import SwiftUI
import PhotosUI

// MARK: - HomeView

struct HomeView: View {
    @State private var viewModel = AnalysisViewModel()
    @State private var showCamera = false
    @State private var showPhotoPicker = false
    @State private var selectedPhotoItems: [PhotosPickerItem] = []
    @State private var navigateToAnalysis = false
    @State private var navigateToReport = false

    private let columns = [
        GridItem(.adaptive(minimum: 100, maximum: 150), spacing: 12)
    ]

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 24) {
                    headerSection
                    photoGrid
                    actionButtons
                }
                .padding()
            }
            .navigationTitle("Car Crash AI")
            .alert("Error", isPresented: $viewModel.showError) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(viewModel.errorMessage ?? "An unknown error occurred.")
            }
            .navigationDestination(isPresented: $navigateToAnalysis) {
                AnalysisView(viewModel: viewModel) {
                    navigateToAnalysis = false
                    navigateToReport = true
                }
            }
            .navigationDestination(isPresented: $navigateToReport) {
                ReportView(viewModel: viewModel)
            }
            .sheet(isPresented: $showCamera) {
                CameraView { image in
                    viewModel.addImage(image)
                }
            }
            .photosPicker(
                isPresented: $showPhotoPicker,
                selection: $selectedPhotoItems,
                maxSelectionCount: 10,
                matching: .images
            )
            .onChange(of: selectedPhotoItems) {
                Task { await loadSelectedPhotos() }
            }
        }
    }

    // MARK: - Header

    private var headerSection: some View {
        VStack(spacing: 8) {
            Image(systemName: "car.fill")
                .font(.system(size: 48))
                .foregroundStyle(.blue)
                .accessibilityHidden(true)

            Text("Take or select photos of vehicle damage")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding(.top, 8)
    }

    // MARK: - Photo Grid

    private var photoGrid: some View {
        Group {
            if viewModel.hasImages {
                LazyVGrid(columns: columns, spacing: 12) {
                    ForEach(Array(viewModel.selectedImages.enumerated()), id: \.offset) { index, image in
                        ZStack(alignment: .topTrailing) {
                            Image(uiImage: image)
                                .resizable()
                                .scaledToFill()
                                .frame(minWidth: 100, minHeight: 100)
                                .clipped()
                                .cornerRadius(12)

                            Button {
                                viewModel.removeImage(at: index)
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
            } else {
                ContentUnavailableView(
                    "No Photos",
                    systemImage: "photo.on.rectangle.angled",
                    description: Text("Add photos to begin damage analysis.")
                )
                .frame(minHeight: 200)
            }
        }
    }

    // MARK: - Actions

    private var actionButtons: some View {
        VStack(spacing: 12) {
            HStack(spacing: 12) {
                Button {
                    showCamera = true
                } label: {
                    Label("Camera", systemImage: "camera.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .accessibilityLabel("Take a photo with the camera")

                Button {
                    showPhotoPicker = true
                } label: {
                    Label("Photos", systemImage: "photo.fill.on.rectangle.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .accessibilityLabel("Select photos from library")
            }

            Button {
                navigateToAnalysis = true
            } label: {
                Label("Analyze Damage", systemImage: "sparkles")
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 4)
            }
            .buttonStyle(.borderedProminent)
            .disabled(!viewModel.hasImages)
            .accessibilityLabel("Analyze damage in selected photos")
        }
    }

    // MARK: - Photo Loading

    private func loadSelectedPhotos() async {
        for item in selectedPhotoItems {
            if let data = try? await item.loadTransferable(type: Data.self),
               let image = UIImage(data: data) {
                viewModel.addImage(image)
            }
        }
        selectedPhotoItems.removeAll()
    }
}
