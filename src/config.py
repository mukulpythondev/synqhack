"""
Meridian Freight Breakdown-to-Resolution Automation
Configuration, Constants, Hub Coordinates, and Corridor Geography
"""

import os
from pathlib import Path

# Base Paths
WORKSPACE_ROOT = Path(r"c:\Users\MUKUL\Documents\Synq Hackathon")
BUNDLE_DIR = WORKSPACE_ROOT / "candidate_bundle"
OUTPUTS_DIR = WORKSPACE_ROOT / "outputs"
AUDIT_DIR = WORKSPACE_ROOT / "audit"
STATE_DB_PATH = WORKSPACE_ROOT / ".state.db"

# Data File Paths
TICKETS_PATH = BUNDLE_DIR / "tickets.json"
FLEET_MASTER_PATH = BUNDLE_DIR / "fleet_master.csv"
DRIVERS_ROSTER_PATH = BUNDLE_DIR / "drivers_roster.csv"
MAINTENANCE_LOG_PATH = BUNDLE_DIR / "maintenance_log.xlsx"
MERIDIAN_TRIPS_PATH = BUNDLE_DIR / "meridian_trips.csv"
EMAILS_DIR = BUNDLE_DIR / "emails"
INTERVIEW_PATH = BUNDLE_DIR / "dispatcher_interview.txt"

# Output File Paths
WORK_ORDERS_PATH = OUTPUTS_DIR / "work_orders.jsonl"
COMMS_PENDING_PATH = OUTPUTS_DIR / "comms_pending.jsonl"
COMMS_SENT_PATH = OUTPUTS_DIR / "comms_sent.jsonl"
QUARANTINE_PATH = OUTPUTS_DIR / "quarantine.jsonl"
AUDIT_PATH = AUDIT_DIR / "audit.jsonl"

# 9 Primary Meridian Hubs & GPS Coordinates (Latitude, Longitude)
HUB_COORDINATES = {
    "Ambala": (30.3782, 76.7767),
    "Chandigarh": (30.7333, 76.7794),
    "Delhi": (28.6139, 77.2090),
    "Gurgaon": (28.4595, 77.0266),
    "Jaipur": (26.9124, 75.7873),
    "Kanpur": (26.4499, 80.3319),
    "Lucknow": (26.8467, 80.9462),
    "Ludhiana": (30.9010, 75.8573),
    "Rudrapur": (28.9800, 79.4000),
}

# Pre-computed Hub-to-Hub Road Distance Matrix (km)
# Derived from median historical OSRM metrics in meridian_trips.csv & highway corridors
HUB_DISTANCE_MATRIX = {
    ("Ambala", "Chandigarh"): 45.0,
    ("Ambala", "Delhi"): 210.0,
    ("Ambala", "Gurgaon"): 235.0,
    ("Ambala", "Jaipur"): 430.0,
    ("Ambala", "Kanpur"): 610.0,
    ("Ambala", "Lucknow"): 620.0,
    ("Ambala", "Ludhiana"): 115.0,
    ("Ambala", "Rudrapur"): 320.0,
    
    ("Chandigarh", "Ambala"): 45.0,
    ("Chandigarh", "Delhi"): 250.0,
    ("Chandigarh", "Gurgaon"): 275.0,
    ("Chandigarh", "Jaipur"): 470.0,
    ("Chandigarh", "Kanpur"): 650.0,
    ("Chandigarh", "Lucknow"): 660.0,
    ("Chandigarh", "Ludhiana"): 100.0,
    ("Chandigarh", "Rudrapur"): 350.0,
    
    ("Delhi", "Ambala"): 210.0,
    ("Delhi", "Chandigarh"): 250.0,
    ("Delhi", "Gurgaon"): 30.0,
    ("Delhi", "Jaipur"): 270.0,
    ("Delhi", "Kanpur"): 440.0,
    ("Delhi", "Lucknow"): 470.0,
    ("Delhi", "Ludhiana"): 310.0,
    ("Delhi", "Rudrapur"): 240.0,
    
    ("Gurgaon", "Ambala"): 235.0,
    ("Gurgaon", "Chandigarh"): 275.0,
    ("Gurgaon", "Delhi"): 30.0,
    ("Gurgaon", "Jaipur"): 240.0,
    ("Gurgaon", "Kanpur"): 445.0,
    ("Gurgaon", "Lucknow"): 480.0,
    ("Gurgaon", "Ludhiana"): 325.0,
    ("Gurgaon", "Rudrapur"): 265.0,
    
    ("Jaipur", "Ambala"): 430.0,
    ("Jaipur", "Chandigarh"): 470.0,
    ("Jaipur", "Delhi"): 270.0,
    ("Jaipur", "Gurgaon"): 240.0,
    ("Jaipur", "Kanpur"): 510.0,
    ("Jaipur", "Lucknow"): 570.0,
    ("Jaipur", "Ludhiana"): 490.0,
    ("Jaipur", "Rudrapur"): 470.0,
    
    ("Kanpur", "Ambala"): 610.0,
    ("Kanpur", "Chandigarh"): 650.0,
    ("Kanpur", "Delhi"): 440.0,
    ("Kanpur", "Gurgaon"): 445.0,
    ("Kanpur", "Jaipur"): 510.0,
    ("Kanpur", "Lucknow"): 80.0,
    ("Kanpur", "Ludhiana"): 720.0,
    ("Kanpur", "Rudrapur"): 330.0,
    
    ("Lucknow", "Ambala"): 620.0,
    ("Lucknow", "Chandigarh"): 660.0,
    ("Lucknow", "Delhi"): 470.0,
    ("Lucknow", "Gurgaon"): 480.0,
    ("Lucknow", "Jaipur"): 570.0,
    ("Lucknow", "Kanpur"): 80.0,
    ("Lucknow", "Ludhiana"): 730.0,
    ("Lucknow", "Rudrapur"): 310.0,
    
    ("Ludhiana", "Ambala"): 115.0,
    ("Ludhiana", "Chandigarh"): 100.0,
    ("Ludhiana", "Delhi"): 310.0,
    ("Ludhiana", "Gurgaon"): 325.0,
    ("Ludhiana", "Jaipur"): 490.0,
    ("Ludhiana", "Kanpur"): 720.0,
    ("Ludhiana", "Lucknow"): 730.0,
    ("Ludhiana", "Rudrapur"): 440.0,
    
    ("Rudrapur", "Ambala"): 320.0,
    ("Rudrapur", "Chandigarh"): 350.0,
    ("Rudrapur", "Delhi"): 240.0,
    ("Rudrapur", "Gurgaon"): 265.0,
    ("Rudrapur", "Jaipur"): 470.0,
    ("Rudrapur", "Kanpur"): 330.0,
    ("Rudrapur", "Lucknow"): 310.0,
    ("Rudrapur", "Ludhiana"): 440.0,
}

