import argparse
import os
# pyrefly: ignore [missing-import]
from ultralytics import YOLO

def main():
    parser = argparse.ArgumentParser(description="Validate a trained YOLO model on the validation dataset.")
    parser.add_argument("--weights", type=str, default="runs/detect/egg_tray_detection/weights/best.pt", help="Path to trained model weights")
    parser.add_argument("--data", type=str, default="dataset.yaml", help="Path to dataset.yaml")
    parser.add_argument("--imgsz", type=int, default=640, help="Image size for validation")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold")
    parser.add_argument("--iou", type=float, default=0.45, help="NMS IoU threshold")
    
    args = parser.parse_args()

    if not os.path.exists(args.weights):
        print(f"Error: Model weights not found at {args.weights}. Did you train the model first?")
        return

    print(f"Loading model: {args.weights}")
    model = YOLO(args.weights)

    print("Running validation...")
    metrics = model.val(
        data=args.data,
        imgsz=args.imgsz,
        conf=args.conf,
        iou=args.iou,
        save_json=True # Save results to JSON
    )

    print("Validation completed.")
    print("Metrics:")
    print(f"mAP50-95: {metrics.box.map}") 
    print(f"mAP50: {metrics.box.map50}") 
    print(f"Precision: {metrics.box.p.mean()}")
    print(f"Recall: {metrics.box.r.mean()}")

if __name__ == "__main__":
    main()
