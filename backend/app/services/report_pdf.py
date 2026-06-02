"""PDF report generation from AssessmentReport.

Uses Jinja2 to render an HTML template, then WeasyPrint to convert to PDF.
Falls back to returning raw HTML bytes if WeasyPrint is not available
(so the endpoint still works in dev without system PDF libs).
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from app.models.estimate import AssessmentReport

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
_jinja_env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)


def render_report_html(
    report: AssessmentReport,
    upload_id: str = "",
    estimate_id: int | None = None,
) -> str:
    """Render the report as an HTML string."""
    template = _jinja_env.get_template("report.html")
    return template.render(
        report_date=datetime.now(timezone.utc).strftime("%d %B %Y"),
        upload_id=upload_id,
        estimate_id=estimate_id,
        vehicle=report.vehicle,
        damages=report.damage_assessment.damages,
        quality_warnings=report.damage_assessment.image_quality_warnings,
        angle_guidance=report.damage_assessment.angle_guidance,
        assessment_warnings=report.assessment_warnings,
        cost_estimates=report.cost_estimates,
        totals=report.totals,
        assessment_method=report.damage_assessment.assessment_method,
        disclaimer=report.disclaimer,
    )


def generate_pdf(
    report: AssessmentReport,
    upload_id: str = "",
    estimate_id: int | None = None,
) -> bytes:
    """Render the report to PDF bytes. Falls back to HTML if WeasyPrint fails."""
    html_str = render_report_html(report, upload_id=upload_id, estimate_id=estimate_id)

    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html_str).write_pdf()
        logger.info("PDF generated (%d bytes)", len(pdf_bytes))
        return pdf_bytes
    except Exception:
        logger.warning("WeasyPrint not available — returning HTML instead of PDF")
        return html_str.encode("utf-8")
