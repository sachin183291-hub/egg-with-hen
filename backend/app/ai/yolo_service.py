import os
import cv2
import numpy as np
import base64
# pyrefly: ignore [missing-import]
from ultralytics import YOLO

# Global model instances
model = None
egg_model = None
tray_model = None

MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "egg_detector.pt")
ALT_MODEL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../models/best.pt"))
FALLBACK_MODEL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../yolov8s-world.pt"))

def load_model():
    global model, egg_model, tray_model
    if model is None:
        try:
            from app.ai.shared_model import get_shared_model
            model = get_shared_model()

            # In cloud environments (Render, Heroku, or constrained RAM), use the single shared YOLO model
            is_cloud = bool(os.environ.get("RENDER") or os.environ.get("PORT"))
            if is_cloud:
                print("[AI] Cloud environment detected. Using single shared YOLO model under 512MB RAM.")
                egg_model = None
                tray_model = None
            else:
                # Dedicated Egg Detection Model on local machines if desired
                egg_candidate_paths = [
                    MODEL_PATH,
                    os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../egg-detection-system/backend/models/egg_detector.pt")),
                ]
                egg_chosen = next((p for p in egg_candidate_paths if os.path.exists(p)), None)
                if egg_chosen:
                    try:
                        print(f"[AI] Loading dedicated egg detector from {egg_chosen}")
                        egg_model = YOLO(egg_chosen)
                    except Exception as egg_err:
                        print(f"[AI] Notice: Could not load egg detector: {egg_err}")
                        egg_model = None

            # YOLOWorld fallback is disabled by default to prevent allocating >1GB of CLIP transformer RAM
            if os.environ.get("ENABLE_YOLO_WORLD", "false").lower() == "true":
                try:
                    from ultralytics import YOLOWorld
                    print("[AI] Loading YOLO-World for trays and hens.")
                    tray_model_path = FALLBACK_MODEL_PATH if os.path.exists(FALLBACK_MODEL_PATH) else "yolov8s-worldv2.pt"
                    if os.path.exists(tray_model_path):
                        tray_model = YOLOWorld(tray_model_path)
                        tray_model.set_classes(["egg tray", "hen"])
                except Exception as e:
                    print(f"[AI] YOLOWorld load notice: {e}")
                    tray_model = None

        except Exception as e:
            print(f"[AI] Error loading model: {e}")
            raise e

    return model, tray_model

def detect_objects_image(image: np.ndarray, conf_threshold: float = 0.35, iou_threshold: float = 0.45) -> dict:
    """
    Runs YOLO inference on a raw OpenCV image array and returns detection results.
    """
    model_instance, tray_model_instance = load_model()
    if not model_instance:
        raise ValueError("Failed to load YOLO model.")

    if image is None:
        raise ValueError("Image array is None.")

    # Run inference for main model
    results = model_instance(image, conf=conf_threshold, iou=iou_threshold, imgsz=640)
    
    # Run inference for eggs if dedicated egg model is available
    egg_results = None
    if egg_model is not None:
        try:
            egg_results = egg_model(image, conf=conf_threshold, iou=iou_threshold, imgsz=640)
        except Exception:
            egg_results = None

    # Run inference for trays if needed
    tray_results = None
    if tray_model_instance:
        try:
            tray_results = tray_model_instance(image, conf=conf_threshold, iou=iou_threshold, imgsz=640)
        except Exception:
            tray_results = None
        
    detections = []
    annotated_image = image.copy()
    
    egg_count = 0
    tray_count = 0
    hen_count = 0
    egg_conf_sum = 0
    tray_conf_sum = 0
    
    def process_boxes(boxes, class_names, is_tray_only=False, is_egg_only=False):
        nonlocal egg_count, tray_count, hen_count, egg_conf_sum, tray_conf_sum, detections, annotated_image
        for box in boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            conf = float(box.conf[0].cpu().numpy())
            cls_id = int(box.cls[0].cpu().numpy())
            
            raw_class_name = class_names.get(cls_id, "unknown").lower()
            if is_egg_only or "egg" in raw_class_name:
                class_name = "egg"
            elif is_tray_only or "tray" in raw_class_name:
                class_name = "egg_tray"
            elif any(k in raw_class_name for k in ("hen", "comb", "bird", "chicken")):
                class_name = "hen"
            else:
                continue  # Skip everything else

            x = int(x1)
            y = int(y1)
            width = int(x2 - x1)
            height = int(y2 - y1)
            
            if class_name == "egg_tray":
                tray_count += 1
                color = (255, 0, 0) # Blue in BGR
                label = f"TRAY {tray_count}"
                tray_conf_sum += conf
                det_id = tray_count
            elif class_name == "hen":
                hen_count += 1
                color = (0, 0, 255) # Red in BGR
                label = f"HEN/COMB {hen_count}"
                det_id = hen_count
            elif class_name == "egg":
                egg_count += 1
                color = (0, 255, 255) # Yellow in BGR
                label = f"EGG {egg_count}"
                egg_conf_sum += conf
                det_id = egg_count
            else:
                continue
            
            detections.append({
                "id": det_id,
                "class": class_name,
                "confidence": round(conf, 3),
                "bbox": [x, y, x + width, y + height]
            })
            
            thickness = max(2, int(image.shape[0] * 0.002))
            cv2.rectangle(annotated_image, (x, y), (x + width, y + height), color, thickness)
            
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = max(0.5, image.shape[0] * 0.0005)
            font_thickness = max(1, int(image.shape[0] * 0.001))
            text_size = cv2.getTextSize(label, font, font_scale, font_thickness)[0]
            cv2.rectangle(annotated_image, (x, y - text_size[1] - 5), (x + text_size[0], y), color, -1)
            cv2.putText(annotated_image, label, (x, y - 5), font, font_scale, (255, 255, 255), font_thickness)

    # Process main model results
    for result in results:
        class_names = getattr(result, "names", {0: "HEN_COMB"})
        process_boxes(result.boxes, class_names)

    # Process dedicated egg model results if present
    if egg_results:
        for result in egg_results:
            class_names = getattr(result, "names", {0: "egg"})
            process_boxes(result.boxes, class_names, is_egg_only=True)
        
    # Process tray model results if present
    if tray_results:
        for result in tray_results:
            class_names = getattr(result, "names", {0: "egg tray", 1: "hen"})
            process_boxes(result.boxes, class_names, is_tray_only=True)

    _, buffer = cv2.imencode('.jpg', annotated_image)
    encoded_img = base64.b64encode(buffer).decode('utf-8')
    
    avg_tray_conf = (tray_conf_sum / max(1, tray_count)) if tray_count > 0 else 0.0
    avg_egg_conf = (egg_conf_sum / max(1, egg_count)) if egg_count > 0 else 0.0
    
    # Use tray confidence by default, fallback to egg if it's the only thing detected
    final_conf = avg_tray_conf if tray_count > 0 else avg_egg_conf
    
    return {
        "success": True,
        "tray_count": tray_count,
        "hen_count": hen_count,
        "egg_count": egg_count,
        "confidence": round(final_conf, 3),
        "detections": detections,
        "result_image": encoded_img,
        "annotated_frame": annotated_image # useful for live stream drawing
    }

def detect_objects(image_bytes: bytes, conf_threshold: float = 0.35, iou_threshold: float = 0.45) -> dict:
    """
    Runs YOLO inference on the image bytes and returns detection results for eggs and trays,
    and a base64 annotated image.
    """
    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not decode image bytes.")
        
    return detect_objects_image(image, conf_threshold, iou_threshold)
