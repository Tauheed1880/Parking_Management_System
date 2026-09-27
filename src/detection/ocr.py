import os
import cv2
import re
import csv
from paddleocr import PaddleOCR

# -----------------------------------
# OUTPUT FOLDER
# -----------------------------------

ocr_output_folder = "output/ocr_results"

os.makedirs(
    ocr_output_folder,
    exist_ok=True
)

csv_path = os.path.join(
    ocr_output_folder,
    "plate_results.csv"
)

# -----------------------------------
# LOAD OCR MODEL
# -----------------------------------

print("Loading PaddleOCR...")

reader = PaddleOCR(lang="en")

print("PaddleOCR loaded successfully.\n")


# -----------------------------------
# CLEAN TEXT
# -----------------------------------

def clean_plate_text(text):

    text = text.upper()

    text = re.sub(
        r"[^A-Z0-9]",
        "",
        text
    )

    return text


# -----------------------------------
# OCR FUNCTION
# -----------------------------------

def read_plate(plate_image_paths):

    ocr_records = []

    for plate_path in plate_image_paths:

        filename = os.path.basename(
            plate_path
        )

        plate = cv2.imread(
            plate_path
        )

        if plate is None:
            continue

        print(f"Processing: {filename}")

        results = reader.predict(
            plate
        )

        detected_texts = []

        confidences = []

        # ----------------------------
        # READ TEXT
        # ----------------------------

        for result in results:
           
            result_dict = result.json
            res = result_dict["res"]

            texts = res.get("rec_texts", [])
            scores = res.get("rec_scores", [])

            for text, confidence in zip(
                texts,
                scores
            ):

                cleaned_text = clean_plate_text(
                    text
                )

                if cleaned_text:

                    detected_texts.append(
                        cleaned_text
                    )

                    confidences.append(
                        float(confidence)
                    )

                    print(
                        f"Detected: {cleaned_text}"
                    )

        # ----------------------------
        # OCR RESULT
        # ----------------------------

        if detected_texts:

            plate_number = "".join(
                detected_texts
            )

            average_confidence = (
                sum(confidences)
                / len(confidences)
            )

            status = "Detected"


        else:

            plate_number = ""

            average_confidence = 0.0

            status = "No text detected"

        # ----------------------------
        # STORE OCR RECORD
        # ----------------------------

        
        ocr_records.append({

            "image": filename,

            "plate_number": plate_number,

            "confidence": round(
                average_confidence,
                2
            ),

            "status": status

        })

        print("-" * 50)

    # ----------------------------
    # SAVE CSV
    # ----------------------------

    with open(
        csv_path,
        mode="w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(

            file,

            fieldnames=[

                "image",

                "plate_number",

                "confidence",

                "status"

            ]

        )

        writer.writeheader()

        writer.writerows(
            ocr_records
        )

    print("\nOCR completed.")

    print(
        f"Results saved to: {csv_path}"
    )

    return csv_path, ocr_records


