---
name: processing-images-ios
description: "iOS-native image handling — camera, photo picker, resize, compress, base64 encoding. Use when working on image capture or processing."
---

# iOS Image Processing

Handles image capture, selection, validation, and processing for the Car Crash AI iOS app.

## Photo Selection

- Use `PHPickerViewController` wrapped in `UIViewControllerRepresentable`
- Set `selectionLimit: 10` and `filter: .images`
- Handle results in the coordinator via `PHPickerViewControllerDelegate`
- Extract `UIImage` from results using `NSItemProvider.loadObject(ofClass: UIImage.self)`

## Camera Capture

- Use `UIImagePickerController` with `sourceType = .camera`
- Check availability with `UIImagePickerController.isSourceTypeAvailable(.camera)` before presenting
- On simulator (no camera available), fall back to the photo library or show an alert

## Image Validation

- Minimum resolution: 640×480
- Check `UIImage.size` (width and height in points) before processing
- Check max file size on the JPEG `Data` representation
- Reject images that don't meet requirements with a user-facing error

## Resize

- Use `UIGraphicsImageRenderer` to resize images
- Maintain aspect ratio — scale to fit within a max dimension of 1024
- Default `UIGraphicsImageRenderer` interpolation is high quality (LANCZOS equivalent)

```swift
func resized(maxDimension: CGFloat = 1024) -> UIImage {
    let ratio = min(maxDimension / size.width, maxDimension / size.height)
    guard ratio < 1 else { return self }
    let newSize = CGSize(width: size.width * ratio, height: size.height * ratio)
    let renderer = UIGraphicsImageRenderer(size: newSize)
    return renderer.image { _ in draw(in: CGRect(origin: .zero, size: newSize)) }
}
```

## JPEG Compression

- Use `UIImage.jpegData(compressionQuality: 0.9)` for output
- HEIC images from the photo library are automatically converted to JPEG by this call
- Handle the `nil` return case (rare, but possible for malformed images)

## Base64 Encoding

- Use `Data.base64EncodedString()` on the JPEG data for API transmission
- No additional encoding options needed for standard REST payloads

## Processing Pipeline

Process images in order: **validate → resize → compress → base64**.

- Return `[Data]` when sending to the Gemini SDK (binary JPEG data)
- Return `[String]` when sending to the OpenAI REST API (base64-encoded strings)

```swift
func processImages(_ images: [UIImage]) -> [Data] {
    images.compactMap { image in
        guard image.size.width >= 640, image.size.height >= 480 else { return nil }
        let resized = image.resized()
        return resized.jpegData(compressionQuality: 0.9)
    }
}
```

## Memory Management

- Wrap batch processing in `autoreleasepool` to release intermediate images promptly
- Avoid holding multiple full-resolution `UIImage` instances simultaneously
- Process one image at a time in loops, letting each go out of scope before the next

```swift
var results: [Data] = []
for image in images {
    autoreleasepool {
        if let data = processImage(image) {
            results.append(data)
        }
    }
}
```
