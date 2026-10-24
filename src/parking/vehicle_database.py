import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

from app.database import sqlite_db


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RECORD_FIELDS = list(sqlite_db.VEHICLE_FIELDS)
LAYOUT_CATEGORIES = {
    "car": "car",
    "bus": "bus",
    "motorcycle": "motorcycle",
    "truck": "bus",
}


class AssignmentConflictError(RuntimeError):
    """Raised when a plate or slot already has an active assignment."""


def _ensure_initialized():
    sqlite_db.initialize_database()


def _category(vehicle_type):
    category = LAYOUT_CATEGORIES.get(str(vehicle_type).strip().lower())
    if category is None:
        raise ValueError("Vehicle type has no canonical parking layout.")
    return category


def _translate_integrity_error(error):
    message = str(error)
    if "uq_vehicle_active_slot_layout" in message or "vehicle_records.layout_id" in message:
        return AssignmentConflictError(
            "Another active vehicle already holds this slot in the selected layout."
        )
    if "uq_vehicle_active_plate" in message or "vehicle_records.plate_number" in message:
        return AssignmentConflictError("This plate already has an active assignment.")
    return error


def load_database():
    _ensure_initialized()
    connection = sqlite_db.get_connection()
    try:
        rows = connection.execute(
            "SELECT plate_number, vehicle_type, entry_time, exit_time, assigned_slot, status, layout_id "
            "FROM vehicle_records ORDER BY id"
        ).fetchall()
        records = [{field: row[field] or "" for field in RECORD_FIELDS} for row in rows]
        return pd.DataFrame(records, columns=RECORD_FIELDS).fillna("").astype(str)
    finally:
        connection.close()


def save_database(df):
    """Replace records from a dataframe while keeping the SQLite-only store."""
    _ensure_initialized()
    records = []
    for source in df.to_dict(orient="records"):
        vehicle_type = str(source.get("vehicle_type", "") or "")
        records.append(
            {
                "plate_number": str(source.get("plate_number", "") or ""),
                "vehicle_type": vehicle_type,
                "entry_time": str(source.get("entry_time", "") or ""),
                "exit_time": str(source.get("exit_time", "") or ""),
                "assigned_slot": str(source.get("assigned_slot", "") or ""),
                "status": str(source.get("status", "") or ""),
                "layout_id": str(source.get("layout_id", "") or _category(vehicle_type)),
            }
        )

    connection = sqlite_db.get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM vehicle_records")
        connection.executemany(
            "INSERT INTO vehicle_records "
            "(plate_number, vehicle_type, entry_time, exit_time, assigned_slot, status, layout_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [tuple(record[field] for field in RECORD_FIELDS) for record in records],
        )
        connection.commit()
    except sqlite3.IntegrityError as error:
        connection.rollback()
        translated = _translate_integrity_error(error)
        if translated is error:
            raise
        raise translated from error
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def plate_exists(plate_number):
    _ensure_initialized()
    connection = sqlite_db.get_connection()
    try:
        return connection.execute(
            "SELECT 1 FROM vehicle_records WHERE plate_number = ? LIMIT 1",
            (plate_number,),
        ).fetchone() is not None
    finally:
        connection.close()


def is_vehicle_inside(plate_number):
    _ensure_initialized()
    connection = sqlite_db.get_connection()
    try:
        return connection.execute(
            "SELECT 1 FROM vehicle_records WHERE plate_number = ? AND status = 'Inside' LIMIT 1",
            (plate_number,),
        ).fetchone() is not None
    finally:
        connection.close()


def get_vehicle(plate_number):
    _ensure_initialized()
    connection = sqlite_db.get_connection()
    try:
        row = connection.execute(
            "SELECT plate_number, vehicle_type, entry_time, exit_time, assigned_slot, status, layout_id "
            "FROM vehicle_records WHERE plate_number = ? ORDER BY id DESC LIMIT 1",
            (plate_number,),
        ).fetchone()
        if row is None:
            return None
        return pd.Series({field: row[field] or "" for field in RECORD_FIELDS})
    finally:
        connection.close()


def add_vehicle(plate_number, vehicle_type, assigned_slot="", layout_id=""):
    _ensure_initialized()
    assigned_slot = str(assigned_slot or "")
    layout_id = str(layout_id or _category(vehicle_type))
    if layout_id != _category(vehicle_type):
        raise ValueError("The selected layout does not match the vehicle category.")

    connection = sqlite_db.get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        entry_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor = connection.execute(
            "INSERT INTO vehicle_records "
            "(plate_number, vehicle_type, entry_time, exit_time, assigned_slot, status, layout_id) "
            "VALUES (?, ?, ?, '', ?, 'Inside', ?)",
            (plate_number, vehicle_type, entry_time, assigned_slot, layout_id),
        )
        connection.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError as error:
        connection.rollback()
        translated = _translate_integrity_error(error)
        if translated is error:
            raise
        raise translated from error
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def update_exit_time(plate_number):
    _ensure_initialized()
    connection = sqlite_db.get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        latest = connection.execute(
            "SELECT id FROM vehicle_records "
            "WHERE plate_number = ? AND status = 'Inside' ORDER BY id DESC LIMIT 1",
            (plate_number,),
        ).fetchone()
        if latest is not None:
            exit_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            connection.execute(
                "UPDATE vehicle_records SET exit_time = ?, status = 'Exited' WHERE id = ?",
                (exit_time, latest["id"]),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def assign_slot(plate_number, slot, layout_id=""):
    _ensure_initialized()
    connection = sqlite_db.get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        vehicle = connection.execute(
            "SELECT id, vehicle_type, assigned_slot, layout_id FROM vehicle_records "
            "WHERE plate_number = ? AND status = 'Inside' ORDER BY id DESC LIMIT 1",
            (plate_number,),
        ).fetchone()
        if vehicle is None:
            connection.commit()
            return
        if vehicle["assigned_slot"] and vehicle["assigned_slot"] != slot:
            raise AssignmentConflictError("An active vehicle cannot be moved to another slot.")
        selected_layout = str(layout_id or vehicle["layout_id"] or _category(vehicle["vehicle_type"]))
        if selected_layout != _category(vehicle["vehicle_type"]):
            raise AssignmentConflictError("An active assignment cannot be transferred to another layout.")
        connection.execute(
            "UPDATE vehicle_records SET assigned_slot = ?, layout_id = ? WHERE id = ?",
            (slot, selected_layout, vehicle["id"]),
        )
        connection.commit()
    except AssignmentConflictError:
        connection.rollback()
        raise
    except sqlite3.IntegrityError as error:
        connection.rollback()
        translated = _translate_integrity_error(error)
        if translated is error:
            raise
        raise translated from error
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def remove_slot(plate_number):
    _ensure_initialized()
    connection = sqlite_db.get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        latest = connection.execute(
            "SELECT id FROM vehicle_records "
            "WHERE plate_number = ? AND status = 'Exited' ORDER BY id DESC LIMIT 1",
            (plate_number,),
        ).fetchone()
        if latest is not None:
            connection.execute(
                "UPDATE vehicle_records SET assigned_slot = '' WHERE id = ?",
                (latest["id"],),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def get_assigned_slot(plate_number):
    _ensure_initialized()
    connection = sqlite_db.get_connection()
    try:
        row = connection.execute(
            "SELECT assigned_slot FROM vehicle_records "
            "WHERE plate_number = ? AND status = 'Inside' ORDER BY id DESC LIMIT 1",
            (plate_number,),
        ).fetchone()
        return None if row is None else row["assigned_slot"]
    finally:
        connection.close()
