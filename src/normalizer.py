"""
Meridian Freight Breakdown Automation
Entity Normalization, Date Parsing, and Canonical Mapping
"""

import re
from datetime import datetime
from typing import Optional, Tuple
from src.config import CLIENT_METADATA, HUB_COORDINATES

# Regex for standard Indian Commercial Vehicle plates
REG_PLATE_REGEX = re.compile(r'^[A-Z]{2}\d{1,2}[A-Z]{1,3}\d{4}$')

CLIENT_ALIASES = {
    "shakti cement": "Shakti Cement",
    "shakti": "Shakti Cement",
    "shakticement": "Shakti Cement",
    "shakti cements": "Shakti Cement",
    "vertex retail": "Vertex Retail",
    "vertex": "Vertex Retail",
    "vertexretail": "Vertex Retail",
    "apex chemicals": "Apex Chemicals",
    "apex": "Apex Chemicals",
    "apexchem": "Apex Chemicals",
    "apex chemical": "Apex Chemicals",
    "orion pharma": "Orion Pharma",
    "orion": "Orion Pharma",
    "orionpharma": "Orion Pharma",
    "internal": "Internal",
    "meridian internal": "Internal",
    "meridian": "Internal",
}

def normalize_vehicle_reg(raw_reg: Optional[str]) -> Tuple[str, bool]:
    """
    Normalizes vehicle registration numbers:
    - Strips whitespace, hyphens, special characters
    - Converts to uppercase
    - Validates against standard plate structure
    Returns: (canonical_plate, is_valid_syntax)
    """
    if not raw_reg or not isinstance(raw_reg, str):
        return "", False
    
    cleaned = re.sub(r'[^A-Za-z0-9]', '', raw_reg).upper()
    if not cleaned or "UNKNOWN" in cleaned or "?" in raw_reg:
        return cleaned, False
    
    is_valid = bool(REG_PLATE_REGEX.match(cleaned))
    return cleaned, is_valid

def normalize_client_name(raw_client: Optional[str]) -> Tuple[str, str]:
    """
    Resolves client names to canonical identifiers:
    Returns: (canonical_name, confidence_state)
    Confidence states: 'HIGH_CONFIDENCE' | 'AMBIGUOUS' | 'UNRESOLVED'
    """
    if not raw_client or not isinstance(raw_client, str):
        return "UNKNOWN_CLIENT", "UNRESOLVED"
    
    key = raw_client.strip().lower()
    if key in CLIENT_ALIASES:
        return CLIENT_ALIASES[key], "HIGH_CONFIDENCE"
    
    # Partial substring check
    for alias, canonical in CLIENT_ALIASES.items():
        if alias in key or key in alias:
            return canonical, "HIGH_CONFIDENCE"
    
    return raw_client.strip(), "UNRESOLVED"

def normalize_hub_name(raw_hub: Optional[str]) -> Optional[str]:
    """
    Resolves a hub name against the 9 primary Meridian hubs.
    """
    if not raw_hub or not isinstance(raw_hub, str):
        return None
    
    clean = raw_hub.strip().title()
    for canonical in HUB_COORDINATES.keys():
        if clean.lower() == canonical.lower():
            return canonical
    return None

def parse_iso_datetime(date_str: Optional[str]) -> Tuple[Optional[datetime], Optional[str]]:
    """
    Deterministic ISO-8601 timestamp parser.
    Returns: (datetime_obj, error_reason)
    """
    if not date_str or not isinstance(date_str, str):
        return None, "Date string is missing or null"
    
    # Common ISO formats
    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d",
    ]
    
    clean_str = date_str.strip()
    for fmt in formats:
        try:
            return datetime.strptime(clean_str, fmt), None
        except ValueError:
            continue
    
    # Handle milliseconds if present
    try:
        if "T" in clean_str:
            clean_part = clean_str.split(".")[0]
            return datetime.strptime(clean_part, "%Y-%m-%dT%H:%M:%S"), None
    except Exception:
        pass
        
    return None, f"Unparseable date format: '{date_str}'"
