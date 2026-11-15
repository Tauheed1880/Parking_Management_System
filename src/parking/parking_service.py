import threading
import uuid
from pathlib import Path
from urllib.parse import quote

import cv2
import numpy as np

from src.detection.ocr import read_plate
from src.detection.plate_detection import detect_plate
from src.detection.vehicle_detection import detect_vehicle
from src.parking import parking_allocation, parking_fee, vehicle_database
from src.parking.draw_parking_layout import draw_parking_layout
from src.parking.parking_reconciliation import (
    ParkingError,
    get_category,
    reconcile_layout,
)


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
PROCESS_LOCK = threading.Lock()
PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "output"


def _output_url(path):
    if not path:
        return None
    source = Path(path)
    if not source.is_absolute():
        source = Path.cwd() / source
    try:
        source = source.resolve()
        relative = source.relative_to(OUTPUT_DIR.resolve())
    except (OSError, ValueError):
        return None
    if not source.is_file():
        return None
    return "/output/" + quote(relative.as_posix())


def _request_image_urls(original_path, vehicle_detection_path, plate_detection_paths, plate_images):
    candidates = {
        "original": original_path,
        "vehicle_detection": vehicle_detection_path,
        "plate_detection": plate_detection_paths[0] if plate_detection_paths else None,
        "plate_crop": plate_images[0] if plate_images else None,
    }
    return {
        name: url
        for name, path in candidates.items()
        if (url := _output_url(path)) is not None
    }


def _allocate_from_snapshot(category, reconciliation):
    slots = reconciliation["slots"]
    if slots.empty:
        return None
    input_columns = ["slot", "status", "row", "column", "x1", "y1", "x2", "y2"]
    return parking_allocation.get_best_parking_slot(
        category,
        parking_df=slots[input_columns].copy(),
    )


