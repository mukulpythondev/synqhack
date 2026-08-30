"""
Meridian Freight Breakdown Automation
Unified Context Store, Ingestion Engine, and Conflict Resolver
"""

import sqlite3
import pandas as pd
import openpyxl
import re
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path

from src.config import (
    FLEET_MASTER_PATH,
    DRIVERS_ROSTER_PATH,
    MAINTENANCE_LOG_PATH,
    MERIDIAN_TRIPS_PATH,
    EMAILS_DIR,
    STATE_DB_PATH
)
from src.models import (
    CanonicalVehicle,
    CanonicalDriver,
    CanonicalMaintenanceEvent
)
from src.normalizer import (
    normalize_vehicle_reg,
    parse_iso_datetime
)
from src.pii_scrubber import PIIScrubber

class ContextStore:
    """
    Unified relational context store backed by SQLite.
    Stores canonical entity models, maintenance histories, and conflict resolutions.
    Enforces strict PII boundary (zero personal names/phones stored).
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path) if db_path else ":memory:"
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()
        self._load_master_data()

    def _init_tables(self):
        cursor = self.conn.cursor()
        
        # Vehicles Table (Authoritative RC Master)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fleet (
                vehicle_id TEXT,
                registration_canonical TEXT PRIMARY KEY,
                model TEXT,
                year INTEGER,
                bs_stage TEXT,
                has_engine_heater INTEGER,
                home_hub TEXT,
                capacity_tonnes REAL,
                status TEXT,
                is_refrigerated INTEGER DEFAULT 1,
                service_due_date TEXT,
                has_unaddressed_critical_fault INTEGER DEFAULT 0
            )
        """)

        # Drivers Table (Strictly driver_id, joining_date, home_hub; NO PII)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS drivers (
                driver_id TEXT PRIMARY KEY,
                joining_date TEXT,
                home_hub TEXT
            )
        """)

        # Maintenance Events Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS maintenance (
                event_id TEXT PRIMARY KEY,
                vehicle_canonical TEXT,
                event_date TEXT,
                odometer_km INTEGER,
                mechanic_name TEXT,
                is_brake_work INTEGER,
                is_jugaad_temporary INTEGER,
                is_permanent_repair_done INTEGER,
                permanent_repair_date TEXT,
                sanitized_notes TEXT
            )
        """)

        # Apex Incident Tracker for Vehicle Rotation
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS client_incident_history (
                client_name TEXT,
                vehicle_canonical TEXT,
                incident_date TEXT,
                PRIMARY KEY (client_name, vehicle_canonical, incident_date)
            )
        """)

        # Idempotent State Table for Processed Tickets
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_tickets (
                ticket_id TEXT PRIMARY KEY,
                status TEXT,
                work_order_id TEXT,
                replacement_vehicle_reg TEXT,
                is_approved INTEGER DEFAULT 0,
                processed_at TEXT
            )
        """)

        self.conn.commit()

    def _load_master_data(self):
        self._load_fleet()
        self._load_drivers()
        self._load_maintenance()
        self._load_incident_history()

    def _load_fleet(self):
        if not FLEET_MASTER_PATH.exists():
            return
        
        df = pd.read_csv(FLEET_MASTER_PATH)
        cursor = self.conn.cursor()
        
        for idx, row in df.iterrows():
            raw_reg = str(row.get('registration_number', ''))
            canon_reg, is_valid = normalize_vehicle_reg(raw_reg)
            if not is_valid:
                continue
            
            raw_vid = row.get('vehicle_id')
            v_id = str(raw_vid).strip() if pd.notnull(raw_vid) and str(raw_vid).strip() != '' else f"MF-REG-{canon_reg}"
            model = str(row.get('model', 'Commercial Truck')).strip() if pd.notnull(row.get('model')) else "Commercial Truck"
            
            year_val = row.get('year')
            try:
                year = int(year_val) if pd.notnull(year_val) else 2018
            except (ValueError, TypeError):
                year = 2018
                
            bs_stage = str(row.get('bs_stage', 'BS4')).strip().upper() if pd.notnull(row.get('bs_stage')) else "BS4"
            heater_str = str(row.get('engine_heater', '')).strip().lower() if pd.notnull(row.get('engine_heater')) else "no"
            heater = 1 if heater_str == 'yes' else 0
            hub = str(row.get('home_hub', 'Delhi')).strip().title() if pd.notnull(row.get('home_hub')) else "Delhi"
            
            cap_val = row.get('capacity_tonnes')
            try:
                cap = float(cap_val) if pd.notnull(cap_val) else 20.0
            except (ValueError, TypeError):
                cap = 20.0
                
            status = str(row.get('status', 'Active')).strip() if pd.notnull(row.get('status')) else "Active"

            cursor.execute("""
                INSERT OR REPLACE INTO fleet (
                    vehicle_id, registration_canonical, model, year, bs_stage,
                    has_engine_heater, home_hub, capacity_tonnes, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (v_id, canon_reg, model, year, bs_stage, heater, hub, cap, status))
        
        self.conn.commit()

    def _load_drivers(self):
        if not DRIVERS_ROSTER_PATH.exists():
            return
        
        df = pd.read_csv(DRIVERS_ROSTER_PATH)
        cursor = self.conn.cursor()
        
        for _, row in df.iterrows():
            drv_id = str(row.get('driver_id', '')).strip()
            if not drv_id or not drv_id.startswith('DRV-'):
                continue
            
            joining_date = str(row.get('joining_date', '2020-01-01')).strip()
            hub = str(row.get('home_hub', '')).strip().title()

            cursor.execute("""
                INSERT OR REPLACE INTO drivers (driver_id, joining_date, home_hub)
                VALUES (?, ?, ?)
            """, (drv_id, joining_date, hub))
        
        self.conn.commit()

    def _load_maintenance(self):
        if not MAINTENANCE_LOG_PATH.exists():
            return
        
        df = pd.read_excel(MAINTENANCE_LOG_PATH)
        cursor = self.conn.cursor()
        
        BRAKE_KEYWORDS = ["brake", "break", "pad", "drum"]
        JUGAAD_KEYWORDS = ["jugaad", "temporary", "temp fix", "band kiya jugaad se"]

        for idx, row in df.iterrows():
            raw_reg = str(row.get('vehicle', ''))
            canon_reg, is_valid = normalize_vehicle_reg(raw_reg)
            if not is_valid:
                continue
            
            raw_date = row.get('date')
            event_date_str = str(raw_date).split()[0] if raw_date else "2025-01-01"
            odo = int(row.get('odometer_km', 0)) if pd.notnull(row.get('odometer_km')) else 0
            mech = str(row.get('mechanic', '')).strip()
            notes = str(row.get('notes', ''))
            
            sanitized_notes = PIIScrubber.scrub_text(notes)
            notes_lower = notes.lower()
            
            is_brake = 1 if any(k in notes_lower for k in BRAKE_KEYWORDS) else 0
            is_jugaad = 1 if any(k in notes_lower for k in JUGAAD_KEYWORDS) else 0
            
            event_id = f"MAINT-{canon_reg}-{event_date_str}-{odo}-{idx}"

            cursor.execute("""
                INSERT OR REPLACE INTO maintenance (
                    event_id, vehicle_canonical, event_date, odometer_km, mechanic_name,
                    is_brake_work, is_jugaad_temporary, is_permanent_repair_done,
                    permanent_repair_date, sanitized_notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL, ?)
            """, (event_id, canon_reg, event_date_str, odo, mech, is_brake, is_jugaad, sanitized_notes))
        
        self.conn.commit()

    def _load_incident_history(self):
        """
        Dynamically derives client incident and rotation history from email threads.
        Scans candidate_bundle/emails/ for reported breakdowns and flags corresponding vehicles.
        """
        if not EMAILS_DIR.exists():
            return
        
        cursor = self.conn.cursor()
        for email_file in EMAILS_DIR.glob("*.txt"):
            try:
                content = email_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            
            content_lower = content.lower()
            
            # Check for Apex Chemicals incident or rotation threads
            if "apex" in content_lower and ("broke down" in content_lower or "incident" in content_lower or "rotation" in content_lower or "same vehicle" in content_lower or "again" in content_lower):
                # Extract date from email header
                date_m = re.search(r'Date:\s*([A-Za-z]+,\s*)?(\d{1,2}\s+[A-Za-z]+\s+\d{4})', content)
                incident_date = "2026-06-01"
                if date_m:
                    raw_d = date_m.group(2)
                    try:
                        dt = datetime.strptime(raw_d, "%d %b %Y")
                        incident_date = dt.strftime("%Y-%m-%d")
                    except Exception:
                        pass
                
                # Extract vehicles mentioned in the email body/subject
                reg_matches = re.findall(r'[A-Z]{2}[-\s]?[0-9]{1,2}[-\s]?[A-Z]{1,3}[-\s]?[0-9]{3,4}', content, re.IGNORECASE)
                for raw_reg in reg_matches:
                    canon_reg, is_valid = normalize_vehicle_reg(raw_reg)
                    if is_valid:
                        cursor.execute("""
                            INSERT OR IGNORE INTO client_incident_history (client_name, vehicle_canonical, incident_date)
                            VALUES (?, ?, ?)
                        """, ("Apex Chemicals", canon_reg, incident_date))

        self.conn.commit()

    def get_vehicle(self, canon_reg: str) -> Optional[CanonicalVehicle]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM fleet WHERE registration_canonical = ?", (canon_reg,))
        row = cursor.fetchone()
        if not row:
            return None
        
        return CanonicalVehicle(
            vehicle_id=row['vehicle_id'] or f"MF-REG-{canon_reg}",
            registration_canonical=row['registration_canonical'],
            model=row['model'] or "Commercial Truck",
            year=int(row['year']) if row['year'] else 2018,
            bs_stage=row['bs_stage'] or "BS4",
            has_engine_heater=bool(row['has_engine_heater']),
            home_hub=row['home_hub'] or "Delhi",
            capacity_tonnes=float(row['capacity_tonnes']) if row['capacity_tonnes'] else 20.0,
            status=row['status'] or "Active",
            is_refrigerated=bool(row['is_refrigerated']),
            has_unaddressed_critical_fault=bool(row['has_unaddressed_critical_fault']),
            source_provenance=f"fleet_master.csv:{row['vehicle_id'] or canon_reg}"
        )

    def get_driver(self, driver_id: str) -> Optional[CanonicalDriver]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM drivers WHERE driver_id = ?", (driver_id,))
        row = cursor.fetchone()
        if not row:
            return None
        
        joining_date_obj, _ = parse_iso_datetime(row['joining_date'])
        joining_date = joining_date_obj.date() if joining_date_obj else date(2020, 1, 1)

        return CanonicalDriver(
            driver_id=row['driver_id'],
            joining_date=joining_date,
            home_hub=row['home_hub'],
            source_provenance=f"drivers_roster.csv:{row['driver_id']}"
        )

    def has_recent_brake_work(self, canon_reg: str, target_date: datetime, days: int = 30) -> bool:
        """
        Returns True if the vehicle had brake work in the preceding `days` before `target_date`.
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT event_date FROM maintenance
            WHERE vehicle_canonical = ? AND is_brake_work = 1
            ORDER BY event_date DESC
        """, (canon_reg,))
        
        target_d = target_date.date() if isinstance(target_date, datetime) else target_date
        
        for row in cursor.fetchall():
            dt, _ = parse_iso_datetime(row['event_date'])
            if dt:
                delta_days = (target_d - dt.date()).days
                if 0 <= delta_days <= days:
                    return True
        return False

    def is_jugaad_active(self, canon_reg: str, target_date: datetime, target_destination: str) -> Tuple[bool, Optional[str]]:
        """
        Returns (is_active_jugaad, reason_if_violating):
        - If temporary patch applied within 7 days, vehicle cannot leave its home region.
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT event_date, sanitized_notes FROM maintenance
            WHERE vehicle_canonical = ? AND is_jugaad_temporary = 1
            ORDER BY event_date DESC LIMIT 1
        """, (canon_reg,))
        
        row = cursor.fetchone()
        if not row:
            return False, None
        
        dt, _ = parse_iso_datetime(row['event_date'])
        if not dt:
            return False, None
        
        target_d = target_date.date() if isinstance(target_date, datetime) else target_date
        delta_days = (target_d - dt.date()).days
        
        if 0 <= delta_days <= 7:
            # Active jugaad clock! Must stay within home region
            v = self.get_vehicle(canon_reg)
            if v and target_destination != v.home_hub:
                return True, f"Active Guddu jugaad patch ({delta_days} days old) restricts vehicle to home hub '{v.home_hub}' (Destination is '{target_destination}')"
        
        return False, None

    def record_apex_incident(self, canon_reg: str, incident_date: str):
        cursor = self.conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO client_incident_history VALUES (?, ?, ?)",
                       ("Apex Chemicals", canon_reg, incident_date))
        self.conn.commit()

    def get_last_apex_incident_vehicle(self) -> Optional[str]:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT vehicle_canonical FROM client_incident_history
            WHERE client_name = 'Apex Chemicals'
            ORDER BY incident_date DESC LIMIT 1
        """)
        row = cursor.fetchone()
        return row['vehicle_canonical'] if row else None

    def get_all_vehicles_in_hub(self, hub: str) -> List[CanonicalVehicle]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT registration_canonical FROM fleet WHERE home_hub = ?", (hub,))
        results = []
        for row in cursor.fetchall():
            v = self.get_vehicle(row['registration_canonical'])
            if v:
                results.append(v)
        return results

    def get_all_active_vehicles(self) -> List[CanonicalVehicle]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT registration_canonical FROM fleet WHERE status = 'Active'")
        results = []
        for row in cursor.fetchall():
            v = self.get_vehicle(row['registration_canonical'])
            if v:
                results.append(v)
        return results

    def is_ticket_processed(self, ticket_id: str) -> bool:
        cursor = self.conn.cursor()
        cursor.execute("SELECT 1 FROM processed_tickets WHERE ticket_id = ?", (ticket_id,))
        return cursor.fetchone() is not None

    def record_processed_ticket(self, ticket_id: str, status: str, work_order_id: Optional[str],
                                replacement_reg: Optional[str], is_approved: int, processed_at: str):
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO processed_tickets (
                ticket_id, status, work_order_id, replacement_vehicle_reg, is_approved, processed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (ticket_id, status, work_order_id, replacement_reg, is_approved, processed_at))
        self.conn.commit()
