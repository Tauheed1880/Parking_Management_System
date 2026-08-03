import os
import cv2
from ultralytics import YOLO

# Load YOLO model only once
model = YOLO("models/yolo11n.pt")


def detect_vehicle(
    image_path,
    vehicle_folder="output/vehicle_crops",
    bounding_box_folder="output/vehicle_bounding_boxes"
):
    """
    Detect vehicles from an image.

    Returns:
        annotated_image_path
        vehicle_image_paths (list)
    """

    os.makedirs(vehicle_folder, exist_ok=True)
    os.makedirs(bounding_box_folder, exist_ok=True)

    frame = cv2.imread(image_path)

    if frame is None:
        raise Exception(f"Unable to read image: {image_path}")

    filename = os.path.basename(image_path)

    print(f"\nProcessing: {filename}")

    results = model(frame, classes=[2, 3, 5, 7])

    vehicle_count = 0
    vehicle_image_paths = []

    # ----------------------------
    # Crop Vehicles
    # ----------------------------

    for result in results:

        for box in result.boxes:

            confidence = float(box.conf[0])

            if confidence < 0.5:
                continue

            vehicle_count += 1

            x1, y1, x2, y2 = map(int, box.xyxy[0])

            cropped_vehicle = frame[y1:y2, x1:x2]

            if cropped_vehicle.size == 0:
                continue

            original_name = os.path.splitext(filename)[0]
            extension = os.path.splitext(filename)[1]

            vehicle_filename = (
                f"{original_name}_vehicle_{vehicle_count}{extension}"
            )

            vehicle_path = os.path.join(
                vehicle_folder,
                vehicle_filename
            )

            cv2.imwrite(vehicle_path, cropped_vehicle)

            vehicle_image_paths.append(vehicle_path)

            print(f"Saved Vehicle: {vehicle_path}")

    # ----------------------------
    # Bounding Boxes
    # ----------------------------

    annotated_image = frame.copy()

    for result in results:
        annotated_image = result.plot()

    annotated_image_path = os.path.join(
        bounding_box_folder,
        filename
    )

    cv2.imwrite(
        annotated_image_path,
        annotated_image
    )

    print(f"Saved Bounding Box Image: {annotated_image_path}")

    return annotated_image_path, vehicle_image_paths