"""Labor cost estimation — static lookup table of labor hours per component."""

from decimal import Decimal

from app.core.config import settings

LABOR_HOURS: dict[str, tuple[Decimal, Decimal]] = {
    "front_bumper": (Decimal("3.0"), Decimal("4.0")),
    "rear_bumper": (Decimal("3.0"), Decimal("4.0")),
    "hood": (Decimal("2.0"), Decimal("3.0")),
    "trunk": (Decimal("2.5"), Decimal("4.0")),
    "grille": (Decimal("0.5"), Decimal("1.0")),
    "headlight_left": (Decimal("0.5"), Decimal("1.5")),
    "headlight_right": (Decimal("0.5"), Decimal("1.5")),
    "taillight_left": (Decimal("0.5"), Decimal("1.0")),
    "taillight_right": (Decimal("0.5"), Decimal("1.0")),
    "fender_front_left": (Decimal("3.0"), Decimal("5.0")),
    "fender_front_right": (Decimal("3.0"), Decimal("5.0")),
    "door_front_left": (Decimal("4.0"), Decimal("6.0")),
    "door_front_right": (Decimal("4.0"), Decimal("6.0")),
    "door_rear_left": (Decimal("4.0"), Decimal("6.0")),
    "door_rear_right": (Decimal("4.0"), Decimal("6.0")),
    "mirror_left": (Decimal("0.5"), Decimal("1.0")),
    "mirror_right": (Decimal("0.5"), Decimal("1.0")),
    "quarter_panel_left": (Decimal("6.0"), Decimal("10.0")),
    "quarter_panel_right": (Decimal("6.0"), Decimal("10.0")),
    "rocker_panel_left": (Decimal("3.0"), Decimal("5.0")),
    "rocker_panel_right": (Decimal("3.0"), Decimal("5.0")),
    "windshield_front": (Decimal("1.5"), Decimal("2.5")),
    "windshield_rear": (Decimal("1.5"), Decimal("2.5")),
    "roof": (Decimal("6.0"), Decimal("10.0")),
    "a_pillar_left": (Decimal("4.0"), Decimal("8.0")),
    "a_pillar_right": (Decimal("4.0"), Decimal("8.0")),
    "b_pillar_left": (Decimal("4.0"), Decimal("8.0")),
    "b_pillar_right": (Decimal("4.0"), Decimal("8.0")),
    "wheel_front_left": (Decimal("0.5"), Decimal("1.0")),
    "wheel_front_right": (Decimal("0.5"), Decimal("1.0")),
    "wheel_rear_left": (Decimal("0.5"), Decimal("1.0")),
    "wheel_rear_right": (Decimal("0.5"), Decimal("1.0")),
}

DEFAULT_HOURS = (Decimal("2.0"), Decimal("4.0"))


def get_labor_hours(component: str) -> Decimal:
    """Return average labor hours for a component."""
    low, high = LABOR_HOURS.get(component, DEFAULT_HOURS)
    return (low + high) / 2


def get_labor_cost(component: str) -> tuple[Decimal, Decimal, Decimal]:
    """Return (labor_hours, labor_rate, labor_cost) for a component."""
    hours = get_labor_hours(component)
    rate = Decimal(str(settings.labor_rate_per_hour))
    cost = (hours * rate).quantize(Decimal("0.01"))
    return hours, rate, cost
