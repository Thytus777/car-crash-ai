import Foundation

enum VehiclePrompts {
    static let identification = """
    Analyze the provided images of a vehicle. Identify the vehicle with the \
    following details. Return ONLY valid JSON, no other text.

    {
      "make": "string (manufacturer, e.g. Toyota)",
      "model": "string (e.g. Camry)",
      "year": integer,
      "body_style": "string (sedan, SUV, truck, coupe, hatchback, van, wagon)",
      "color": "string",
      "confidence": float 0.0-1.0 (how confident you are in this identification)
    }

    If the vehicle is too damaged to identify confidently, set confidence below 0.7 \
    and provide your best guess. If multiple vehicles are visible, identify the most \
    prominently damaged one.
    """
}
