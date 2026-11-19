"""The labelling tool page renders (#15)."""

from pathlib import Path

import pytest

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

APP = Path(__file__).parents[3] / "frontend" / "labelling_app.py"


def test_labelling_tool_renders_without_errors() -> None:
    app = AppTest.from_file(str(APP), default_timeout=30).run()

    assert not app.exception
    assert app.title[0].value == "🏷️ Label an eval case"
    assert app.button[0].disabled  # no photos yet
