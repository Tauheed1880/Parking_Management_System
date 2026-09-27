from ultralytics import YOLO


# ============================================================
# STEP 1: LOAD MODEL
# ============================================================

model = YOLO("models/best.pt")


# ============================================================
# STEP 2: EVALUATE MODEL
# ============================================================

print("\n" + "=" * 60)
print("LICENSE PLATE DETECTOR EVALUATION")
print("=" * 60)

results = model.val(
    data="data/vehicle_images/data.yaml",
    split="test",
    imgsz=640,
    conf=0.25,
    iou=0.5
)

# ============================================================
# STEP 3: PRINT METRICS
# ============================================================

print("\n" + "=" * 60)
print("EVALUATION RESULTS")
print("=" * 60)

print(f"Precision : {results.box.mp:.4f}")
print(f"Recall    : {results.box.mr:.4f}")
print(f"mAP@50    : {results.box.map50:.4f}")
print(f"mAP@50-95 : {results.box.map:.4f}")


# ============================================================
# STEP 4: RUN PREDICTIONS ON TEST IMAGES
# ============================================================

print("\n" + "=" * 60)
print("GENERATING TEST PREDICTIONS")
print("=" * 60)

model.predict(
    source="data/vehicle_images/test/images",
    imgsz=640,
    conf=0.25,
    save=True
)

print("\nTest prediction images have been saved.")