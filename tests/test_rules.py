"""
Unit Tests: Complete Suite for All 9 Dispatcher Tribal Knowledge Rules & Corridor Geometry
"""

from datetime import datetime, date, timedelta
import pytest

from src.models import CanonicalTicket, CanonicalVehicle, CanonicalDriver
from src.context_store import ContextStore
from src.rule_engine import RuleEngine
from src.allocator import ReplacementAllocator

@pytest.fixture
def store():
    return ContextStore()

@pytest.fixture
def rule_engine(store):
    return RuleEngine(store)

# Rule 01: Delhi NCR Winter BS6
def test_delhi_winter_bs6_rule(rule_engine):
    """
    Rule 01: Oct-Feb Delhi NCR routes require BS6 vehicles only.
    """
    winter_ticket = CanonicalTicket(
        ticket_id="TKT-WINTER-01",
        sanitized_input_snapshot={},
        created_at="2026-11-15T10:00:00",
        event_timestamp=datetime(2026, 11, 15, 10, 0, 0),
        vehicle_reg_canonical="DL41GG9786",
        driver_id="DRV-001",
        origin_hub="Delhi",
        destination="Jaipur",
        km_from_origin_hub=20.0,
        issue="engine overheating",
        severity="HIGH",
        client_name="Shakti Cement",
        is_valid=True
    )

    bs4_vehicle = CanonicalVehicle(
        vehicle_id="MF-BS4",
        registration_canonical="UP17GN7381",
        model="Truck BS4",
        year=2018,
        bs_stage="BS4",
        has_engine_heater=False,
        home_hub="Delhi",
        capacity_tonnes=20.0,
        status="Active"
    )

    bs6_vehicle = CanonicalVehicle(
        vehicle_id="MF-BS6",
        registration_canonical="UP33PG6813",
        model="Truck BS6",
        year=2023,
        bs_stage="BS6",
        has_engine_heater=True,
        home_hub="Delhi",
        capacity_tonnes=20.0,
        status="Active"
    )

    is_bs4_eligible, _, rejections_bs4 = rule_engine.evaluate_vehicle_eligibility(bs4_vehicle, winter_ticket)
    assert is_bs4_eligible is False
    assert any("BS4 vehicle prohibited on Delhi/NCR" in r for r in rejections_bs4)

    is_bs6_eligible, _, _ = rule_engine.evaluate_vehicle_eligibility(bs6_vehicle, winter_ticket)
    assert is_bs6_eligible is True

# Rule 02: Hill Route Heater & Brakes
def test_hill_route_winter_heater_and_brake_rule(rule_engine):
    """
    Rule 02: Nov-Feb Hill routes (Rudrapur/Nainital) require Engine Heater = Yes
    and zero brake work in preceding 30 days.
    """
    hill_ticket = CanonicalTicket(
        ticket_id="TKT-HILL-01",
        sanitized_input_snapshot={},
        created_at="2026-12-05T08:00:00",
        event_timestamp=datetime(2026, 12, 5, 8, 0, 0),
        vehicle_reg_canonical="UK76OD5061",
        driver_id="DRV-009",
        origin_hub="Rudrapur",
        destination="Ludhiana",
        km_from_origin_hub=15.0,
        issue="gearbox jam",
        severity="LOW",
        client_name="Shakti Cement",
        is_valid=True
    )

    no_heater_vehicle = CanonicalVehicle(
        vehicle_id="MF-NO-HEAT",
        registration_canonical="PB84TB2343",
        model="Truck",
        year=2021,
        bs_stage="BS6",
        has_engine_heater=False,
        home_hub="Rudrapur",
        capacity_tonnes=20.0,
        status="Active"
    )

    is_eligible, _, rejections = rule_engine.evaluate_vehicle_eligibility(no_heater_vehicle, hill_ticket)
    assert is_eligible is False
    assert any("requires vehicle equipped with Engine Heater" in r for r in rejections)

# Rule 03: 50km Origin Proximity
def test_origin_50km_rule(rule_engine):
    """
    Rule 03: Within 50km of origin hub, replacement MUST come from origin hub.
    """
    near_ticket = CanonicalTicket(
        ticket_id="TKT-NEAR",
        sanitized_input_snapshot={},
        created_at="2026-07-01T05:00:00",
        event_timestamp=datetime(2026, 7, 1, 5, 0, 0),
        vehicle_reg_canonical="PB74TA4257",
        driver_id="DRV-041",
        origin_hub="Ludhiana",
        destination="Kanpur",
        km_from_origin_hub=11.0,
        issue="gearbox jam",
        severity="HIGH",
        client_name="Vertex Retail",
        is_valid=True
    )

    allowed_hubs, rule_name, citations = rule_engine.determine_allowed_hubs(near_ticket)
    assert allowed_hubs == ["Ludhiana"]
    assert rule_name == "RULE_03_ORIGIN_PROXIMITY_50KM"

