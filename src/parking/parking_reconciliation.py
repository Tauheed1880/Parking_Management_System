import hashlib
from pathlib import Path

import cv2
import pandas as pd
from ultralytics import YOLO

from app.database import sqlite_db


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LAYOUT_FOLDER = PROJECT_ROOT / "output" / "parking_layout"
PARKING_MODEL_PATH = PROJECT_ROOT / "models" / "parking_lot.pt"

VEHICLE_CATEGORY = {
    "car": "car",
    "bus": "bus",
    "motorcycle": "motorcycle",
    "truck": "bus",
}
LAYOUT_FILENAMES = {
    "car": "car_base_layout.jpg",
    "bus": "bus_base_layout.jpg",
    "motorcycle": "motorcycle_base_layout.jpg",
}
MODEL_CLASSES = {0: "space-empty", 1: "space-occupied"}
SLOT_COLUMNS = ["slot", "status", "row", "column", "x1", "y1", "x2", "y2"]
DUPLICATE_IOU_THRESHOLD = 0.75


class ParkingError(Exception):
    def __init__(self, code, message, status_code=409, data=None):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.data = data


try:
    parking_model = YOLO(str(PARKING_MODEL_PATH))
    if parking_model.names != MODEL_CLASSES:
        raise RuntimeError(f"Unexpected parking model classes: {parking_model.names}")
    parking_model_error = None
except Exception as exc:
    parking_model = None
    parking_model_error = str(exc)


def get_category(vehicle_type):
    category = VEHICLE_CATEGORY.get(str(vehicle_type).strip().lower())
    if category is None:
        raise ParkingError("unsupported_vehicle_type", "Vehicle type is not supported.", 422)
    return category


def canonical_layout_path(category):
    filename = LAYOUT_FILENAMES.get(category)
    if filename is None:
        raise ParkingError("missing_layout", f"No canonical layout is configured for {category}.", 503)
    return LAYOUT_FOLDER / filename


def _read_layout_image(category):
    image_path = canonical_layout_path(category)
    if not image_path.is_file():
        raise ParkingError("missing_layout", f"Canonical {category} layout image is missing.", 503)
    image = cv2.imread(str(image_path))
    if image is None:
        raise ParkingError("unreadable_layout", f"Canonical {category} layout image cannot be read.", 503)
    digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
    relative_path = image_path.relative_to(PROJECT_ROOT).as_posix()
    return image_path, image, digest, relative_path


def _iou(box_a, box_b):
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_a = max(0.0, box_a[2] - box_a[0]) * max(0.0, box_a[3] - box_a[1])
    area_b = max(0.0, box_b[2] - box_b[0]) * max(0.0, box_b[3] - box_b[1])
    union = area_a + area_b - intersection
    return intersection / union if union else 0.0


def _letter_for_row(index):
    label = ""
    number = index + 1
    while number:
        number, remainder = divmod(number - 1, 26)
        label = chr(ord("A") + remainder) + label
    return label


