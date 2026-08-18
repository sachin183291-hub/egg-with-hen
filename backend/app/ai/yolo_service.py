import os
import cv2
import numpy as np
import base64
# pyrefly: ignore [missing-import]
from ultralytics import YOLO, YOLOWorld

# Global model instances
model = None
tray_model = None
MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "egg_detector.pt")
ALT_MODEL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../models/best.pt"))
FALLBACK_MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "yolov8s-world.pt")

def load_model():
    global model
    global tray_model
    if model is None:
        try:
            if os.path.exists(MODEL_PATH):
                print(f"Loading custom model from {MODEL_PATH}")
                model = YOLO(MODEL_PATH)
            elif os.path.exists(ALT_MODEL_PATH):
                print(f"Loading custom model from {ALT_MODEL_PATH}")
                model = YOLO(ALT_MODEL_PATH)
            else:
                print(f"Custom model not found. Using zero-shot YOLO-World to detect 'egg tray' and 'hen'.")
                model = YOLOWorld(FALLBACK_MODEL_PATH if os.path.exists(FALLBACK_MODEL_PATH) else "yolov8s-world.pt") 
                model.set_classes(["egg tray", "hen"])
                return model, None
                
            # Check if custom model has tray class
            has_tray = any("tray" in name.lower() for name in model.names.values())
            if not has_tray:
                print("Custom model lacks 'tray' class. Loading YOLO-World for trays and hens.")
                tray_model = YOLOWorld(FALLBACK_MODEL_PATH if os.path.exists(FALLBACK_MODEL_PATH) else "yolov8s-world.pt")
                tray_model.set_classes(["egg tray", "hen"])
                
        except Exception as e:
            print(f"Error loading model: {e}")
            raise e
    return model, tray_model

def detect_objects(image_bytes: bytes, conf_threshold: float = 0.35, iou_threshold: float = 0.45) -> dict:
    """
    Runs YOLO inference on the image bytes and returns detection results for eggs and trays,
    and a base64 annotated image.
    """
    model_instance, tray_model_instance = load_model()
    if not model_instance:
        raise ValueError("Failed to load YOLO model.")

    # Decode image from bytes
    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if image is None:
        raise ValueError("Could not decode image bytes.")

    # Run inference for main model
    results = model_instance(image, conf=conf_threshold, iou=iou_threshold, imgsz=640)
    
    # Run inference for trays if needed
    tray_results = None
    if tray_model_instance:
        tray_results = tray_model_instance(image, conf=conf_threshold, iou=iou_threshold, imgsz=640)
        
    detections = []
    annotated_image = image.copy()
    
    egg_count = 0
    tray_count = 0
    hen_count = 0
    egg_conf_sum = 0
    tray_conf_sum = 0
    
    def process_boxes(boxes, class_names, is_tray_only=False):
        nonlocal egg_count, tray_count, hen_count, egg_conf_sum, tray_conf_sum, detections, annotated_image
        for box in boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            conf = float(box.conf[0].cpu().numpy())
            cls_id = int(box.cls[0].cpu().numpy())
            
            raw_class_name = class_names.get(cls_id, "unknown").lower()
            if is_tray_only or "tray" in raw_class_name:
                class_name = "egg_tray"
            elif "hen" in raw_class_name:
                class_name = "hen"
            elif "egg" in raw_class_name:
                class_name = "egg"
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
                label = f"HEN {hen_count}"
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
        class_names = getattr(result, "names", {0: "egg", 1: "egg_tray"})
        process_boxes(result.boxes, class_names)
        
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
        "result_image": encoded_img
    }