# Rule 04: Orion Pharma Age & Refrigeration
def test_orion_pharma_age_rule(rule_engine):
    """
    Rule 04: Orion Pharma requires vehicle manufacturing year >= 2020.
    """
    orion_ticket = CanonicalTicket(
        ticket_id="TKT-ORION-01",
        sanitized_input_snapshot={},
        created_at="2026-06-18T08:00:00",
        event_timestamp=datetime(2026, 6, 18, 8, 0, 0),
        vehicle_reg_canonical="PB31NP8886",
        driver_id="DRV-011",
        origin_hub="Ludhiana",
        destination="Kanpur",
        km_from_origin_hub=25.0,
        issue="tyre burst",
        severity="HIGH",
        client_name="Orion Pharma",
        is_valid=True
    )

    old_vehicle = CanonicalVehicle(
        vehicle_id="MF-OLD",
        registration_canonical="RJ43DD3546",
        model="Old Truck",
        year=2017,
        bs_stage="BS4",
        has_engine_heater=False,
        home_hub="Ludhiana",
        capacity_tonnes=20.0,
        status="Active"
    )

    new_vehicle = CanonicalVehicle(
        vehicle_id="MF-NEW",
        registration_canonical="HR24VR5371",
        model="New Truck",
        year=2023,
        bs_stage="BS6",
        has_engine_heater=True,
        home_hub="Ludhiana",
        capacity_tonnes=20.0,
        status="Active"
    )

    is_old_eligible, _, rejections = rule_engine.evaluate_vehicle_eligibility(old_vehicle, orion_ticket)
    assert is_old_eligible is False
    assert any("Orion Pharma requires model year >= 2020" in r for r in rejections)

    is_new_eligible, _, _ = rule_engine.evaluate_vehicle_eligibility(new_vehicle, orion_ticket)
    assert is_new_eligible is True

# Rule 05: Apex Chemicals Vehicle Rotation
def test_apex_chemicals_rotation_rule(store, rule_engine):
    """
    Rule 05: If a vehicle has an incident on an Apex run, it cannot go on immediate next Apex dispatch.
    """
    # Seed an incident for vehicle PB59PM4997 on Apex Chemicals
    store.record_apex_incident("PB59PM4997", "2026-08-11")

    apex_ticket = CanonicalTicket(
        ticket_id="TKT-APEX-01",
        sanitized_input_snapshot={},
        created_at="2026-08-12T10:00:00",
        event_timestamp=datetime(2026, 8, 12, 10, 0, 0),
        vehicle_reg_canonical="CH40IK6238",
        driver_id="DRV-031",
        origin_hub="Chandigarh",
        destination="Rudrapur",
        km_from_origin_hub=10.0,
        issue="suspension damage",
        severity="LOW",
        client_name="Apex Chemicals",
        is_valid=True
    )

    broken_apex_vehicle = CanonicalVehicle(
        vehicle_id="MF-BROKEN",
        registration_canonical="PB59PM4997",
        model="Truck",
        year=2021,
        bs_stage="BS6",
        has_engine_heater=True,
        home_hub="Chandigarh",
        capacity_tonnes=20.0,
        status="Active"
    )

    clean_vehicle = CanonicalVehicle(
        vehicle_id="MF-CLEAN",
        registration_canonical="CH10YZ3615",
        model="Truck",
        year=2022,
        bs_stage="BS6",
        has_engine_heater=True,
        home_hub="Chandigarh",
        capacity_tonnes=20.0,
        status="Active"
    )

    is_broken_eligible, _, rejections = rule_engine.evaluate_vehicle_eligibility(broken_apex_vehicle, apex_ticket)
    assert is_broken_eligible is False
    assert any("Apex rotation rule" in r for r in rejections)

    is_clean_eligible, _, _ = rule_engine.evaluate_vehicle_eligibility(clean_vehicle, apex_ticket)
    assert is_clean_eligible is True

