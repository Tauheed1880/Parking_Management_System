import os
import csv
import cv2

VEHICLE_TYPES = {
    "car": "car_pklot",
    "motorcycle": "motorcycle_pklot",
    "bus": "bus_pklot",
}

EMPTY_CLASS_ID = {
    "car": 0,
    "motorcycle": 0,
    "bus": 1,
}

DATASET_ROOT = "data/pklot"
OUTPUT_FOLDER = "output/parking_layout"

os.makedirs(OUTPUT_FOLDER, exist_ok=True)


def generate_parking_layout(vehicle_type, folder_name):

    images_folder = os.path.join(DATASET_ROOT, folder_name, "images")
    labels_folder = os.path.join(DATASET_ROOT, folder_name, "labels")

    image_files = sorted([
        f for f in os.listdir(images_folder)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ])

    if len(image_files) == 0:
        print(f"No images found for {vehicle_type}, skipping.")
        return

    image_name = image_files[0]

    image_path = os.path.join(images_folder, image_name)
    label_path = os.path.join(
        labels_folder,
        os.path.splitext(image_name)[0] + ".txt"
    )

    if not os.path.exists(label_path):
        print(f"Label file not found for {vehicle_type}: {label_path}")
        return

    image = cv2.imread(image_path)

    if image is None:
        print(f"Unable to read image for {vehicle_type}.")
        return

    base_image_path = os.path.join(
        OUTPUT_FOLDER, f"{vehicle_type}_base_layout.jpg"
    )

    if not os.path.exists(base_image_path):
        cv2.imwrite(base_image_path, image)
        print(f"Original image saved: {base_image_path}")

    height, width = image.shape[:2]

    spaces = []

    with open(label_path, "r") as file:

        for line in file:

            values = line.strip().split()

            cls = int(values[0])

            x_center = float(values[1]) * width
            y_center = float(values[2]) * height
            box_width = float(values[3]) * width
            box_height = float(values[4]) * height

            x1 = int(x_center - box_width / 2)
            y1 = int(y_center - box_height / 2)
            x2 = int(x_center + box_width / 2)
            y2 = int(y_center + box_height / 2)

            spaces.append({
                "class": cls,
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "cx": x_center,
                "cy": y_center
            })

    spaces.sort(key=lambda s: (round(s["cy"] / 30), s["cx"]))

    current_row = -1
    previous_y = -100
    slot_number = 1

    csv_data = []

    for space in spaces:

        if abs(space["cy"] - previous_y) > 30:
            current_row += 1
            slot_number = 1
            previous_y = space["cy"]

        row_letter = chr(ord("A") + current_row)
        slot_id = f"{row_letter}{slot_number}"

        if space["class"] == EMPTY_CLASS_ID[vehicle_type]:
            status = "empty"
            color = (0, 255, 0)
        else:
            status = "occupied"
            color = (0, 0, 255)

        cv2.rectangle(
            image,
            (space["x1"], space["y1"]),
            (space["x2"], space["y2"]),
            color,
            2
        )

        cv2.putText(
            image,
            slot_id,
            (space["x1"], space["y1"] - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1
        )

        csv_data.append([
            slot_id,
            status,
            space["x1"],
            space["y1"],
            space["x2"],
            space["y2"],
            row_letter,
            slot_number
        ])

        slot_number += 1

    image_output = os.path.join(
        OUTPUT_FOLDER, f"{vehicle_type}_parking_layout.jpg"
    )
    cv2.imwrite(image_output, image)

    csv_output = os.path.join(
        OUTPUT_FOLDER, f"{vehicle_type}_parking_layout.csv"
    )

    with open(csv_output, "w", newline="", encoding="utf-8") as file:

        writer = csv.writer(file)

        writer.writerow([
            "slot", "status", "x1", "y1", "x2", "y2", "row", "column"
        ])

        writer.writerows(csv_data)

    print(f"Parking layout image saved: {image_output}")
    print(f"Parking layout CSV saved: {csv_output}")

if __name__ == "__main__":

    for vehicle_type, folder_name in VEHICLE_TYPES.items():
        generate_parking_layout(vehicle_type, folder_name)
