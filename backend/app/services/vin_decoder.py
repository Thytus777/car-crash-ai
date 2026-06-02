"""VIN decoder using the free NHTSA vPIC API.

No API key required. Returns Vehicle with confirmed make/model/year/trim.
Raises VINDecodeError on invalid VIN, network failure, or unrecognised result.
"""

import logging

import httpx

from app.models.vehicle import Vehicle

logger = logging.getLogger(__name__)

_NHTSA_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/decodevinvalues/{vin}?format=json"
_TIMEOUT = 8.0


class VINDecodeError(Exception):
    pass


async def decode_vin(vin: str) -> Vehicle:
    """Decode a 17-character VIN via NHTSA vPIC API.

    Returns a Vehicle model with confidence=1.0.
    Raises VINDecodeError if the VIN is invalid or the response is unusable.
    """
    vin = vin.strip().upper()
    if len(vin) != 17:
        raise VINDecodeError(f"VIN must be 17 characters, got {len(vin)}")

    url = _NHTSA_URL.format(vin=vin)
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        raise VINDecodeError(f"NHTSA API request failed: {exc}") from exc

    results = data.get("Results", [])
    if not results:
        raise VINDecodeError("NHTSA returned no results")

    r = results[0]

    # Check for NHTSA error codes
    error_code = r.get("ErrorCode", "0")
    if error_code not in ("0", ""):
        raise VINDecodeError(
            f"NHTSA decode error {error_code}: {r.get('ErrorText', 'unknown')}"
        )

    make = r.get("Make", "").strip()
    model = r.get("Model", "").strip()
    year_raw = r.get("ModelYear", "").strip()
    trim = r.get("Trim", "").strip() or None
    body_style = _normalise_body_style(r.get("BodyClass", ""))

    if not make or not model or not year_raw:
        raise VINDecodeError("NHTSA response missing make, model, or year")

    try:
        year = int(year_raw)
    except ValueError as exc:
        raise VINDecodeError(f"Invalid model year from NHTSA: {year_raw!r}") from exc

    logger.info("VIN %s decoded: %d %s %s %s", vin, year, make, model, trim or "")

    return Vehicle(
        make=make,
        model=model,
        year=year,
        trim=trim,
        body_style=body_style,
        confidence=1.0,
        vin=vin,
    )


def _normalise_body_style(raw: str) -> str | None:
    raw = raw.lower()
    mapping = {
        "sedan": "sedan",
        "suv": "suv",
        "sport utility": "suv",
        "truck": "truck",
        "pickup": "truck",
        "coupe": "coupe",
        "hatchback": "hatchback",
        "van": "van",
        "wagon": "wagon",
        "convertible": "convertible",
    }
    for key, value in mapping.items():
        if key in raw:
            return value
    return None
