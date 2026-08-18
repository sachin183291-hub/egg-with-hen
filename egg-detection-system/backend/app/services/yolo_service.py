import os
import cv2
import numpy as np
import base64
import time
# pyrefly: ignore [missing-import]
from ultralytics import YOLO, YOLOWorld

# Global model instance
model = None

# ─── Configurable model paths (egg tray detector) ─────────────────────────────
MODEL_PATH = os.path.join(os.path.dirname(__file__), "../../models/egg_tray_best.pt")
LEGACY_MODEL_PATH = os.path.join(os.path.dirname(__file__), "../../models/egg_detector.pt")
FALLBACK_MODEL = "yolov8s-world.pt"

# Configurable thresholds
DEFAULT_CONF_THRESHOLD = 0.40
DEFAULT_IOU_THRESHOLD  = 0.45


def load_model():
    """Load the egg tray detection model. Falls back to YOLO-World zero-shot if no custom model is found."""
    global model
    if model is None:
        try:
            if os.path.exists(MODEL_PATH):
                print(f"Loading tray model from {MODEL_PATH}")
                model = YOLO(MODEL_PATH)
            elif os.path.exists(LEGACY_MODEL_PATH):
                print(f"Loading tray model from {LEGACY_MODEL_PATH}")
                model = YOLO(LEGACY_MODEL_PATH)
            else:
                print("No custom tray model found. Using YOLO-World zero-shot for 'egg tray'.")
                fallback = FALLBACK_MODEL
                model = YOLOWorld(fallback)
                model.set_classes(["egg tray"])
        except Exception as e:
            print(f"Error loading model: {e}")
            raise
    return model


def detect_trays(image_bytes: bytes, conf_threshold: float = DEFAULT_CONF_THRESHOLD,
                 iou_threshold: float = DEFAULT_IOU_THRESHOLD) -> dict:
    """
    Runs YOLO inference on image bytes, returning only egg tray detections.
    
    - Ignores all non-tray classes (eggs, background, etc.)
    - Applies NMS (performed internally by YOLO) to prevent double-counting
    - Labels each detected tray uniquely: TRAY 1, TRAY 2, ...
    - Returns annotated image as base64 JPEG string
    
    Returns:
        {
            "success": True,
            "tray_count": <int>,
            "confidence": <float>,     # average confidence across all detections
            "detections": [
                {"id": 1, "class": "egg_tray", "confidence": 0.96, "bbox": [x1, y1, x2, y2]},
                ...
            ],
            "result_image": "<base64 encoded annotated JPEG>"
        }
    """
    model_instance = load_model()
    if not model_instance:
        raise ValueError("Failed to load YOLO model.")

    # ─── Decode image ─────────────────────────────────────────────────────────
    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not decode image bytes.")

    # ─── Run inference ────────────────────────────────────────────────────────
    # imgsz=640 is faster and usually sufficient for object detection
    results = model_instance(image, conf=conf_threshold, iou=iou_threshold, imgsz=640)

    annotated_image = image.copy()
    detections = []
    tray_count = 0
    conf_sum = 0.0

    for result in results:
        class_names = getattr(result, "names", {0: "egg_tray"})
        for box in result.boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            conf = float(box.conf[0].cpu().numpy())
            cls_id = int(box.cls[0].cpu().numpy())

            # ── Accept only tray-related classes; skip everything else ──────────
            raw_class = class_names.get(cls_id, "unknown").lower()
            if "tray" not in raw_class and "egg_tray" not in raw_class and cls_id != 0:
                # If using a single-class custom model (class 0 = egg_tray), always accept class 0
                continue

            tray_count += 1
            conf_sum += conf

            xi, yi = int(x1), int(y1)
            w, h = int(x2 - x1), int(y2 - y1)

            detections.append({
                "id": tray_count,
                "class": "egg_tray",
                "confidence": round(conf, 3),
                "bbox": [xi, yi, xi + w, yi + h]
            })

            # ── Draw bounding box ────────────────────────────────────────────
            color = (50, 140, 255)  # Blue-orange
            thickness = max(2, int(image.shape[0] * 0.003))
            cv2.rectangle(annotated_image, (xi, yi), (xi + w, yi + h), color, thickness)

            # ── Draw label: TRAY N ─────────────────────────────────────────
            label = f"TRAY {tray_count}"
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = max(0.6, image.shape[0] * 0.0006)
            font_thickness = max(1, int(image.shape[0] * 0.001))
            (tw, th), baseline = cv2.getTextSize(label, font, font_scale, font_thickness)
            # Background rectangle for label
            cv2.rectangle(annotated_image, (xi, yi - th - baseline - 4), (xi + tw + 4, yi), color, -1)
            cv2.putText(annotated_image, label, (xi + 2, yi - baseline - 2),
                        font, font_scale, (255, 255, 255), font_thickness)

    # ─── Encode annotated image ───────────────────────────────────────────────
    _, buffer = cv2.imencode('.jpg', annotated_image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    encoded_img = base64.b64encode(buffer).decode('utf-8')

    avg_confidence = (conf_sum / max(1, tray_count)) if tray_count > 0 else 0.0

    return {
        "success": True,
        "tray_count": tray_count,
        "confidence": round(avg_confidence, 3),
        "detections": detections,
        "result_image": encoded_img
    }


# ─── Backward compatibility alias ─────────────────────────────────────────────
def detect_eggs(image_path: str, conf_threshold: float = DEFAULT_CONF_THRESHOLD):
    """
    Legacy entry point kept for backward compatibility.
    Reads a file path, converts to bytes, calls detect_trays().
    """
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    return detect_trays(image_bytes, conf_threshold=conf_threshold)
