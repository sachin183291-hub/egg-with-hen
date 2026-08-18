"""
Egg Tray Detection Training Script
====================================
Trains a YOLOv8 model to detect and count physical egg trays.
Target class: 0 = egg_tray

ANNOTATION RULES:
  - Annotate each PHYSICAL TRAY separately (one bounding box per tray layer)
  - Do NOT annotate eggs, holes, cavities, background, walls, or floor
  - Use data.yaml with: names: {0: egg_tray}

USAGE:
  python train.py
"""
import os
import shutil
# pyrefly: ignore [missing-import]
from ultralytics import YOLO


def main():
    print("=" * 60)
    print("  EGG TRAY DETECTION - Training Script")
    print("  Target class: egg_tray (0)")
    print("=" * 60)

    # Use YOLOv8s (small) — better accuracy than nano for distinguishing
    # stacked tray boundaries. Upgrade to yolov8m.pt for even better results.
    model_pretrained = "yolov8s.pt"

    if not os.path.exists(model_pretrained):
        print(f"Downloading pretrained weights: {model_pretrained}")

    model = YOLO(model_pretrained)

    data_yaml_path = os.path.abspath("data.yaml")
    print(f"\nDataset config: {data_yaml_path}")
    print("Starting training...\n")

    results = model.train(
        data=data_yaml_path,
        epochs=100,          # More epochs for complex stacked-tray patterns
        imgsz=1280,          # High resolution — critical for counting individual tray layers
        batch=8,             # Reduce if GPU memory is limited
        name="egg_tray_detector",
        device="cpu",        # Switch to 0 (GPU index) if CUDA is available
        patience=20,         # Early stopping if no improvement for 20 epochs

        # ─── Augmentation (helps generalise across lighting, angles, stack heights)
        augment=True,
        hsv_h=0.015,         # Hue shift — handle different tray colours (green/brown/grey)
        hsv_s=0.7,           # Saturation — handle shadows and uneven lighting
        hsv_v=0.4,           # Brightness — handle warehouse lighting conditions
        degrees=10.0,        # Rotation — handle tilted camera shots
        translate=0.1,       # Translation — handle partial tray visibility
        scale=0.5,           # Scale — handle different distances from camera
        shear=2.0,           # Shear — handle perspective distortion
        perspective=0.0005,  # Perspective warp — handle camera angle variation
        flipud=0.3,          # Vertical flip
        fliplr=0.5,          # Horizontal flip
        mosaic=1.0,          # Mosaic — combine 4 images for context variety
        mixup=0.1,           # Mixup — blend images for robustness
        copy_paste=0.1,      # Copy-paste augmentation for instance variety

        # ─── NMS / detection settings
        iou=0.45,            # IoU threshold for NMS — prevents double-counting same tray
        conf=0.40,           # Confidence threshold

        verbose=True,
    )

    print("\n" + "=" * 60)
    print("  Training Complete! Validating model...")
    print("=" * 60)
    metrics = model.val()
    map50 = metrics.box.map50
    map50_95 = metrics.box.map
    print(f"\n  mAP@50:    {map50:.4f}")
    print(f"  mAP@50-95: {map50_95:.4f}")

    # ─── Save best weights
    best_weights = os.path.abspath("runs/detect/egg_tray_detector/weights/best.pt")
    if os.path.exists(best_weights):
        os.makedirs("models", exist_ok=True)

        # Primary model path (used by giotag backend yolo_service.py)
        primary = os.path.abspath("models/egg_tray_best.pt")
        shutil.copy(best_weights, primary)
        print(f"\n  ✅ Saved best model → {primary}")

        # Also copy under legacy name so existing yolo_service picks it up
        legacy = os.path.abspath("models/egg_detector.pt")
        shutil.copy(best_weights, legacy)
        print(f"  ✅ Also saved → {legacy}")
    else:
        print("\n  ⚠️  Best weights not found. Check training run directory.")

    print("\n  To evaluate counting accuracy, run:")
    print("  python count_validation.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
