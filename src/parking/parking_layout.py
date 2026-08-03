import os
import csv
import cv2

# Dataset folder
dataset_folder = "data/pklot/test"

# Output folder
output_folder = "output/parking_layout"
os.makedirs(output_folder, exist_ok=True)

# Find first image
image_files = sorted([
    f for f in os.listdir(dataset_folder)
    if f.lower().endswith((".jpg", ".jpeg", ".png"))
])

if len(image_files) == 0:
    raise Exception("No images found.")

image_name = image_files[0]

image_path = os.path.join(dataset_folder, image_name)
label_path = os.path.join(
    dataset_folder,
    os.path.splitext(image_name)[0] + ".txt"
)

if not os.path.exists(label_path):
    raise Exception(f"Label file not found:\n{label_path}")

image = cv2.imread(image_path)

if image is None:
    raise Exception("Unable to read image.")

# Save original parking image (only once)
base_image_path = os.path.join(output_folder, "base_layout.jpg")

if not os.path.exists(base_image_path):
    cv2.imwrite(base_image_path, image)
    print("Original image saved\n",base_image_path)

height, width = image.shape[:2]

spaces = []

# Read YOLO annotations
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

# Sort parking spaces
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

    if space["class"] == 0:
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

# Save image
image_output = os.path.join(
    output_folder,
    "parking_layout.jpg"
)

cv2.imwrite(image_output, image)

# Save CSV
csv_output = os.path.join(
    output_folder,
    "parking_layout.csv"
)

with open(csv_output, "w", newline="", encoding="utf-8") as file:

    writer = csv.writer(file)

    writer.writerow([
        "slot",
        "status",
        "x1",
        "y1",
        "x2",
        "y2",
        "row",
        "column"
    ])

    writer.writerows(csv_data)

print("Parking layout image saved:")
print(image_output)

print("Parking layout CSV saved:")
print(csv_output)