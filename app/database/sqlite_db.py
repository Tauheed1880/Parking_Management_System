import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "database" / "smart_parking.db"

VEHICLE_FIELDS = (
    "plate_number",
    "vehicle_type",
    "entry_time",
    "exit_time",
    "assigned_slot",
    "status",
    "layout_id",
    "province",
)
SLOT_FIELDS = ("slot", "status", "row", "column", "x1", "y1", "x2", "y2")


def _connect(db_path=None):
    path = Path(db_path) if db_path is not None else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_schema(db_path=None):
    connection = _connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS layouts (
                type TEXT PRIMARY KEY CHECK (type IN ('car', 'bus', 'motorcycle')),
                image_path TEXT NOT NULL,
                sha256 TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS slots (
                layout_id TEXT NOT NULL REFERENCES layouts(type) ON DELETE CASCADE,
                slot TEXT NOT NULL,
                row TEXT NOT NULL,
                column INTEGER NOT NULL,
                x1 REAL NOT NULL,
                y1 REAL NOT NULL,
                x2 REAL NOT NULL,
                y2 REAL NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('empty', 'occupied')),
                PRIMARY KEY (layout_id, slot)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS vehicle_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plate_number TEXT NOT NULL,
                vehicle_type TEXT NOT NULL,
                entry_time TEXT NOT NULL,
                exit_time TEXT NOT NULL DEFAULT '',
                assigned_slot TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL CHECK (status IN ('Inside', 'Exited')),
                layout_id TEXT NOT NULL REFERENCES layouts(type),
                province TEXT
            )
            """
        )
        existing_cols = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(vehicle_records)").fetchall()
        }
        if "province" not in existing_cols:
            connection.execute("ALTER TABLE vehicle_records ADD COLUMN province TEXT")
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_vehicle_active_slot_layout
            ON vehicle_records(layout_id, assigned_slot)
            WHERE status = 'Inside' AND assigned_slot <> ''
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_vehicle_active_plate
            ON vehicle_records(plate_number)
            WHERE status = 'Inside'
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS parking_fees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_record_id INTEGER NOT NULL UNIQUE REFERENCES vehicle_records(id) ON DELETE CASCADE,
                plate_number TEXT NOT NULL,
                vehicle_type TEXT NOT NULL,
                entry_time TEXT NOT NULL,
                assessment_time TEXT,
                exit_time TEXT,
                duration_minutes INTEGER,
                rate_base_fee REAL NOT NULL,
                rate_additional_hourly REAL NOT NULL,
                base_fee REAL,
                additional_hours INTEGER,
                additional_fee REAL,
                total_fee REAL,
                payment_status TEXT NOT NULL DEFAULT 'Unpaid' CHECK (payment_status IN ('Unpaid', 'Paid')),
                created_at TEXT NOT NULL
            )
            """
        )
        existing_fee_cols = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(parking_fees)").fetchall()
        }
        if "assessment_time" not in existing_fee_cols:
            connection.execute("ALTER TABLE parking_fees ADD COLUMN assessment_time TEXT")

        # Ensure active vehicles ('Inside') have exit_time as NULL and assessment_time populated if needed
        connection.execute(
            """
            UPDATE parking_fees
            SET assessment_time = COALESCE(assessment_time, exit_time),
                exit_time = NULL
            WHERE vehicle_record_id IN (
                SELECT id FROM vehicle_records WHERE status = 'Inside'
            ) AND exit_time IS NOT NULL
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_parking_fees_plate_number
            ON parking_fees(plate_number)
            """
        )
        try:
            from src.parking.parking_fee import backfill_existing_records
            backfill_existing_records(connection)
        except Exception:
            pass
        connection.commit()
    finally:
        connection.close()


def initialize_database(db_path=None):
    """Create the fresh schema without importing or accessing any CSV data."""
    initialize_schema(db_path)


def get_connection(db_path=None):
    """Open a project-relative SQLite connection for the persistence layer."""
    return _connect(db_path)
