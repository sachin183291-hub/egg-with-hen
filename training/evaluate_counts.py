import argparse
import os
import glob
# pyrefly: ignore [missing-import]
from ultralytics import YOLO

def main():
    parser = argparse.ArgumentParser(description="Evaluate predicted counts against ground truth labels.")
    parser.add_argument("--weights", type=str, default="runs/detect/egg_tray_detection/weights/best.pt", help="Path to trained model")
    parser.add_argument("--images", type=str, default="../dataset/images/val", help="Path to validation images")
    parser.add_argument("--labels", type=str, default="../dataset/labels/val", help="Path to validation labels")
    parser.add_argument("--conf", type=float, default=0.35, help="Confidence threshold")
    
    args = parser.parse_args()

    if not os.path.exists(args.weights) or not os.path.exists(args.images) or not os.path.exists(args.labels):
        print("Error: Weights, images, or labels path not found.")
        return

    model = YOLO(args.weights)
    image_files = glob.glob(os.path.join(args.images, "*.jpg")) + glob.glob(os.path.join(args.images, "*.png"))
    
    total_egg_error = 0
    total_tray_error = 0
    total_gt_eggs = 0
    total_gt_trays = 0
    
    print(f"Evaluating counts on {len(image_files)} images...")
    
    for img_path in image_files:
        basename = os.path.basename(img_path)
        name, _ = os.path.splitext(basename)
        label_path = os.path.join(args.labels, f"{name}.txt")
        
        gt_eggs = 0
        gt_trays = 0
        
        # Read Ground Truth
        if os.path.exists(label_path):
            with open(label_path, "r") as f:
                lines = f.readlines()
                for line in lines:
                    cls_id = int(line.strip().split()[0])
                    if cls_id == 0: gt_eggs += 1
                    elif cls_id == 1: gt_trays += 1
        
        # Predict
        results = model.predict(source=img_path, conf=args.conf, verbose=False)
        pred_eggs = 0
        pred_trays = 0
        
        for result in results:
            boxes = result.boxes
            for box in boxes:
                cls_id = int(box.cls[0].item())
                class_name = result.names[cls_id]
                if "egg" in class_name and "tray" not in class_name: pred_eggs += 1
                elif "tray" in class_name: pred_trays += 1
                
        # Calculate Errors
        egg_error = abs(gt_eggs - pred_eggs)
        tray_error = abs(gt_trays - pred_trays)
        
        total_egg_error += egg_error
        total_tray_error += tray_error
        total_gt_eggs += gt_eggs
        total_gt_trays += gt_trays
        
        print(f"[{basename}] GT Eggs: {gt_eggs}, Pred Eggs: {pred_eggs} | GT Trays: {gt_trays}, Pred Trays: {pred_trays}")
        
    # Final Metrics
    if len(image_files) > 0:
        mae_eggs = total_egg_error / len(image_files)
        mae_trays = total_tray_error / len(image_files)
        
        egg_pct_error = (total_egg_error / total_gt_eggs * 100) if total_gt_eggs > 0 else 0
        tray_pct_error = (total_tray_error / total_gt_trays * 100) if total_gt_trays > 0 else 0
        
        print("\n--- Final Evaluation Metrics ---")
        print(f"Total Images Evaluated: {len(image_files)}")
        print(f"Mean Absolute Error (Eggs): {mae_eggs:.2f}")
        print(f"Mean Absolute Error (Trays): {mae_trays:.2f}")
        print(f"Percentage Count Error (Eggs): {egg_pct_error:.2f}%")
        print(f"Percentage Count Error (Trays): {tray_pct_error:.2f}%")

if __name__ == "__main__":
    main()
