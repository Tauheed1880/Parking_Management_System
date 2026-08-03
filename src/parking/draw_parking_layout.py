import cv2
import pandas as pd

# Original parking image (without boxes)
IMAGE_PATH = "output/parking_layout/base_layout.jpg"

# Parking layout CSV
CSV_PATH = "output/parking_layout/parking_layout.csv"

# Output image
OUTPUT_PATH = "output/parking_layout/parking_layout.jpg"


def draw_parking_layout():

    image = cv2.imread(IMAGE_PATH)

    if image is None:
        print("Could not load parking image.")
        return None

    df = pd.read_csv(CSV_PATH)

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

    cv2.imwrite(OUTPUT_PATH, image)

    print("Parking layout updated.")
    print(OUTPUT_PATH)

    return OUTPUT_PATH