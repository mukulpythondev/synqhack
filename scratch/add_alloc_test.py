import json

with open('tests/test_allocator.py', 'r') as f:
    code = f.read()

code += '''
def test_already_assigned_vehicle_cannot_be_selected(test_allocator):
    """
    Confirms an already-assigned vehicle cannot be selected as replacement.
    """
    from src.models import CanonicalTicket
    ticket = CanonicalTicket(
        ticket_id="TKT-ALREADY-ASSIGNED",
        sanitized_input_snapshot={},
        origin_hub="Delhi",
        destination="Kanpur",
        issue="Engine failure",
        client_name="Internal"
    )
    
    # Run once to get the best vehicle
    best_vehicle1, citations1, why_not1 = test_allocator.allocate_replacement_vehicle(ticket, set())
    assert best_vehicle1 is not None
    
    # Run again but add it to assigned set
    best_vehicle2, citations2, why_not2 = test_allocator.allocate_replacement_vehicle(ticket, {best_vehicle1.registration_canonical})
    assert best_vehicle2 is not None
    assert best_vehicle2.registration_canonical != best_vehicle1.registration_canonical
    assert why_not2.get(best_vehicle1.registration_canonical) == "Already assigned to a concurrent active work order"
'''

with open('tests/test_allocator.py', 'w') as f:
    f.write(code)
print('Done')
