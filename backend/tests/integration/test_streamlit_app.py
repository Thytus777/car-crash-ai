"""The Streamlit demo script runs (#4)."""

from pathlib import Path

import pytest

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

APP = Path(__file__).parents[3] / "frontend" / "streamlit_app.py"


def test_demo_renders_without_errors() -> None:
    app = AppTest.from_file(str(APP), default_timeout=30).run()

    assert not app.exception
    assert app.title[0].value == "🚗 Car Crash Damage Assessment"
    assert app.button[0].disabled  # nothing uploaded yet
