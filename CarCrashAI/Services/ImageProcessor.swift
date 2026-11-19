import Foundation
import UIKit
import CoreGraphics

// MARK: - ImageProcessor

enum ImageProcessor {
    static let targetSize = CGSize(width: 1024, height: 1024)
    static let minimumSize = CGSize(width: 640, height: 480)
    static let maxFileSizeBytes = 20 * 1024 * 1024 // 20 MB
    static let jpegQuality: CGFloat = 0.85

    // MARK: - Validation

    enum ImageError: Error, LocalizedError {
        case tooSmall(width: Int, height: Int)
        case fileTooLarge(bytes: Int)
        case compressionFailed

        var errorDescription: String? {
            switch self {
            case .tooSmall(let w, let h):
                "Image too small (\(w)×\(h)). Minimum is \(Int(minimumSize.width))×\(Int(minimumSize.height))."
            case .fileTooLarge(let bytes):
                "Image too large (\(bytes / 1_048_576) MB). Maximum is \(maxFileSizeBytes / 1_048_576) MB."
            case .compressionFailed:
                "Failed to compress image to JPEG."
            }
        }
    }

    static func validate(_ image: UIImage) throws {
        let size = image.size
        if size.width < minimumSize.width || size.height < minimumSize.height {
            throw ImageError.tooSmall(width: Int(size.width), height: Int(size.height))
        }
    }

    // MARK: - Processing

    static func process(_ image: UIImage) throws -> Data {
        try validate(image)

        let resized = resize(image, to: targetSize)
        guard let jpegData = resized.jpegData(compressionQuality: jpegQuality) else {
            throw ImageError.compressionFailed
        }

        if jpegData.count > maxFileSizeBytes {
            throw ImageError.fileTooLarge(bytes: jpegData.count)
        }

        return jpegData
    }

    static func processMultiple(_ images: [UIImage]) throws -> [Data] {
        try images.map { try process($0) }
    }

    // MARK: - Resize

    static func resize(_ image: UIImage, to targetSize: CGSize) -> UIImage {
        let size = image.size
        let widthRatio = targetSize.width / size.width
        let heightRatio = targetSize.height / size.height
        let ratio = min(widthRatio, heightRatio)

        if ratio >= 1.0 { return image }

        let newSize = CGSize(width: size.width * ratio, height: size.height * ratio)
        let renderer = UIGraphicsImageRenderer(size: newSize)
        return renderer.image { _ in
            image.draw(in: CGRect(origin: .zero, size: newSize))
        }
    }
}
