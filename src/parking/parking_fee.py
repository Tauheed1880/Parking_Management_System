import math
from datetime import datetime
from typing import Any, Dict, Optional

from app.database import sqlite_db


FEE_RATES: Dict[str, Dict[str, Any]] = {
    "motorcycle": {
        "display_name": "Motorcycle / Bike",
        "base_fee": 20.0,
        "additional_hourly_fee": 5.0,
        "base_hours": 2,
    },
    "car": {
        "display_name": "Car",
        "base_fee": 50.0,
        "additional_hourly_fee": 10.0,
        "base_hours": 2,
    },
    "bus": {
        "display_name": "Bus",
        "base_fee": 100.0,
        "additional_hourly_fee": 20.0,
        "base_hours": 2,
    },
    "truck": {
        "display_name": "Truck",
        "base_fee": 100.0,
        "additional_hourly_fee": 20.0,
        "base_hours": 2,
    },
}

TYPE_ALIASES: Dict[str, str] = {
    "motorcycle": "motorcycle",
    "bike": "motorcycle",
    "motorbike": "motorcycle",
    "car": "car",
    "bus": "bus",
    "truck": "truck",
}


class FeeCalculationError(ValueError):
    """Raised when duration or fee cannot be safely calculated."""


def normalize_vehicle_type(vehicle_type: str) -> str:
    cleaned = str(vehicle_type or "").strip().lower()
    normalized = TYPE_ALIASES.get(cleaned)
    if not normalized:
        raise ValueError(f"Unsupported vehicle type for fee calculation: {vehicle_type}")
    return normalized


def get_vehicle_rates(vehicle_type: str) -> Dict[str, Any]:
    canonical = normalize_vehicle_type(vehicle_type)
    return FEE_RATES[canonical]


