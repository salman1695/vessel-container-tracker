# Connect with safecube Carrier & SCAC Resolver
import re
from typing import Optional

# User-friendly Carrier Names / Aliases -> Standard 4-Letter SCAC Codes
CARRIER_NAME_TO_SCAC = {
    "COSCO": "COSU",
    "COSCO SHIPPING": "COSU",
    "MAERSK": "MAEU",
    "MAERSK LINE": "MAEU",
    "MSC": "MSCU",
    "MEDITERRANEAN SHIPPING COMPANY": "MSCU",
    "CMA": "CMDU",
    "CMA CGM": "CMDU",
    "HAPAG": "HLCU",
    "HAPAG-LLOYD": "HLCU",
    "HAPAG LLOYD": "HLCU",
    "ONE": "ONEY",
    "OCEAN NETWORK EXPRESS": "ONEY",
    "EVERGREEN": "EGLV",
    "EVERGREEN LINE": "EGLV",
    "HMM": "HDMU",
    "HYUNDAI MERCHANT MARINE": "HDMU",
    "YANG MING": "YMLU",
    "ZIM": "ZIMU",
    "OOCL": "OOLU",
    "ORIENT OVERSEAS CONTAINER LINE": "OOLU",
    "WAN HAI": "WHLC",
    "PIL": "PCIU",
    "PACIFIC INTERNATIONAL LINES": "PCIU",
    "KMTC": "KMTC",
}

VALID_SCAC_CODES = set(CARRIER_NAME_TO_SCAC.values())


def resolve_sealine(sealine_input: Optional[str]) -> Optional[str]:
    """
    Carrier name ya SCAC code ko valid Safecube SCAC code mein convert karta hai.
    Invalid / unmapped lamba naam aane par None return karta hai taake 400 Bad Request na aaye.
    """
    if not sealine_input or not sealine_input.strip():
        return None

    cleaned = re.sub(r"\s+", " ", sealine_input.strip().upper())

    # 1. Exact match in dictionary
    if cleaned in CARRIER_NAME_TO_SCAC:
        return CARRIER_NAME_TO_SCAC[cleaned]

    # 2. Partial match (e.g., "COSCO SHIPPING LINES" -> "COSU")
    for name_key, scac in CARRIER_NAME_TO_SCAC.items():
        if name_key in cleaned or cleaned in name_key:
            return scac

    # 3. Valid SCAC format check (typically 2 to 4 uppercase alphanumeric chars, no spaces)
    if re.match(r"^[A-Z0-9]{2,4}$", cleaned):
        return cleaned

    return None