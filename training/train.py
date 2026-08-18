import argparse
import os
# pyrefly: ignore [missing-import]
from ultralytics import YOLO 

def main():
    parser = argparse.ArgumentParser(description="Train custom YOLO model for Egg and Tray Detection.")
    parser.add_argument("--data", type=str, default="dataset.yaml", help="Path to dataset.yaml")
    parser.add_argument("--epochs", type=int, default=50, help="Number of training epochs")
    parser.add_argument("--imgsz", type=int, default=640, help="Image size for training")
    parser.add_argument("--batch", type=int, default=16, help="Batch size")
    parser.add_argument("--model", type=str, default="yolov8s.pt", help="Base model to transfer learn from")
    parser.add_argument("--device", type=str, default="", help="Device to run on, i.e. cuda device=0 or device=cpu")
    
    args = parser.parse_args()

    # Make sure dataset file exists
    if not os.path.exists(args.data):
        print(f"Error: Dataset configuration file not found at {args.data}")
        return

    # Initialize YOLO model (we use transfer learning from the base pre-trained model)
    print(f"Loading base model: {args.model}")
    model = YOLO(args.model)

    print("Starting training...")
    # Train the model
    results = model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device if args.device else None,
        name="egg_tray_detection",
        exist_ok=True # Overwrite existing project/name folder if it exists
    )

    print(f"Training completed. Best model saved to: {results.save_dir}/weights/best.pt")
    print("You can now copy this best.pt model to your backend/models/ directory for the API to use.")

if __name__ == "__main__":
    main()
