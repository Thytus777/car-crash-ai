import Foundation

enum DamagePrompts {
    static let assessment = """
    Analyze the provided images of a damaged vehicle. Identify ALL visible \
    damage to the vehicle components.

    For each damaged component, provide:
    - component: use ONLY names from this list: [\(Components.allNames)]
    - damage_type: one of [scratch, dent, crack, shatter, crush, deformation, missing]
    - severity: float from 0.0 to 1.0 where:
      - 0.0-0.1: cosmetic only (light scratch, scuff)
      - 0.1-0.3: minor (small dent, paint chip, repairable)
      - 0.3-0.6: moderate (significant dent, crack, replacement recommended)
      - 0.6-0.8: severe (large deformation, shattered, replacement required)
      - 0.8-1.0: destroyed (component non-functional/missing)
    - description: brief description of the damage observed

    Return ONLY valid JSON array, no other text:
    [
      {
        "component": "front_bumper",
        "damage_type": "crush",
        "severity": 0.75,
        "description": "Front bumper is crushed inward with paint transfer and cracking"
      }
    ]

    If no damage is visible, return an empty array: []
    """

    static func priceExtraction(vehicle: Vehicle, component: String) -> String {
        """
        Given the following product page text, extract pricing info \
        for the car part: \(vehicle.year) \(vehicle.make) \(vehicle.model) \(component).

        Return ONLY valid JSON:
        {
          "price": number or null if not found,
          "currency": "USD",
          "part_type": "oem" or "aftermarket" or "unknown",
          "confidence": 0.0 to 1.0
        }
        """
    }

    static func aiPriceEstimate(vehicle: Vehicle, component: String) -> String {
        """
        Estimate the replacement cost for a \(vehicle.year) \(vehicle.make) \
        \(vehicle.model) \(Components.displayName(component)).

        Consider that this is a \(vehicle.bodyStyle ?? "standard") vehicle. \
        Provide a realistic price range based on typical aftermarket parts.

        Return ONLY valid JSON:
        {
          "price_low": number,
          "price_avg": number,
          "price_high": number,
          "currency": "USD",
          "confidence": 0.0 to 1.0
        }
        """
    }
}
