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
            """
            SELECT v.id, v.plate_number, v.vehicle_type, v.entry_time, v.exit_time,
                   v.assigned_slot, v.status, v.layout_id, v.province,
                   f.id AS fee_id, f.duration_minutes, f.base_fee, f.additional_hours,
                   f.additional_fee, f.total_fee, f.payment_status, f.assessment_time
            FROM vehicle_records v
            LEFT JOIN parking_fees f ON v.id = f.vehicle_record_id
            ORDER BY v.id
            """
        ).fetchall()
        all_fields = RECORD_FIELDS + [
            "id",
            "fee_id",
            "duration_minutes",
            "base_fee",
            "additional_hours",
            "additional_fee",
            "total_fee",
            "payment_status",
            "assessment_time",
        ]
        records = [
            {field: ("" if row[field] is None else row[field]) for field in all_fields}
            for row in rows
        ]
        return pd.DataFrame(records, columns=all_fields).fillna("").astype(str)
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
                "province": source.get("province") or None,
            }
        )

    connection = sqlite_db.get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM vehicle_records")
        connection.executemany(
            "INSERT INTO vehicle_records "
            "(plate_number, vehicle_type, entry_time, exit_time, assigned_slot, status, layout_id, province) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
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
            "SELECT id, plate_number, vehicle_type, entry_time, exit_time, assigned_slot, status, layout_id, province "
            "FROM vehicle_records WHERE plate_number = ? ORDER BY id DESC LIMIT 1",
            (plate_number,),
        ).fetchone()
        if row is None:
            return None
        series_data = {field: row[field] or "" for field in RECORD_FIELDS}
        series_data["id"] = row["id"]
        return pd.Series(series_data)
    finally:
        connection.close()


def add_vehicle(plate_number, vehicle_type, assigned_slot="", layout_id="", province=None):
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
            "(plate_number, vehicle_type, entry_time, exit_time, assigned_slot, status, layout_id, province) "
            "VALUES (?, ?, ?, '', ?, 'Inside', ?, ?)",
            (plate_number, vehicle_type, entry_time, assigned_slot, layout_id, province or None),
        )
        record_id = cursor.lastrowid
        from src.parking import parking_fee
        parking_fee.create_fee_record_tx(
            connection,
            vehicle_record_id=record_id,
            plate_number=plate_number,
            vehicle_type=vehicle_type,
            entry_time=entry_time,
        )
        connection.commit()
        return record_id
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


def assess_exit_fee(plate_number, assessment_time=None):
    """Assess fee at exit detection time while keeping vehicle Inside and slot occupied."""
    _ensure_initialized()
    if assessment_time is None:
        assessment_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    connection = sqlite_db.get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        latest = connection.execute(
            "SELECT id, entry_time, vehicle_type, assigned_slot, layout_id FROM vehicle_records "
            "WHERE plate_number = ? AND status = 'Inside' ORDER BY id DESC LIMIT 1",
            (plate_number,),
        ).fetchone()
        if latest is None:
            connection.rollback()
            raise ValueError(f"No active vehicle inside found with plate {plate_number}.")

        from src.parking import parking_fee
        fee_record = parking_fee.assess_fee_record_tx(
            connection,
            vehicle_record_id=latest["id"],
            assessment_time=assessment_time,
        )
        connection.commit()
        return {"id": latest["id"], "fee": fee_record, "vehicle": dict(latest)}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def finalize_exit(plate_number, exit_time=None):
    """Mark vehicle Exited and allow slot release only if payment is Paid."""
    _ensure_initialized()
    if exit_time is None:
        exit_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    connection = sqlite_db.get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        latest = connection.execute(
            "SELECT id, entry_time, vehicle_type, assigned_slot, layout_id FROM vehicle_records "
            "WHERE plate_number = ? AND status = 'Inside' ORDER BY id DESC LIMIT 1",
            (plate_number,),
        ).fetchone()
        if latest is None:
            connection.rollback()
            raise ValueError(f"No active vehicle inside found with plate {plate_number}.")

        fee = connection.execute(
            "SELECT * FROM parking_fees WHERE vehicle_record_id = ? LIMIT 1",
            (latest["id"],),
        ).fetchone()
        if fee is None or str(fee["payment_status"]).strip().lower() != "paid":
            connection.rollback()
            raise PermissionError("Payment required before exit.")

        connection.execute(
            "UPDATE vehicle_records SET exit_time = ?, status = 'Exited' WHERE id = ?",
            (exit_time, latest["id"]),
        )
        connection.execute(
            "UPDATE parking_fees SET exit_time = ? WHERE id = ?",
            (exit_time, fee["id"]),
        )
        connection.commit()
        updated_fee = connection.execute(
            "SELECT * FROM parking_fees WHERE id = ? LIMIT 1", (fee["id"],)
        ).fetchone()
        return {
            "id": latest["id"],
            "exit_time": exit_time,
            "fee": dict(updated_fee) if updated_fee else dict(fee),
            "vehicle": dict(latest),
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def finalize_exit_by_fee_id(fee_id, exit_time=None):
    """Finalize vehicle exit given a fee_id, verifying payment status first."""
    _ensure_initialized()
    if exit_time is None:
        exit_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    connection = sqlite_db.get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        fee = connection.execute(
            "SELECT * FROM parking_fees WHERE id = ? LIMIT 1", (fee_id,)
        ).fetchone()
        if fee is None:
            connection.rollback()
            raise ValueError(f"Fee record {fee_id} not found.")
        if str(fee["payment_status"]).strip().lower() != "paid":
            connection.rollback()
            raise PermissionError("Payment required before exit.")

        latest = connection.execute(
            "SELECT id, entry_time, vehicle_type, assigned_slot, layout_id, plate_number, status "
            "FROM vehicle_records WHERE id = ? LIMIT 1",
            (fee["vehicle_record_id"],),
        ).fetchone()
        if latest is None:
            connection.rollback()
            raise ValueError(f"Vehicle session {fee['vehicle_record_id']} not found.")

        if latest["status"] == "Inside":
            connection.execute(
                "UPDATE vehicle_records SET exit_time = ?, status = 'Exited' WHERE id = ?",
                (exit_time, latest["id"]),
            )
            connection.execute(
                "UPDATE parking_fees SET exit_time = ? WHERE id = ?",
                (exit_time, fee["id"]),
            )
        connection.commit()
        updated_fee = connection.execute(
            "SELECT * FROM parking_fees WHERE id = ? LIMIT 1", (fee["id"],)
        ).fetchone()
        return {
            "id": latest["id"],
            "plate_number": latest["plate_number"],
            "vehicle_type": latest["vehicle_type"],
            "assigned_slot": latest["assigned_slot"],
            "layout_id": latest["layout_id"],
            "exit_time": exit_time,
            "fee": dict(updated_fee) if updated_fee else dict(fee),
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def update_exit_time(plate_number):
    """Backwards-compatible exit helper: assesses fee and finalizes exit only if payment is Paid."""
    assessment = assess_exit_fee(plate_number)
    fee = assessment.get("fee")
    if fee and str(fee.get("payment_status", "")).strip().lower() == "paid":
        return finalize_exit(plate_number)
    raise PermissionError("Payment required before exit.")


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
