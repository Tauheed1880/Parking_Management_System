import os
import cv2
from ultralytics import YOLO

# Load model only once
model = YOLO("models/plate_detection_model.pt")

def detect_plate(
    vehicle_image_paths,
    plate_folder="output/plate_crops",
    bounding_box_folder="output/plate_bounding_boxes"
):
    """
    Detect license plates from cropped vehicle images.

    Returns:
        bounding_box_image_paths (list)
        plate_image_paths (list)
    """

    os.makedirs(plate_folder, exist_ok=True)
    os.makedirs(bounding_box_folder, exist_ok=True)

    plate_image_paths = []
    bounding_box_image_paths = []

    for vehicle_path in vehicle_image_paths:

        vehicle = cv2.imread(vehicle_path)

        if vehicle is None:
            continue

        filename = os.path.basename(vehicle_path)

        print(f"Processing: {filename}")

        results = model(vehicle)

        # ----------------------------
        # Crop Plates
        # ----------------------------

        for result in results:

            for box in result.boxes:

                confidence = float(box.conf[0])

                if confidence < 0.5:
                    continue

                x1, y1, x2, y2 = map(int, box.xyxy[0])

                plate = vehicle[y1:y2, x1:x2]

                if plate.size == 0:
                    continue

                plate_path = os.path.join(
                    plate_folder,
                    filename
                )
                # processed_plate = preprocess_plate(plate)

                cv2.imwrite(
                    plate_path,
                    plate
                )
                plate_image_paths.append(
                    plate_path
                )

                print(f"Saved Plate: {plate_path}")

        # ----------------------------
        # Bounding Box Image
        # ----------------------------

        annotated_image = results[0].plot()

        bounding_box_path = os.path.join(
            bounding_box_folder,
            filename
        )

        cv2.imwrite(
            bounding_box_path,
            annotated_image
        )

        bounding_box_image_paths.append(
            bounding_box_path
        )

    print("\nLicense plate detection completed.")

    return (
        bounding_box_image_paths,
        plate_image_paths
    )