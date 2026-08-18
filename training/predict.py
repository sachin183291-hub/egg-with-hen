import argparse
import os
import cv2
# pyrefly: ignore [missing-import]
from ultralytics import YOLO 

def main():
    parser = argparse.ArgumentParser(description="Run inference with trained YOLO model.")
    parser.add_argument("--weights", type=str, default="runs/detect/egg_tray_detection/weights/best.pt", help="Path to trained model weights")
    parser.add_argument("--source", type=str, required=True, help="Path to image or directory to run inference on")
    parser.add_argument("--conf", type=float, default=0.35, help="Confidence threshold")
    parser.add_argument("--iou", type=float, default=0.45, help="NMS IoU threshold")
    
    args = parser.parse_args()

    if not os.path.exists(args.weights):
        print(f"Error: Model weights not found at {args.weights}.")
        return
        
    if not os.path.exists(args.source):
        print(f"Error: Source image/directory not found at {args.source}.")
        return

    print(f"Loading model: {args.weights}")
    model = YOLO(args.weights)

    print(f"Running inference on: {args.source}")
    results = model.predict(
        source=args.source,
        conf=args.conf,
        iou=args.iou,
        save=True, # Save images with drawn bounding boxes
        imgsz=1280 # Use large size for small egg detection
    )

    for result in results:
        boxes = result.boxes
        print(f"\nImage: {result.path}")
        
        egg_count = 0
        tray_count = 0
        
        for box in boxes:
            cls_id = int(box.cls[0].cpu().numpy())
            class_name = result.names[cls_id]
            conf = float(box.conf[0].cpu().numpy())
            
            if "egg" in class_name and "tray" not in class_name:
                egg_count += 1
            elif "tray" in class_name:
                tray_count += 1
                
        print(f"Total Eggs Detected: {egg_count}")
        print(f"Total Trays Detected: {tray_count}")
        print(f"Saved annotated image to: {result.save_dir}")

if __name__ == "__main__":
    main()
