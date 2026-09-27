import cv2
import pandas as pd

# # Original parking image (without boxes)
# IMAGE_PATH = "output/parking_layout/base_layout.jpg"

# # Parking layout CSV
# CSV_PATH = "output/parking_layout/parking_layout.csv"

# # Output image
# OUTPUT_PATH = "output/parking_layout/parking_layout.jpg"

OUTPUT_FOLDER = "output/parking_layout"

def draw_parking_layout(vehicle_type):

    image_path = f"{OUTPUT_FOLDER}/{vehicle_type}_base_layout.jpg"
    csv_path = f"{OUTPUT_FOLDER}/{vehicle_type}_parking_layout.csv"
    output_path = f"{OUTPUT_FOLDER}/{vehicle_type}_parking_layout.jpg"

    image = cv2.imread(image_path)

    if image is None:
        print("Could not load parking image.")
        return None

    df = pd.read_csv(csv_path)

    for _, row in df.iterrows():

        x1 = int(row["x1"])
        y1 = int(row["y1"])
        x2 = int(row["x2"])
        y2 = int(row["y2"])

        slot = row["slot"]
        status = row["status"]

        if status == "empty":
            color = (0, 255, 0)
        else:
            color = (0, 0, 255)

        cv2.rectangle(
            image,
            (x1, y1),
            (x2, y2),
            color,
            2
        )

        cv2.putText(
            image,
            slot,
            (x1, y1 - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1
        )

    cv2.imwrite(output_path, image)

    print("Parking layout updated.")
    print(output_path)

    return output_path