def process_vehicle_image(contents, original_filename, mode="auto"):
    with PROCESS_LOCK:
        encoded = np.frombuffer(contents, dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if image is None:
            raise ParkingError("invalid_upload", "The uploaded file is not a readable image.", 400)

        suffix = Path(original_filename).suffix.lower() or ".jpg"
        safe_name = f"api_{uuid.uuid4().hex}{suffix}"
        upload_directory = OUTPUT_DIR / "vehicle_uploads"
        upload_directory.mkdir(parents=True, exist_ok=True)
        original_path = upload_directory / safe_name
        original_path.write_bytes(contents)
        try:
            vehicle_detection_path, vehicle_images, vehicle_types = detect_vehicle(image, safe_name)
        except Exception as exc:
            raise ParkingError("vehicle_model_error", f"Vehicle detection failed: {exc}", 500)
        if not vehicle_types or not vehicle_images:
            raise ParkingError("vehicle_not_detected", "No supported vehicle was detected in the image.", 422)

        detected_type = str(vehicle_types[0]).strip().lower()
        category = get_category(detected_type)
        reconciliation = reconcile_layout(detected_type)

        try:
            plate_detection_paths, plate_images = detect_plate(vehicle_images)
            if not plate_images:
                raise ParkingError("plate_unreadable", "No license plate was detected.", 422)
            _, ocr_records = read_plate(plate_images)
        except ParkingError:
            raise
        except Exception as exc:
            raise ParkingError("plate_model_error", f"License-plate processing failed: {exc}", 500)

        if not ocr_records or not str(ocr_records[0].get("plate_number", "")).strip():
            raise ParkingError(
                "plate_unreadable",
                "The detected license plate could not be read.",
                422,
                {
                    "vehicle_type": detected_type,
                    "selected_layout": reconciliation["layout"],
                    "occupancy": reconciliation["occupancy"],
                },
            )

        plate_result = ocr_records[0]
        plate_number = str(plate_result["plate_number"]).strip().upper()
        images = _request_image_urls(
            original_path,
            vehicle_detection_path,
            plate_detection_paths,
            plate_images,
        )

        is_inside = vehicle_database.is_vehicle_inside(plate_number)

        # Mode validation
        if mode == "entry" and is_inside:
            raise ParkingError("assignment_conflict", f"Vehicle {plate_number} is already recorded as inside.", 409)
        if mode == "exit" and not is_inside:
            raise ParkingError("vehicle_not_inside", f"Vehicle {plate_number} is not recorded as inside.", 404)

        should_exit = (mode == "exit") or (mode == "auto" and is_inside)

        if should_exit:
            vehicle_record = vehicle_database.get_vehicle(plate_number)
            if vehicle_record is None:
                raise ParkingError("assignment_conflict", "The active vehicle record could not be read.", 409)
            stored_type = str(vehicle_record["vehicle_type"]).strip().lower()
            stored_category = get_category(stored_type)
            assigned_slot = str(vehicle_record["assigned_slot"]).strip()
            if not assigned_slot:
                raise ParkingError("assignment_conflict", "The active vehicle has no assigned slot.", 409)
            if stored_category != category:
                reconciliation = reconcile_layout(stored_type)
            if assigned_slot not in set(reconciliation["slots"]["slot"].astype(str)):
                raise ParkingError("assignment_conflict", "The active slot is not present in the selected layout.", 409)

            # 1. Calculate and update parking fee using current exit detection time
            try:
                assessment = vehicle_database.assess_exit_fee(plate_number)
            except parking_fee.FeeCalculationError as exc:
                raise ParkingError("fee_calculation_error", str(exc), 400)
            except Exception as exc:
                raise ParkingError("exit_error", f"Fee assessment failed: {exc}", 500)

            fee_record = assessment.get("fee") if assessment else None
            payment_status = str(fee_record.get("payment_status", "Unpaid") if fee_record else "Unpaid").strip().lower()

            # 2. When payment is Unpaid: block exit authorization, keep vehicle Inside, keep slot occupied
            if payment_status != "paid":
                reconciliation = reconcile_layout(stored_type)
                return {
                    "action": "exit_blocked",
                    "exit_authorized": False,
                    "status": "Payment Blocked",
                    "message": "Payment required before exit.",
                    "vehicle_type": detected_type,
                    "plate_result": plate_result,
                    "ocr_confidence": plate_result.get("confidence"),
                    "images": images,
                    "selected_layout": reconciliation["layout"],
                    "assigned_slot": assigned_slot,
                    "occupancy": reconciliation["occupancy"],
                    "fee": fee_record,
                }

            # 3. When payment is Paid: allow exit authorization, finalize exit and release slot
            try:
                exit_result = vehicle_database.finalize_exit(plate_number)
            except Exception as exc:
                raise ParkingError("exit_error", f"Vehicle exit could not be finalized: {exc}", 500)

            reconciliation = reconcile_layout(stored_type)
            try:
                draw_parking_layout(stored_category, assigned_slot)
            except Exception as exc:
                raise ParkingError("layout_render_error", f"The live layout image could not be updated: {exc}", 500)

            final_fee = exit_result.get("fee") if exit_result else fee_record
            return {
                "action": "exit",
                "exit_authorized": True,
                "status": "Payment Paid - Exit Authorized",
                "message": "Exit authorized. Parking slot released.",
                "vehicle_type": detected_type,
                "plate_result": plate_result,
                "ocr_confidence": plate_result.get("confidence"),
                "images": images,
                "selected_layout": reconciliation["layout"],
                "assigned_slot": assigned_slot,
                "occupancy": reconciliation["occupancy"],
                "fee": final_fee,
            }

        assigned_slot = _allocate_from_snapshot(category, reconciliation)
        if assigned_slot is None:
            raise ParkingError(
                "no_available_space",
                f"No safely matched consecutive parking space is available for {category}.",
                409,
                {"occupancy": reconciliation["occupancy"]},
            )

        if assigned_slot in reconciliation["protected_slots"]:
            raise ParkingError(
                "assignment_conflict",
                f"Allocator selected protected active slot {assigned_slot}.",
                409,
                {"slot": assigned_slot},
            )

        active_records = vehicle_database.load_database()
        if not active_records.empty:
            active_records = active_records[active_records["status"].astype(str).str.casefold().eq("inside")]
            if (active_records["plate_number"].astype(str).str.upper() == plate_number).any():
                raise ParkingError("assignment_conflict", "This plate already has an active assignment.", 409)

        try:
            record_id = vehicle_database.add_vehicle(
                plate_number,
                detected_type,
                assigned_slot=assigned_slot,
                layout_id=category,
                province=plate_result.get("province"),
            )
        except vehicle_database.AssignmentConflictError as exc:
            raise ParkingError("assignment_conflict", str(exc), 409)
        except parking_fee.FeeCalculationError as exc:
            raise ParkingError("fee_calculation_error", str(exc), 400)
        except Exception as exc:
            raise ParkingError("record_error", f"Vehicle record could not be saved: {exc}", 500)

        if vehicle_database.get_assigned_slot(plate_number) != assigned_slot:
            raise ParkingError("assignment_conflict", "The saved assignment does not match the selected slot.", 409)

        reconciliation = reconcile_layout(detected_type)
        try:
            draw_parking_layout(category, assigned_slot)
        except Exception as exc:
            raise ParkingError("layout_render_error", f"The live layout image could not be updated: {exc}", 500)

        fee_record = parking_fee.get_fee_by_vehicle_record_id(record_id) if record_id else None
        return {
            "action": "entry",
            "vehicle_type": detected_type,
            "plate_result": plate_result,
            "ocr_confidence": plate_result.get("confidence"),
            "images": images,
            "selected_layout": reconciliation["layout"],
            "assigned_slot": assigned_slot,
            "occupancy": reconciliation["occupancy"],
            "fee": fee_record,
        }


def process_vehicle_entry(contents, original_filename):
    return process_vehicle_image(contents, original_filename, mode="entry")


def process_vehicle_exit(contents, original_filename):
    return process_vehicle_image(contents, original_filename, mode="exit")
