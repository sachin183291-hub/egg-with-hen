# pyrefly: ignore [missing-import]
from ultralytics import YOLO 

def main():
    # Load a pre-trained YOLOv8 nano model (fast and lightweight)
    model = YOLO("yolov8n.pt") 

    # Train the model
    # Note: Make sure the path to your data.yaml is correct based on where you extracted the dataset.
    print("Starting training...")
    results = model.train(
        data="egg_dataset/data.yaml",  # Path to the dataset config file
        epochs=50,                     # Number of training iterations (50 is a good start)
        imgsz=640,                     # Image size
        batch=16,                      # Batch size 
        name="egg_counter_model"       # Name of the folder where results will be saved
    )
    print("Training complete! Your model is saved in runs/detect/egg_counter_model/weights/best.pt")

if __name__ == "__main__":
    main()