# Corridor Geography Definitions
DELHI_NCR_NODES = {"Delhi", "Gurgaon", "Noida", "Faridabad", "Ghaziabad", "Kundli", "Sonipat"}

# Routes that transit the Delhi/NCR highway ring
NCR_TRANSIT_PAIRS = {
    ("Ludhiana", "Jaipur"), ("Jaipur", "Ludhiana"),
    ("Chandigarh", "Jaipur"), ("Jaipur", "Chandigarh"),
    ("Ambala", "Jaipur"), ("Jaipur", "Ambala"),
    ("Ludhiana", "Kanpur"), ("Kanpur", "Ludhiana"),
    ("Ludhiana", "Lucknow"), ("Lucknow", "Ludhiana"),
    ("Chandigarh", "Kanpur"), ("Kanpur", "Chandigarh"),
    ("Ambala", "Kanpur"), ("Kanpur", "Ambala"),
}

HILL_CORRIDOR_NODES = {"Rudrapur", "Nainital", "Haldwani", "Ramnagar", "Almora", "Pithorgarh", "Ranikhet"}

# East of Lucknow Longitude Meridian
LUCKNOW_LONGITUDE = 80.9462
EAST_OF_LUCKNOW_CENTERS = {
    "Gorakhpur", "Varanasi", "Patna", "Muzaffarpur", "Ranchi", "Kolkata",
    "Siliguri", "Guwahati", "Assam", "Bihar", "West Bengal", "Jharkhand", "Orissa"
}

# Client Operational Rules & Contact Endpoints
CLIENT_METADATA = {
    "Shakti Cement": {
        "contract_sla_hours": 48,
        "operational_sla_hours": 36,
        "email_recipient": "dispatch@shakticement.example.in",
        "notes": "Plan everything to 36h internally. Contract 48h is legacy."
    },
    "Vertex Retail": {
        "contract_sla_hours": 48,
        "operational_sla_hours": 48,
        "gate_close_hour": 18,  # 6:00 PM
        "morning_delivery_hour": 8,  # 8:00 AM
        "email_recipient": "logistics@vertexretail.example.in",
        "notes": "Ludhiana WH gate closes 6pm. Late arrivals delivered 8am next day; must mark as 'scheduled morning delivery', never failed."
    },
    "Apex Chemicals": {
        "contract_sla_hours": 48,
        "operational_sla_hours": 48,
        "email_recipient": "stores@apexchem.example.in",
        "notes": "Truck rotation mandatory: if vehicle breaks down on Apex run, rotate to another vehicle for next dispatch."
    },
    "Orion Pharma": {
        "contract_sla_hours": 48,
        "operational_sla_hours": 48,
        "min_model_year": 2020,
        "email_recipient": "scm@orionpharma.example.in",
        "notes": "RC year 2020 or later only. Never leave at hub overnight unrefrigerated."
    },
    "Internal": {
        "contract_sla_hours": 48,
        "operational_sla_hours": 48,
        "email_recipient": "ops@meridianfreight.example.in",
        "notes": "Meridian internal transfers."
    }
}

# Quarantine Reason Codes
QUARANTINE_REASONS = {
    "MISSING_CRITICAL_FIELDS": "Record missing mandatory routing or identifier keys (origin_hub, destination, vehicle, driver_id)",
    "INVALID_DATE_FORMAT": "created_at timestamp cannot be parsed into ISO-8601 datetime",
    "UNRESOLVED_VEHICLE": "Vehicle registration cannot be resolved in fleet master or contains corrupted mask (e.g. hr??unknown)",
    "UNRESOLVED_DRIVER": "Driver ID not found in driver roster master",
    "NULL_DISTANCE_METRIC": "km_from_origin_hub is missing or null",
    "CORRUPTED_PAYLOAD": "Malformed JSON structure or unrecoverable schema drift"
}
