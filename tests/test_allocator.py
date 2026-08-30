import pytest
from src.context_store import ContextStore
from src.rule_engine import RuleEngine
from src.allocator import ReplacementAllocator
from src.models import CanonicalTicket, CanonicalVehicle

@pytest.fixture
def test_allocator():
    store = ContextStore()
    rule_engine = RuleEngine(store)
    return ReplacementAllocator(store, rule_engine)

def test_already_assigned_vehicle_cannot_be_selected(test_allocator):
    """
    Confirms an already-assigned vehicle cannot be selected as replacement.
    """
    from datetime import datetime, timezone
    ticket = CanonicalTicket(
        ticket_id="TKT-ALREADY-ASSIGNED",
        sanitized_input_snapshot={},
        origin_hub="Delhi",
        destination="Kanpur",
        issue="Engine failure",
        client_name="Internal",
        vehicle_reg_canonical="DL30JD1420",
        is_valid=True,
        created_at="2026-08-30T10:00:00Z",
        event_timestamp=datetime(2026, 8, 30, 10, 0, tzinfo=timezone.utc),
        driver_id="DRV-001",
        km_from_origin_hub=0.0,
        severity="HIGH"
    )
    
    # Run once to get the best vehicle
    best_vehicle1, citations1, why_not1 = test_allocator.allocate_replacement_vehicle(ticket, set())
    assert best_vehicle1 is not None
    
    # Run again but add it to assigned set
    best_vehicle2, citations2, why_not2 = test_allocator.allocate_replacement_vehicle(ticket, {best_vehicle1.registration_canonical})
    assert best_vehicle2 is not None
    assert best_vehicle2.registration_canonical != best_vehicle1.registration_canonical
    assert why_not2.get(best_vehicle1.registration_canonical) == "Already assigned to a concurrent active work order"
