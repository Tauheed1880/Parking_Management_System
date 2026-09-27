import os
import sys
import pandas as pd
from difflib import SequenceMatcher

sys.path.append(
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            ".."
        )
    )
)

from src.detection.ocr import read_plate

# ============================================================
# CONFIGURATION
# ============================================================

PLATE_FOLDER = "output/plate_crops"
GROUND_TRUTH_FILE = "evaluation/ocr_ground_truth.csv"
RESULT_FILE = "evaluation/ocr_results.csv"

# Number of plates to evaluate
MAX_IMAGES = 50


# ============================================================
# CREATE EVALUATION FOLDER
# ============================================================

os.makedirs("evaluation", exist_ok=True)


# ============================================================
# GET PLATE IMAGES
# ============================================================

plate_files = [
    f
    for f in os.listdir(PLATE_FOLDER)
    if f.lower().endswith((".jpg", ".jpeg", ".png"))
]

plate_files = sorted(plate_files)

if len(plate_files) == 0:
    print("No plate images found.")
    print("Check:", PLATE_FOLDER)
    exit()

# Limit number of images
plate_files = plate_files[:MAX_IMAGES]

print("\n" + "=" * 70)
print("OCR EVALUATION")
print("=" * 70)
print("Plate images found:", len(plate_files))


# ============================================================
# LOAD OR CREATE GROUND TRUTH
# ============================================================

if os.path.exists(GROUND_TRUTH_FILE):
    print("\n[INFO] Found existing ground truth file. Loading from:", GROUND_TRUTH_FILE)
    df = pd.read_csv(GROUND_TRUTH_FILE)
else:
    print("\nEnter the actual number plate for each image.")
    print("Example: BAT777")
    print("Remove spaces when entering the plate number.")
    print("-" * 70)

    ground_truth = []

    for i, filename in enumerate(plate_files, 1):
        print(f"\n[{i}/{len(plate_files)}]")
        print("Image:", filename)

        actual_text = input("Actual plate number: ").strip()

        ground_truth.append({
            "image": filename,
            "actual_text": actual_text
        })

    df = pd.DataFrame(ground_truth)
    df.to_csv(GROUND_TRUTH_FILE, index=False)
    print("\nGround truth saved to:", GROUND_TRUTH_FILE)


# ============================================================
# PREPARE IMAGE PATHS
# ============================================================

plate_images = []

for filename in df["image"]:
    image_path = os.path.join(PLATE_FOLDER, filename)

    if os.path.exists(image_path):
        plate_images.append(image_path)
    else:
        print("WARNING: Image not found:", image_path)


# ============================================================
# RUN OCR
# ============================================================

print("\n" + "=" * 70)
print("RUNNING OCR")
print("=" * 70)

_, ocr_records = read_plate(plate_images)


# ============================================================
# CREATE PREDICTION LOOKUP
# ============================================================

predictions = {}

for record in ocr_records:
    raw_path = record.get("image", "")
    image_name = os.path.basename(raw_path) if raw_path else ""

    if image_name:
        predictions[image_name] = record.get("plate_number", "")


# ============================================================
# COMPARE OCR WITH GROUND TRUTH
# ============================================================

exact_matches = 0
character_scores = []
results = []

for _, row in df.iterrows():
    image_name = row["image"]

    actual = str(row["actual_text"]).upper().replace(" ", "")
    predicted = str(predictions.get(image_name, "")).upper().replace(" ", "")

    exact_match = actual == predicted
    if exact_match:
        exact_matches += 1

    similarity = SequenceMatcher(None, actual, predicted).ratio()
    character_scores.append(similarity)

    results.append({
        "image": image_name,
        "actual": actual,
        "predicted": predicted,
        "exact_match": exact_match,
        "character_similarity": similarity
    })


# ============================================================
# CALCULATE METRICS
# ============================================================

total = len(df)
exact_accuracy = (exact_matches / total) if total > 0 else 0
character_accuracy = (sum(character_scores) / len(character_scores)) if character_scores else 0


# ============================================================
# PRINT RESULTS
# ============================================================

print("\n" + "=" * 70)
print("OCR RESULTS")
print("=" * 70)

print(f"Total plates          : {total}")
print(f"Exact matches         : {exact_matches}")
print(f"Exact plate accuracy  : {exact_accuracy:.4f} ({exact_accuracy * 100:.2f}%)")
print(f"Character similarity  : {character_accuracy:.4f} ({character_accuracy * 100:.2f}%)")


# ============================================================
# DISPLAY INDIVIDUAL RESULTS
# ============================================================

print("\n" + "=" * 70)
print("INDIVIDUAL RESULTS")
print("=" * 70)

for result in results:
    status = "✓" if result["exact_match"] else "✗"
    print(
        f"{status} "
        f"{result['image']} | "
        f"Actual: {result['actual']} | "
        f"OCR: {result['predicted']} | "
        f"Similarity: {result['character_similarity']:.2f}"
    )


# ============================================================
# SAVE RESULTS
# ============================================================

results_df = pd.DataFrame(results)
results_df.to_csv(RESULT_FILE, index=False)


# ============================================================
# COMPLETE
# ============================================================

print("\n" + "=" * 70)
print("EVALUATION COMPLETE")
print("=" * 70)
print("Ground truth:", GROUND_TRUTH_FILE)
print("Detailed results:", RESULT_FILE)