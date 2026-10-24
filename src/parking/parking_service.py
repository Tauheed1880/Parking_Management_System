import threading
import uuid
from pathlib import Path
from urllib.parse import quote

import cv2
import numpy as np

from src.detection.ocr import read_plate
from src.detection.plate_detection import detect_plate
from src.detection.vehicle_detection import detect_vehicle
from src.parking import parking_allocation, vehicle_database
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


def process_vehicle_image(contents, original_filename):
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

        if vehicle_database.is_vehicle_inside(plate_number):
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

            # Keep the active slot protected during inference, then record the explicit exit.
            vehicle_database.update_exit_time(plate_number)
            reconciliation = reconcile_layout(stored_type)
            try:
                draw_parking_layout(stored_category, assigned_slot)
            except Exception as exc:
                raise ParkingError("layout_render_error", f"The live layout image could not be updated: {exc}", 500)
            return {
                "action": "exit",
                "vehicle_type": detected_type,
                "plate_result": plate_result,
                "ocr_confidence": plate_result.get("confidence"),
                "images": images,
                "selected_layout": reconciliation["layout"],
                "assigned_slot": assigned_slot,
                "occupancy": reconciliation["occupancy"],
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
            vehicle_database.add_vehicle(
                plate_number,
                detected_type,
                assigned_slot=assigned_slot,
                layout_id=category,
            )
        except vehicle_database.AssignmentConflictError as exc:
            raise ParkingError("assignment_conflict", str(exc), 409)
        except Exception as exc:
            raise ParkingError("record_error", f"Vehicle record could not be saved: {exc}", 500)

        if vehicle_database.get_assigned_slot(plate_number) != assigned_slot:
            raise ParkingError("assignment_conflict", "The saved assignment does not match the selected slot.", 409)

        reconciliation = reconcile_layout(detected_type)
        try:
            draw_parking_layout(category, assigned_slot)
        except Exception as exc:
            raise ParkingError("layout_render_error", f"The live layout image could not be updated: {exc}", 500)

        return {
            "action": "entry",
            "vehicle_type": detected_type,
            "plate_result": plate_result,
            "ocr_confidence": plate_result.get("confidence"),
            "images": images,
            "selected_layout": reconciliation["layout"],
            "assigned_slot": assigned_slot,
            "occupancy": reconciliation["occupancy"],
        }
