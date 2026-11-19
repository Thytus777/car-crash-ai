from decimal import Decimal

from app.models.damage import DamageAssessment, DamageItem
from app.models.estimate import AssessmentReport, CostEstimate, ReportTotals
from app.models.vehicle import Vehicle
from app.services.report_pdf import render_report_html


def test_unpriced_components_render_as_unpriced_not_zero() -> None:
    zero = Decimal("0.00")
    labor = Decimal("100.00")
    report = AssessmentReport(
        vehicle=Vehicle(make="Ferrari", model="F40", year=1990),
        damage_assessment=DamageAssessment(
            damages=[
                DamageItem(
                    component="hood",
                    damage_type="crush",
                    severity=0.9,
                    description="Destroyed",
                    recommendation="replace",
                )
            ]
        ),
        cost_estimates=[
            CostEstimate(
                component="hood",
                recommendation="replace",
                part_cost_low=None,
                part_cost_avg=None,
                part_cost_high=None,
                pricing_method="unpriced",
                labor_hours=Decimal("2.5"),
                labor_rate=Decimal("40.00"),
                labor_cost=labor,
                total_low=None,
                total_avg=None,
                total_high=None,
            )
        ],
        totals=ReportTotals(
            parts_total=zero,
            labor_total=labor,
            grand_total=labor,
            unpriced_components=["hood"],
        ),
    )

    html = render_report_html(report)

    assert "Unpriced" in html
    assert html.count("<td>—</td>") == 3  # low / avg / high part cost
    assert "excludes unpriced: hood" in html
