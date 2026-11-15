from pathlib import Path

import cv2

from src.parking.parking_reconciliation import (
    PROJECT_ROOT,
    canonical_layout_path,
    reconcile_layout,
)


OUTPUT_FOLDER = PROJECT_ROOT / "output" / "parking_layout"


def draw_parking_layout(vehicle_type, highlighted_slot=None):
    """Render stored model slots with live assignments on the canonical image."""
    result = reconcile_layout(vehicle_type)
    category = result["category"]
    image = cv2.imread(str(canonical_layout_path(category)))
    if image is None:
        raise FileNotFoundError(f"Canonical {category} layout image cannot be read.")

    if category == "bus":
        scale_ratio = image.shape[1] / 900.0
        font_scale = 0.45 * scale_ratio
        font_thickness = max(1, int(round(scale_ratio)))
        label_offset = int(round(5 * scale_ratio))
        label_min_y = int(round(16 * scale_ratio))
    else:
        font_scale = 0.45
        font_thickness = 1
        label_offset = 5
        label_min_y = 16

    for slot in result["slots"].itertuples(index=False):
        x1, y1, x2, y2 = (int(round(value)) for value in (slot.x1, slot.y1, slot.x2, slot.y2))
        color = (0, 255, 0) if slot.status == "empty" else (0, 0, 255)
        is_highlighted = str(slot.slot) == str(highlighted_slot or "")

        if is_highlighted:
            cv2.rectangle(image, (x1 - 3, y1 - 3), (x2 + 3, y2 + 3), (255, 0, 0), 4)
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
        label_y = max(label_min_y, y1 - label_offset)
        cv2.putText(
            image,
            str(slot.slot),
            (x1, label_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            color,
            font_thickness,
            cv2.LINE_AA,
        )

    output_path = OUTPUT_FOLDER / f"{category}_live_layout.jpg"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), image):
        raise OSError(f"Could not write annotated {category} layout image.")
    return str(output_path)