# Rule 06: Guddu Jugaad 7-Day Limit & Home Region Confinement
def test_guddu_jugaad_7day_limit_rule(store, rule_engine):
    """
    Rule 06: Roadside jugaad by Guddu carries a 7-day clock and confines vehicle to home region.
    """
    # Insert a temporary jugaad maintenance record for HR10TK9005 in Gurgaon hub
    cursor = store.conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO maintenance (
            event_id, vehicle_canonical, event_date, odometer_km, mechanic_name,
            is_brake_work, is_jugaad_temporary, is_permanent_repair_done, sanitized_notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("MAINT-JUGAAD-01", "HR10TK9005", "2026-08-15", 190000, "Guddu", 0, 1, 0, "fan belt jugaad se chalu kiya"))
    store.conn.commit()

    jugaad_vehicle = CanonicalVehicle(
        vehicle_id="MF-JUGAAD",
        registration_canonical="HR10TK9005",
        model="Truck",
        year=2022,
        bs_stage="BS6",
        has_engine_heater=True,
        home_hub="Gurgaon",
        capacity_tonnes=20.0,
        status="Active"
    )

    # Dispatch to DIFFERENT hub outside home region (e.g. Kanpur) on day 3
    ticket_outside = CanonicalTicket(
        ticket_id="TKT-JUG-01",
        sanitized_input_snapshot={},
        created_at="2026-08-18T10:00:00",
        event_timestamp=datetime(2026, 8, 18, 10, 0, 0),
        vehicle_reg_canonical="DL64IB1058",
        driver_id="DRV-001",
        origin_hub="Gurgaon",
        destination="Kanpur",
        km_from_origin_hub=20.0,
        issue="radiator leak",
        severity="MEDIUM",
        client_name="Internal",
        is_valid=True
    )

    is_eligible, _, rejections = rule_engine.evaluate_vehicle_eligibility(jugaad_vehicle, ticket_outside)
    assert is_eligible is False
    assert any("Active Guddu jugaad patch" in r for r in rejections)

# Rule 07: Driver Night Solo Restriction
def test_driver_night_solo_rule(store, rule_engine):
    """
    Rule 07: Drivers with <6 months tenure cannot drive solo on night runs (20:00-06:00).
    """
    # DRV-011 joined on 2026-07-10 (tenure < 6 months on 2026-08-01)
    night_ticket = CanonicalTicket(
        ticket_id="TKT-NIGHT-01",
        sanitized_input_snapshot={},
        created_at="2026-08-01T02:30:00",
        event_timestamp=datetime(2026, 8, 1, 2, 30, 0),
        vehicle_reg_canonical="PB31NP8886",
        driver_id="DRV-011",
        origin_hub="Ludhiana",
        destination="Kanpur",
        km_from_origin_hub=20.0,
        issue="engine overheating",
        severity="HIGH",
        client_name="Internal",
        is_valid=True
    )

    is_compliant, action_msg, citations = rule_engine.evaluate_driver_safety(night_ticket)
    assert is_compliant is False
    assert "Solo night run prohibited" in action_msg
    assert any("dispatcher_interview.txt" in c for c in citations)

# Rule 08: Service Overdue & Grounding
def test_service_overdue_and_grounded_rule(rule_engine):
    """
    Rule 08: Any vehicle marked Grounded/Inactive or with critical unresolved faults is grounded.
    """
    grounded_vehicle = CanonicalVehicle(
        vehicle_id="MF-GROUNDED",
        registration_canonical="HR59KV7624",
        model="Truck",
        year=2021,
        bs_stage="BS6",
        has_engine_heater=True,
        home_hub="Delhi",
        capacity_tonnes=20.0,
        status="Grounded",
        has_unaddressed_critical_fault=True
    )

    normal_ticket = CanonicalTicket(
        ticket_id="TKT-NORM",
        sanitized_input_snapshot={},
        created_at="2026-05-01T10:00:00",
        event_timestamp=datetime(2026, 5, 1, 10, 0, 0),
        vehicle_reg_canonical="UP40IM3144",
        driver_id="DRV-001",
        origin_hub="Delhi",
        destination="Jaipur",
        km_from_origin_hub=20.0,
        issue="flat tyre",
        severity="LOW",
        client_name="Internal",
        is_valid=True
    )

    is_eligible, _, rejections = rule_engine.evaluate_vehicle_eligibility(grounded_vehicle, normal_ticket)
    assert is_eligible is False
    assert any("Grounded/Inactive" in r for r in rejections)

# Rule 09: Monsoon East-of-Lucknow Buffer
def test_monsoon_east_of_lucknow_eta_rule(rule_engine):
    """
    Rule 09: July-September dispatches to eastern centers beyond Lucknow get +20% ETA buffer upfront.
    """
    monsoon_ticket = CanonicalTicket(
        ticket_id="TKT-MONSOON-01",
        sanitized_input_snapshot={},
        created_at="2026-08-10T14:00:00",
        event_timestamp=datetime(2026, 8, 10, 14, 0, 0),
        vehicle_reg_canonical="UP40IM3144",
        driver_id="DRV-001",
        origin_hub="Lucknow",
        destination="Gorakhpur",
        km_from_origin_hub=20.0,
        issue="fuel line leak",
        severity="HIGH",
        client_name="Shakti Cement",
        is_valid=True
    )

    sla_desc, effective_eta, citations = rule_engine.evaluate_client_sla_and_eta(monsoon_ticket, base_osrm_hours=10.0)
    assert effective_eta == 12.0  # 10.0 * 1.20 = 12.0 hours (+20% buffer)
    assert "Monsoon +20% Buffer Applied" in sla_desc
    assert any("thread_23_internal_monsoon.txt" in c for c in citations)
