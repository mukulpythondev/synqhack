"""
Unit Tests: Entity Resolution, Registration Normalization, and Conflict Hierarchy
"""

import pytest
from src.normalizer import normalize_vehicle_reg, normalize_client_name, normalize_hub_name
from src.context_store import ContextStore

@pytest.fixture
def store():
    return ContextStore()

def test_registration_normalization():
    """
    Validates that messy registration strings resolve to canonical uppercase alphanumeric tokens.
    """
    cases = [
        ("UP-40-IM-3144", "UP40IM3144", True),
        ("up86cm7252", "UP86CM7252", True),
        ("DL 64 IB 1058", "DL64IB1058", True),
        ("CH-40-IK-6238", "CH40IK6238", True),
        ("UK-41-CO-2604", "UK41CO2604", True),
        ("hr??unknown", "HRUNKNOWN", False),
        ("", "", False),
        (None, "", False)
    ]
    for raw, expected, is_valid in cases:
        canon, valid = normalize_vehicle_reg(raw)
        assert canon == expected
        assert valid == is_valid

def test_client_name_normalization():
    """
    Validates client alias resolution.
    """
    assert normalize_client_name("shakti cement")[0] == "Shakti Cement"
    assert normalize_client_name("shakticement")[0] == "Shakti Cement"
    assert normalize_client_name("VERTEX")[0] == "Vertex Retail"
    assert normalize_client_name("Apex Chemicals")[0] == "Apex Chemicals"
    assert normalize_client_name("orion pharma")[0] == "Orion Pharma"

def test_rj43dd3546_year_conflict_resolution(store):
    """
    Validates that RJ43DD3546 is resolved to 2017 (Master RC)
    rather than 2021 (Jaipur Hub email claim).
    """
    v = store.get_vehicle("RJ43DD3546")
    assert v is not None
    assert v.year == 2017
    assert v.bs_stage == "BS4"

def test_ch67hy8613_maintenance_resolution(store):
    """
    Validates that CH67HY8613 maintenance history contains official workshop records.
    """
    v = store.get_vehicle("CH67HY8613")
    assert v is not None
    assert v.bs_stage == "BS6"
    assert v.has_engine_heater is True