def _detect_slots(category, image):
    if parking_model is None:
        raise ParkingError("model_error", f"Parking-space model could not be loaded: {parking_model_error}", 503)
    try:
        result = parking_model.predict(source=image, verbose=False)[0]
    except Exception as exc:
        raise ParkingError("model_error", f"Parking-space inference failed: {exc}", 500)

    image_height, image_width = image.shape[:2]
    minimum_width = max(10.0, image_width * 0.012)
    minimum_height = max(8.0, image_height * 0.012)
    minimum_area = image_width * image_height * 0.0002
    detections = []
    tiny_dropped = 0

    for box in result.boxes:
        class_id = int(box.cls[0])
        if class_id not in MODEL_CLASSES:
            raise ParkingError("model_error", f"Unexpected parking-space class ID {class_id}.", 500)
        raw = [float(value) for value in box.xyxy[0].tolist()]
        coordinates = (
            max(0.0, min(float(image_width - 1), raw[0])),
            max(0.0, min(float(image_height - 1), raw[1])),
            max(0.0, min(float(image_width - 1), raw[2])),
            max(0.0, min(float(image_height - 1), raw[3])),
        )
        width = coordinates[2] - coordinates[0]
        height = coordinates[3] - coordinates[1]
        if width < minimum_width or height < minimum_height or width * height < minimum_area:
            tiny_dropped += 1
            continue
        detections.append(
            {
                "box": coordinates,
                "class_id": class_id,
                "confidence": float(box.conf[0]),
            }
        )

    detections.sort(key=lambda item: item["confidence"], reverse=True)
    merged = []
    duplicate_count = 0
    for detection in detections:
        if any(
            _iou(detection["box"], selected["box"]) >= DUPLICATE_IOU_THRESHOLD
            for selected in merged
        ):
            duplicate_count += 1
            continue
        merged.append(detection)

    if not merged:
        raise ParkingError("no_slots_detected", f"No parking spaces were detected for {category}.", 503)

    median_height = sorted(
        detection["box"][3] - detection["box"][1] for detection in merged
    )[len(merged) // 2]
    row_tolerance = max(12.0, median_height * 0.75)
    rows = []
    for detection in sorted(
        merged,
        key=lambda item: (
            (item["box"][1] + item["box"][3]) / 2,
            (item["box"][0] + item["box"][2]) / 2,
        ),
    ):
        center_y = (detection["box"][1] + detection["box"][3]) / 2
        candidates = []
        for row_index, row in enumerate(rows):
            row_center = sorted(row["centers"])[len(row["centers"]) // 2]
            distance = abs(center_y - row_center)
            if distance <= row_tolerance:
                candidates.append((distance, row_index))
        if candidates:
            _, row_index = min(candidates)
            rows[row_index]["detections"].append(detection)
            rows[row_index]["centers"].append(center_y)
        else:
            rows.append({"detections": [detection], "centers": [center_y]})

    rows.sort(key=lambda row: sum(row["centers"]) / len(row["centers"]))
    records = []
    row_report = []
    for row_index, row in enumerate(rows):
        row_name = _letter_for_row(row_index)
        ordered = sorted(row["detections"], key=lambda item: (item["box"][0] + item["box"][2]) / 2)
        for column, detection in enumerate(ordered, start=1):
            x1, y1, x2, y2 = detection["box"]
            records.append(
                {
                    "slot": f"{row_name}{column}",
                    "status": "empty" if detection["class_id"] == 0 else "occupied",
                    "row": row_name,
                    "column": column,
                    "x1": round(x1, 2),
                    "y1": round(y1, 2),
                    "x2": round(x2, 2),
                    "y2": round(y2, 2),
                }
            )
        centers = row["centers"]
        span = max(centers) - min(centers)
        row_report.append(
            {
                "row": row_name,
                "slots": len(ordered),
                "y_center_min": round(min(centers), 1),
                "y_center_max": round(max(centers), 1),
                "y_center_span": round(span, 1),
                "looks_suspicious": span > row_tolerance * 1.5 or len(ordered) == 1,
            }
        )

    return records, {
        "category": category,
        "slots_detected": len(records),
        "rows_found": len(rows),
        "row_tolerance_pixels": round(row_tolerance, 1),
        "tiny_dropped": tiny_dropped,
        "duplicates_merged": duplicate_count,
        "rows": row_report,
    }


def _generate_and_store(category, allow_replace=False):
    image_path, image, image_hash, relative_path = _read_layout_image(category)
    records, report = _detect_slots(category, image)
    connection = sqlite_db.get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        active_count = connection.execute(
            "SELECT COUNT(*) FROM vehicle_records WHERE layout_id = ? AND status = 'Inside'",
            (category,),
        ).fetchone()[0]
        if allow_replace and active_count:
            raise ParkingError(
                "active_assignments_exist",
                f"Cannot regenerate the {category} layout while vehicles are actively assigned.",
                409,
            )
        existing = connection.execute(
            "SELECT COUNT(*) FROM slots WHERE layout_id = ?", (category,)
        ).fetchone()[0]
        if existing and not allow_replace:
            raise ParkingError("layout_already_generated", f"The {category} layout already has stored slots.", 409)

        connection.execute(
            "INSERT INTO layouts(type, image_path, sha256) VALUES (?, ?, ?) "
            "ON CONFLICT(type) DO UPDATE SET image_path = excluded.image_path, sha256 = excluded.sha256",
            (category, relative_path, image_hash),
        )
        if allow_replace or existing == 0:
            connection.execute("DELETE FROM slots WHERE layout_id = ?", (category,))
        connection.executemany(
            "INSERT INTO slots(layout_id, slot, row, column, x1, y1, x2, y2, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    category,
                    item["slot"],
                    item["row"],
                    item["column"],
                    item["x1"],
                    item["y1"],
                    item["x2"],
                    item["y2"],
                    item["status"],
                )
                for item in records
            ],
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return report


def initialize_layouts():
    """Generate only categories with no saved slots; never re-number existing rows."""
    sqlite_db.initialize_database()
    reports = []
    for category in LAYOUT_FILENAMES:
        image_path, _, image_hash, relative_path = _read_layout_image(category)
        connection = sqlite_db.get_connection()
        try:
            layout = connection.execute(
                "SELECT image_path, sha256 FROM layouts WHERE type = ?", (category,)
            ).fetchone()
            slot_count = connection.execute(
                "SELECT COUNT(*) FROM slots WHERE layout_id = ?", (category,)
            ).fetchone()[0]
            active_count = connection.execute(
                "SELECT COUNT(*) FROM vehicle_records WHERE layout_id = ? AND status = 'Inside'",
                (category,),
            ).fetchone()[0]
        finally:
            connection.close()

        if slot_count == 0:
            if active_count:
                raise ParkingError(
                    "assignment_conflict",
                    f"The {category} layout has active records but no stored slots.",
                    409,
                )
            reports.append(_generate_and_store(category))
            continue

        if layout is None:
            raise ParkingError("layout_metadata_missing", f"The {category} layout metadata is missing.", 503)
        if layout["sha256"] != image_hash or layout["image_path"] != relative_path:
            raise ParkingError(
                "layout_image_changed",
                f"The {category} base image changed; use the manual regenerate function to rebuild its slots.",
                409,
            )
        reports.append(_stored_layout_report(category))
    return reports


def _stored_layout_report(category):
    connection = sqlite_db.get_connection()
    try:
        rows = connection.execute(
            "SELECT row, COUNT(*) AS slot_count FROM slots WHERE layout_id = ? GROUP BY row ORDER BY MIN(y1)",
            (category,),
        ).fetchall()
        slot_count = connection.execute(
            "SELECT COUNT(*) FROM slots WHERE layout_id = ?", (category,)
        ).fetchone()[0]
    finally:
        connection.close()
    return {
        "category": category,
        "slots_detected": slot_count,
        "rows_found": len(rows),
        "rows": [
            {"row": item["row"], "slots": item["slot_count"], "looks_suspicious": False}
            for item in rows
        ],
    }


def regenerate_layout(vehicle_type):
    """Manually rerun parking-space inference for a category with no active vehicles."""
    return _generate_and_store(get_category(vehicle_type), allow_replace=True)


def reconcile_layout(vehicle_type):
    category = get_category(vehicle_type)
    _, _, image_hash, relative_path = _read_layout_image(category)
    connection = sqlite_db.get_connection()
    try:
        layout = connection.execute(
            "SELECT image_path, sha256 FROM layouts WHERE type = ?", (category,)
        ).fetchone()
        if layout is None:
            raise ParkingError("layout_not_initialized", f"The {category} layout has not been generated yet.", 503)
        if layout["sha256"] != image_hash or layout["image_path"] != relative_path:
            raise ParkingError(
                "layout_image_changed",
                f"The {category} base image changed; use the manual regenerate function to rebuild its slots.",
                409,
            )
        slot_rows = connection.execute(
            "SELECT slot, row, column, x1, y1, x2, y2, status "
            "FROM slots WHERE layout_id = ? ORDER BY row, column",
            (category,),
        ).fetchall()
        active_rows = connection.execute(
            "SELECT plate_number, assigned_slot FROM vehicle_records "
            "WHERE layout_id = ? AND status = 'Inside'",
            (category,),
        ).fetchall()
    except ParkingError:
        raise
    except Exception as exc:
        raise ParkingError("layout_read_error", f"The {category} slots could not be loaded from SQLite: {exc}", 500)
    finally:
        connection.close()

    if not slot_rows:
        raise ParkingError("layout_not_initialized", f"The {category} layout has no stored slots.", 503)

    slots = pd.DataFrame(
        [
            {
                "slot": str(row["slot"]),
                "status": str(row["status"]),
                "row": str(row["row"]),
                "column": int(row["column"]),
                "x1": float(row["x1"]),
                "y1": float(row["y1"]),
                "x2": float(row["x2"]),
                "y2": float(row["y2"]),
            }
            for row in slot_rows
        ],
        columns=SLOT_COLUMNS,
    )
    model_states = slots["status"].tolist()
    protected = {}
    known_slots = set(slots["slot"].astype(str))
    for record in active_rows:
        assigned_slot = str(record["assigned_slot"] or "")
        if not assigned_slot or assigned_slot not in known_slots:
            raise ParkingError(
                "assignment_conflict",
                f"Active vehicle {record['plate_number']} has an invalid {category} slot assignment.",
                409,
            )
        if assigned_slot in protected:
            raise ParkingError(
                "assignment_conflict",
                f"Multiple active vehicles are assigned to {category} slot {assigned_slot}.",
                409,
            )
        protected[assigned_slot] = str(record["plate_number"])

    for index, slot in slots.iterrows():
        if str(slot["slot"]) in protected:
            slots.at[index, "status"] = "occupied"

    total = len(slots)
    occupied = int(slots["status"].eq("occupied").sum())
    empty = int(slots["status"].eq("empty").sum())
    layout = {
        "category": category,
        "path": (LAYOUT_FOLDER / f"{category}_live_layout.jpg").relative_to(PROJECT_ROOT).as_posix(),
        "base_path": relative_path,
        "sha256": image_hash,
    }
    return {
        "category": category,
        "layout": layout,
        "slots": slots,
        "model_states": model_states,
        "protected_slots": protected,
        "occupancy": {
            "total": total,
            "empty": empty,
            "occupied": occupied,
            "total_slots": total,
            "usable_empty": empty,
        },
        "generation": _stored_layout_report(category),
    }