def calculate_duration_minutes(entry_time_str: str, exit_time_str: str) -> int:
    if not entry_time_str or not exit_time_str:
        raise FeeCalculationError("Missing entry or exit timestamp.")
    try:
        entry_dt = datetime.strptime(str(entry_time_str).strip(), "%Y-%m-%d %H:%M:%S")
        exit_dt = datetime.strptime(str(exit_time_str).strip(), "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError) as exc:
        raise FeeCalculationError(f"Invalid timestamp format: {exc}")

    total_seconds = (exit_dt - entry_dt).total_seconds()
    if total_seconds < 0:
        raise FeeCalculationError(
            f"Exit time ({exit_time_str}) cannot be earlier than entry time ({entry_time_str})."
        )
    return max(0, int(total_seconds // 60))


def calculate_additional_hours(duration_minutes: int, base_hours: int = 2) -> int:
    if duration_minutes < 0:
        raise FeeCalculationError("Duration cannot be negative.")
    base_minutes = base_hours * 60
    if duration_minutes <= base_minutes:
        return 0
    return max(0, math.ceil((duration_minutes - base_minutes) / 60))


def calculate_fee(
    vehicle_type: str,
    duration_minutes: int,
    rate_base_fee: Optional[float] = None,
    rate_additional_hourly: Optional[float] = None,
) -> Dict[str, Any]:
    normalized_type = normalize_vehicle_type(vehicle_type)
    rates = get_vehicle_rates(normalized_type)
    base_rate = float(rate_base_fee) if rate_base_fee is not None else float(rates["base_fee"])
    hourly_rate = (
        float(rate_additional_hourly)
        if rate_additional_hourly is not None
        else float(rates["additional_hourly_fee"])
    )

    additional_hours = calculate_additional_hours(duration_minutes, rates["base_hours"])
    additional_fee = round(additional_hours * hourly_rate, 2)
    total_fee = round(base_rate + additional_fee, 2)

    return {
        "vehicle_type": normalized_type,
        "duration_minutes": duration_minutes,
        "base_fee": base_rate,
        "additional_hours": additional_hours,
        "additional_fee": additional_fee,
        "total_fee": total_fee,
    }


def create_fee_record_tx(
    connection,
    vehicle_record_id: int,
    plate_number: str,
    vehicle_type: str,
    entry_time: str,
) -> Dict[str, Any]:
    """Create a pending fee record within an existing database transaction."""
    if not entry_time:
        raise FeeCalculationError("Entry time is required to create a fee record.")
    try:
        datetime.strptime(str(entry_time).strip(), "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError) as exc:
        raise FeeCalculationError(f"Invalid entry timestamp format: {exc}")

    normalized_type = normalize_vehicle_type(vehicle_type)
    rates = get_vehicle_rates(normalized_type)
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor = connection.execute(
        """
        INSERT INTO parking_fees
        (vehicle_record_id, plate_number, vehicle_type, entry_time, exit_time,
         duration_minutes, rate_base_fee, rate_additional_hourly, base_fee,
         additional_hours, additional_fee, total_fee, payment_status, created_at)
        VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, NULL, NULL, NULL, NULL, 'Unpaid', ?)
        """,
        (
            vehicle_record_id,
            str(plate_number).strip().upper(),
            normalized_type,
            str(entry_time).strip(),
            rates["base_fee"],
            rates["additional_hourly_fee"],
            created_at,
        ),
    )
    return {
        "id": cursor.lastrowid,
        "vehicle_record_id": vehicle_record_id,
        "plate_number": str(plate_number).strip().upper(),
        "vehicle_type": normalized_type,
        "entry_time": str(entry_time).strip(),
        "exit_time": None,
        "duration_minutes": None,
        "rate_base_fee": rates["base_fee"],
        "rate_additional_hourly": rates["additional_hourly_fee"],
        "base_fee": None,
        "additional_hours": None,
        "additional_fee": None,
        "total_fee": None,
        "payment_status": "Unpaid",
        "created_at": created_at,
    }


def assess_fee_record_tx(
    connection,
    vehicle_record_id: int,
    assessment_time: str,
) -> Dict[str, Any]:
    """Calculate and update parking fee up to the current assessment time without marking vehicle exited."""
    row = connection.execute(
        """
        SELECT id, vehicle_record_id, plate_number, vehicle_type, entry_time, exit_time,
               duration_minutes, rate_base_fee, rate_additional_hourly, base_fee,
               additional_hours, additional_fee, total_fee, payment_status, created_at
        FROM parking_fees
        WHERE vehicle_record_id = ?
        LIMIT 1
        """,
        (vehicle_record_id,),
    ).fetchone()

    if row is None:
        # Fallback: check vehicle_records to see if this is an older session missing a fee record
        v_row = connection.execute(
            "SELECT id, plate_number, vehicle_type, entry_time FROM vehicle_records WHERE id = ?",
            (vehicle_record_id,),
        ).fetchone()
        if v_row is None:
            raise FeeCalculationError(f"No vehicle record found for id {vehicle_record_id}.")
        created = create_fee_record_tx(
            connection,
            v_row["id"],
            v_row["plate_number"],
            v_row["vehicle_type"],
            v_row["entry_time"],
        )
        row = connection.execute(
            "SELECT * FROM parking_fees WHERE id = ?", (created["id"],)
        ).fetchone()

    # If the fee record is already paid, do not recompute or increase fee
    if str(row["payment_status"]).strip().lower() == "paid":
        return dict(row)

    entry_time = row["entry_time"]
    duration_minutes = calculate_duration_minutes(entry_time, assessment_time)
    calc = calculate_fee(
        row["vehicle_type"],
        duration_minutes,
        rate_base_fee=row["rate_base_fee"],
        rate_additional_hourly=row["rate_additional_hourly"],
    )

    connection.execute(
        """
        UPDATE parking_fees
        SET assessment_time = ?,
            exit_time = NULL,
            duration_minutes = ?,
            base_fee = ?,
            additional_hours = ?,
            additional_fee = ?,
            total_fee = ?
        WHERE id = ?
        """,
        (
            assessment_time,
            calc["duration_minutes"],
            calc["base_fee"],
            calc["additional_hours"],
            calc["additional_fee"],
            calc["total_fee"],
            row["id"],
        ),
    )

    updated = connection.execute(
        "SELECT * FROM parking_fees WHERE id = ?", (row["id"],)
    ).fetchone()
    return dict(updated)


def finalize_fee_record_tx(
    connection,
    vehicle_record_id: int,
    actual_exit_time: str,
) -> Dict[str, Any]:
    """Record actual exit time on fee record after exit confirmation."""
    row = connection.execute(
        "SELECT * FROM parking_fees WHERE vehicle_record_id = ? LIMIT 1",
        (vehicle_record_id,),
    ).fetchone()
    if row is None:
        raise FeeCalculationError(f"No fee record found for vehicle record {vehicle_record_id}.")

    connection.execute(
        "UPDATE parking_fees SET exit_time = ? WHERE id = ?",
        (actual_exit_time, row["id"]),
    )
    updated = connection.execute(
        "SELECT * FROM parking_fees WHERE id = ?", (row["id"],)
    ).fetchone()
    return dict(updated)


def complete_fee_record_tx(
    connection,
    vehicle_record_id: int,
    exit_time: str,
) -> Dict[str, Any]:
    """Assess and return fee record for a vehicle session inside an existing transaction."""
    return assess_fee_record_tx(connection, vehicle_record_id, exit_time)


def get_fee_by_vehicle_record_id(vehicle_record_id: int, connection=None) -> Optional[Dict[str, Any]]:
    owns_conn = False
    if connection is None:
        connection = sqlite_db.get_connection()
        owns_conn = True
    try:
        row = connection.execute(
            "SELECT * FROM parking_fees WHERE vehicle_record_id = ? LIMIT 1",
            (vehicle_record_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        if owns_conn:
            connection.close()


def get_fee_by_id(fee_id: int, connection=None) -> Optional[Dict[str, Any]]:
    owns_conn = False
    if connection is None:
        connection = sqlite_db.get_connection()
        owns_conn = True
    try:
        row = connection.execute(
            "SELECT * FROM parking_fees WHERE id = ? LIMIT 1",
            (fee_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        if owns_conn:
            connection.close()


def mark_fee_paid(fee_id: int, admin_auth: bool = False, note: str = "") -> Dict[str, Any]:
    if not admin_auth:
        raise PermissionError("Manual payment updates require verified administrative authorization.")

    connection = sqlite_db.get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM parking_fees WHERE id = ? LIMIT 1", (fee_id,)
        ).fetchone()
        if row is None:
            connection.rollback()
            raise ValueError(f"Fee record {fee_id} does not exist.")

        if row["total_fee"] is None:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            duration = calculate_duration_minutes(row["entry_time"], now_str)
            calc = calculate_fee(
                row["vehicle_type"],
                duration,
                row["rate_base_fee"],
                row["rate_additional_hourly"],
            )
            connection.execute(
                """
                UPDATE parking_fees
                SET assessment_time = ?,
                    exit_time = NULL,
                    duration_minutes = ?,
                    base_fee = ?,
                    additional_hours = ?,
                    additional_fee = ?,
                    total_fee = ?,
                    payment_status = 'Paid'
                WHERE id = ?
                """,
                (
                    now_str,
                    calc["duration_minutes"],
                    calc["base_fee"],
                    calc["additional_hours"],
                    calc["additional_fee"],
                    calc["total_fee"],
                    fee_id,
                ),
            )
        else:
            connection.execute(
                "UPDATE parking_fees SET payment_status = 'Paid' WHERE id = ?",
                (fee_id,),
            )
        connection.commit()
        updated = connection.execute(
            "SELECT * FROM parking_fees WHERE id = ? LIMIT 1", (fee_id,)
        ).fetchone()
        return dict(updated)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def backfill_existing_records(connection) -> int:
    """Safely backfill fee records for existing vehicle records without inventing data."""
    unbacked = connection.execute(
        """
        SELECT v.id, v.plate_number, v.vehicle_type, v.entry_time, v.exit_time, v.status
        FROM vehicle_records v
        LEFT JOIN parking_fees f ON v.id = f.vehicle_record_id
        WHERE f.id IS NULL
        ORDER BY v.id
        """
    ).fetchall()

    created_count = 0
    for v in unbacked:
        # Validate vehicle type
        try:
            norm_type = normalize_vehicle_type(v["vehicle_type"])
            rates = get_vehicle_rates(norm_type)
        except Exception:
            continue

        # Validate entry time
        entry_time_str = str(v["entry_time"] or "").strip()
        try:
            datetime.strptime(entry_time_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue

        status = str(v["status"] or "").strip()
        exit_time_str = str(v["exit_time"] or "").strip()

        if status == "Inside":
            connection.execute(
                """
                INSERT INTO parking_fees
                (vehicle_record_id, plate_number, vehicle_type, entry_time, exit_time,
                 duration_minutes, rate_base_fee, rate_additional_hourly, base_fee,
                 additional_hours, additional_fee, total_fee, payment_status, created_at)
                VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, NULL, NULL, NULL, NULL, 'Unpaid', ?)
                """,
                (
                    v["id"],
                    str(v["plate_number"]).strip().upper(),
                    norm_type,
                    entry_time_str,
                    rates["base_fee"],
                    rates["additional_hourly_fee"],
                    entry_time_str,
                ),
            )
            created_count += 1

        elif status == "Exited":
            # For exited records, exit_time must be valid and exit >= entry
            try:
                duration_minutes = calculate_duration_minutes(entry_time_str, exit_time_str)
                calc = calculate_fee(
                    norm_type,
                    duration_minutes,
                    rate_base_fee=rates["base_fee"],
                    rate_additional_hourly=rates["additional_hourly_fee"],
                )
                connection.execute(
                    """
                    INSERT INTO parking_fees
                    (vehicle_record_id, plate_number, vehicle_type, entry_time, exit_time,
                     duration_minutes, rate_base_fee, rate_additional_hourly, base_fee,
                     additional_hours, additional_fee, total_fee, payment_status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Unpaid', ?)
                    """,
                    (
                        v["id"],
                        str(v["plate_number"]).strip().upper(),
                        norm_type,
                        entry_time_str,
                        exit_time_str,
                        calc["duration_minutes"],
                        rates["base_fee"],
                        rates["additional_hourly_fee"],
                        calc["base_fee"],
                        calc["additional_hours"],
                        calc["additional_fee"],
                        calc["total_fee"],
                        entry_time_str,
                    ),
                )
                created_count += 1
            except Exception:
                # Do not invent values or modify vehicle_records
                continue

    return created_count

