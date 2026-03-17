import Foundation

enum Components {
    static let all: [String] = [
        "front_bumper", "rear_bumper", "hood", "trunk", "grille",
        "headlight_left", "headlight_right", "taillight_left", "taillight_right",
        "fender_front_left", "fender_front_right",
        "door_front_left", "door_front_right", "door_rear_left", "door_rear_right",
        "mirror_left", "mirror_right",
        "quarter_panel_left", "quarter_panel_right",
        "rocker_panel_left", "rocker_panel_right",
        "windshield_front", "windshield_rear",
        "roof", "a_pillar_left", "a_pillar_right", "b_pillar_left", "b_pillar_right",
        "wheel_front_left", "wheel_front_right", "wheel_rear_left", "wheel_rear_right",
    ]

    static var allNames: String {
        all.joined(separator: ", ")
    }

    static func displayName(_ component: String) -> String {
        component
            .replacingOccurrences(of: "_", with: " ")
            .capitalized
    }
}
