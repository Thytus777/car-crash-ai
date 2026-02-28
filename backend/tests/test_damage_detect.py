import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.damage_detect import _parse_damage_response, detect_damage


def test_parse_valid_damage_response() -> None:
    raw = json.dumps(
        [
            {
                "component": "front_bumper",
                "damage_type": "crush",
                "severity": 0.75,
                "description": "Crushed inward with cracking",
            },
            {
                "component": "headlight_left",
                "damage_type": "shatter",
                "severity": 0.9,
                "description": "Shattered lens",
            },
        ]
    )
    items = _parse_damage_response(raw)
    assert len(items) == 2
    assert items[0].component == "front_bumper"
    assert items[0].severity == 0.75
    assert items[0].recommendation == "replace"
    assert items[1].recommendation == "replace"


def test_parse_low_severity_gets_repair() -> None:
    raw = json.dumps(
        [
            {
                "component": "door_front_left",
                "damage_type": "scratch",
                "severity": 0.15,
                "description": "Light scratch on paint",
            },
        ]
    )
    items = _parse_damage_response(raw)
    assert items[0].recommendation == "repair"


def test_parse_unknown_component_skipped() -> None:
    raw = json.dumps(
        [
            {
                "component": "imaginary_part",
                "damage_type": "dent",
                "severity": 0.5,
                "description": "Test",
            },
            {
                "component": "hood",
                "damage_type": "dent",
                "severity": 0.4,
                "description": "Dented hood",
            },
        ]
    )
    items = _parse_damage_response(raw)
    assert len(items) == 1
    assert items[0].component == "hood"


def test_parse_severity_clamped() -> None:
    raw = json.dumps(
        [
            {
                "component": "roof",
                "damage_type": "crush",
                "severity": 1.5,
                "description": "Over max",
            },
        ]
    )
    items = _parse_damage_response(raw)
    assert items[0].severity == 1.0


def test_parse_with_code_fences() -> None:
    raw = '```json\n[{"component": "grille", "damage_type": "crack", "severity": 0.6, "description": "Cracked"}]\n```'
    items = _parse_damage_response(raw)
    assert len(items) == 1
    assert items[0].component == "grille"


@pytest.mark.asyncio
async def test_detect_damage_calls_openai() -> None:
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content=json.dumps(
                    [
                        {
                            "component": "rear_bumper",
                            "damage_type": "deformation",
                            "severity": 0.65,
                            "description": "Rear bumper pushed in",
                        }
                    ]
                )
            )
        )
    ]

    with (
        patch(
            "app.services.damage_detect.load_images_as_base64",
            return_value=["fake_b64"],
        ),
        patch("app.services.damage_detect.AsyncOpenAI") as mock_client_cls,
    ):
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = await detect_damage("test_upload_id")

    assert len(result.damages) == 1
    assert result.damages[0].component == "rear_bumper"
    assert result.damages[0].recommendation == "replace"
