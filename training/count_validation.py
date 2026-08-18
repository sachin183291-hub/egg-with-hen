import os
import glob
import argparse
# pyrefly: ignore [missing-import]
from ultralytics import YOLO

def get_ground_truth_counts(label_path):
    """Parses a YOLO format label file and returns egg and tray counts."""
    egg_count = 0
    tray_count = 0
    if os.path.exists(label_path):
        with open(label_path, 'r') as f:
            for line in f:
                class_id = int(line.strip().split()[0])
                if class_id == 0:
                    egg_count += 1
                elif class_id == 1:
                    tray_count += 1
    return egg_count, tray_count

def count_validation(model_path, images_dir, labels_dir, imgsz=1280, conf=0.35, iou=0.45):
    """
    Evaluates the model by comparing the actual count vs predicted count per image,
    and computes the Mean Absolute Error for Egg and Tray counting.
    """
    print(f"Loading model from {model_path}...")
    try:
        model = YOLO(model_path)
    except Exception as e:
        print(f"Failed to load model: {e}")
        return

    image_paths = glob.glob(os.path.join(images_dir, "*.jpg")) + \
                  glob.glob(os.path.join(images_dir, "*.png"))
                  
    if not image_paths:
        print(f"No images found in {images_dir}")
        return
        
    print(f"Found {len(image_paths)} images for count validation.")
    
    total_egg_error = 0
    total_tray_error = 0
    total_gt_eggs = 0
    total_gt_trays = 0
    
    for img_path in image_paths:
        base_name = os.path.splitext(os.path.basename(img_path))[0]
        label_path = os.path.join(labels_dir, f"{base_name}.txt")
        
        gt_eggs, gt_trays = get_ground_truth_counts(label_path)
        total_gt_eggs += gt_eggs
        total_gt_trays += gt_trays
        
        # Run prediction
        results = model(img_path, conf=conf, iou=iou, imgsz=imgsz, verbose=False)
        pred_eggs = 0
        pred_trays = 0
        
        for result in results:
            boxes = result.boxes
            for cls_tensor in boxes.cls:
                cls_id = int(cls_tensor.cpu().numpy())
                # Adjust if class IDs differ
                if cls_id == 0:
                    pred_eggs += 1
                elif cls_id == 1:
                    pred_trays += 1
                    
        egg_err = abs(gt_eggs - pred_eggs)
        tray_err = abs(gt_trays - pred_trays)
        
        total_egg_error += egg_err
        total_tray_error += tray_err
        
        # Uncomment below to print per-image stats
        # print(f"Image: {base_name}")
        # print(f"  Eggs  - GT: {gt_eggs}, Pred: {pred_eggs}, Error: {egg_err}")
        # print(f"  Trays - GT: {gt_trays}, Pred: {pred_trays}, Error: {tray_err}")

    n = len(image_paths)
    mae_eggs = total_egg_error / n
    mae_trays = total_tray_error / n
    
    pct_err_eggs = (total_egg_error / total_gt_eggs * 100) if total_gt_eggs > 0 else 0
    pct_err_trays = (total_tray_error / total_gt_trays * 100) if total_gt_trays > 0 else 0
    
    print("\n--- Count Validation Results ---")
    print(f"Total Images Analyzed: {n}")
    print(f"Total Ground Truth - Eggs: {total_gt_eggs}, Trays: {total_gt_trays}")
    print("\nEgg Counting:")
    print(f"  Mean Absolute Error (MAE): {mae_eggs:.2f} eggs per image")
    print(f"  Percentage Count Error:    {pct_err_eggs:.2f}%")
    print("\nTray Counting:")
    print(f"  Mean Absolute Error (MAE): {mae_trays:.2f} trays per image")
    print(f"  Percentage Count Error:    {pct_err_trays:.2f}%")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Count Accuracy for Egg and Tray Detection.")
    parser.add_argument("--model", type=str, default="runs/detect/egg_tray_model/weights/best.pt", help="Path to best.pt")
    parser.add_argument("--images", type=str, default="../dataset/images/val", help="Path to validation images dir")
    parser.add_argument("--labels", type=str, default="../dataset/labels/val", help="Path to validation labels dir")
    parser.add_argument("--conf", type=float, default=0.35, help="Confidence threshold")
    parser.add_argument("--iou", type=float, default=0.45, help="IoU threshold")
    
    args = parser.parse_args()
    
    count_validation(args.model, args.images, args.labels, conf=args.conf, iou=args.iou)
