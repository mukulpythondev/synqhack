"""
Meridian Freight Breakdown Automation
Replacement Vehicle Allocation Engine with Decoupled Allowed Hubs & Deterministic 3-Tier Ranking
"""

from typing import Optional, List, Dict, Any, Tuple
from src.config import HUB_DISTANCE_MATRIX, HUB_COORDINATES
from src.models import CanonicalTicket, CanonicalVehicle
from src.context_store import ContextStore
from src.rule_engine import RuleEngine

class ReplacementAllocator:
    """
    Deterministic Replacement Vehicle Allocator.
    Decouples Allowed-Hub constraints from ranking.
    Provides complete 'Why Not' transparency for every candidate considered.
    """

    def __init__(self, context_store: ContextStore, rule_engine: RuleEngine):
        self.store = context_store
        self.rule_engine = rule_engine

    def get_hubs_by_proximity(self, reference_hub: str) -> List[str]:
        """
        Returns all hubs sorted by highway road distance from reference_hub.
        """
        hub_distances = []
        for hub in HUB_COORDINATES.keys():
            if hub == reference_hub:
                hub_distances.append((0.0, hub))
            else:
                dist = HUB_DISTANCE_MATRIX.get((reference_hub, hub), 999.0)
                hub_distances.append((dist, hub))
        
        hub_distances.sort(key=lambda x: x[0])
        return [h[1] for h in hub_distances]

    def allocate_replacement_vehicle(
        self,
        ticket: CanonicalTicket,
        currently_assigned_regs: set
    ) -> Tuple[Optional[CanonicalVehicle], List[str], Dict[str, str]]:
        """
        Allocates the single best replacement vehicle deterministically.
        Returns: (selected_vehicle, citations, why_not_matrix)
        """
        why_not_matrix: Dict[str, str] = {}
        citations: List[str] = []

        # Phase 1: Determine Allowed Hubs (Rule 03)
        allowed_hubs, hub_rule, hub_citations = self.rule_engine.determine_allowed_hubs(ticket)
        citations.extend(hub_citations)

        if allowed_hubs == ["ALL_HUBS_BY_DISTANCE"]:
            ordered_hubs = self.get_hubs_by_proximity(ticket.origin_hub)
        else:
            ordered_hubs = allowed_hubs

        eligible_candidates: List[Tuple[float, CanonicalVehicle]] = []

        # Phase 2: Evaluate Vehicles across Ordered Hubs
        for hub_idx, hub_name in enumerate(ordered_hubs):
            hub_distance = 0.0 if hub_name == ticket.origin_hub else HUB_DISTANCE_MATRIX.get((ticket.origin_hub, hub_name), 999.0)
            hub_vehicles = self.store.get_all_vehicles_in_hub(hub_name)

            for vehicle in hub_vehicles:
                reg = vehicle.registration_canonical

                # Check if already allocated to another active work order in this run
                if reg in currently_assigned_regs:
                    why_not_matrix[reg] = "Already assigned to a concurrent active work order"
                    continue

                # Evaluate Hard Constraints per Dispatcher Rules
                is_eligible, rules_applied, rejections = self.rule_engine.evaluate_vehicle_eligibility(vehicle, ticket)
                
                if not is_eligible:
                    why_not_matrix[reg] = f"Rejected: {'; '.join(rejections)}"
                else:
                    eligible_candidates.append((hub_distance, vehicle))

            # If we are restricted strictly to Origin Hub, stop after evaluating origin hub
            if allowed_hubs != ["ALL_HUBS_BY_DISTANCE"]:
                break
            
            # If we found eligible candidates in the nearest hub, we don't need to search further away
            if eligible_candidates:
                break

        if not eligible_candidates:
            return None, citations, why_not_matrix

        # Phase 3: Deterministic Ranking & Tie-Breaking
        # Tie-Breaking Hierarchy:
        # Tier 1: Hub Road Distance to origin (lowest km)
        # Tier 2: Capacity (closest capacity >= 20.0 tonnes)
        # Tier 3: Model Year (newest model year preferred)
        # Tier 4: Stable Alphabetical Registration Plate (100% deterministic reproducibility)
        
        def ranking_key(item: Tuple[float, CanonicalVehicle]):
            hub_dist, v = item
            cap = float(v.capacity_tonnes) if v.capacity_tonnes is not None else 20.0
            yr = int(v.year) if v.year is not None else 2018
            return (
                hub_dist,                                  # 1. Proximity
                -cap,                                      # 2. Higher capacity
                -yr,                                       # 3. Newest year
                v.registration_canonical                   # 4. Alphabetical tie-breaker
            )

        eligible_candidates.sort(key=ranking_key)
        winner_dist, winner_vehicle = eligible_candidates[0]

        # Record why other eligible candidates were ranked lower
        for idx, (dist, cand) in enumerate(eligible_candidates[1:], start=2):
            why_not_matrix[cand.registration_canonical] = f"Eligible (Rank #{idx}): Passed over for closer/newer vehicle {winner_vehicle.registration_canonical}"

        citations.append(f"fleet_master.csv:{winner_vehicle.vehicle_id} ({winner_vehicle.registration_canonical}, {winner_vehicle.model}, {winner_vehicle.bs_stage}, Year {winner_vehicle.year})")
        return winner_vehicle, citations, why_not_matrix
