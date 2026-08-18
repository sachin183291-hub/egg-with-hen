# AI Egg & Tray Detection Pipeline

This project implements a complete computer vision ML pipeline to accurately detect and count eggs and egg trays from user-uploaded images (e.g., from mobile phones). It seamlessly integrates with the existing React frontend and FastAPI backend without replacing existing working components.

## 1. Complete Source Code & Architecture

The system uses a modern **YOLO object detection** model (Ultralytics YOLOv8) specifically optimized for accurate counting without duplicates.

**Key Files Integrated into Existing Project:**
- **Frontend Integration:** `frontend/src/pages/EggCounterPage.tsx` (Handles camera capture, file uploads, threshold adjustments, and rendering bounding boxes/counts).
- **Inference API:** `backend/app/api/ai.py` (Exposes `POST /api/detect`).
- **Detection Service:** `backend/app/ai/yolo_service.py` (Runs the YOLO model, parses bounding boxes, counts unique objects, and draws bounding boxes using OpenCV).
- **Training Scripts:** `training/train.py`, `training/validate.py`, `training/count_validation.py`
- **Dataset Configuration:** `dataset/dataset.yaml`

## 2. Requirements & Setup (requirements.txt)

The backend relies on the following key dependencies which are included in `backend/requirements.txt`:
```text
ultralytics         # YOLO framework for detection and training
opencv-python-headless # Image processing and bounding box drawing
numpy               # Array manipulation
python-multipart    # Uploading form data from frontend
```

### Environment Setup Instructions
1. Navigate to the backend directory: `cd backend`
2. Ensure your virtual environment is activated: `.\.venv\Scripts\activate` (Windows) or `source .venv/bin/activate` (Mac/Linux).
3. Install dependencies: `pip install -r requirements.txt`
4. The system requires standard system libraries for OpenCV.

## 3. Local Testing Instructions

1. **Start Backend:** `cd backend && python -m uvicorn app.main:app --reload`
2. **Start Frontend:** `cd frontend && npm run dev`
3. Open your browser and navigate to the Egg Counter page in the UI (or go directly to the upload route).
4. **Test the Pipeline:** Upload an image containing eggs and trays. The backend will process the image using YOLO and return the `egg_count`, `tray_count`, and a base64 string of the image with bounding boxes drawn.

*Note: Out-of-the-box, if a custom trained model (`models/best.pt`) is not found, the backend will gracefully fallback to a pre-trained **YOLO-World** model performing zero-shot detection on the classes "egg" and "egg tray" to guarantee real object detection from day one.*

## 4. Dataset Structure

To train your own custom model for absolute accuracy across different lighting and tray types, structure your dataset as follows:

```text
dataset/
    ├── dataset.yaml
    ├── images/
    │   ├── train/     # 80% of images (JPEG/PNG)
    │   ├── val/       # 20% of images
    │   └── test/      # (Optional)
    └── labels/
        ├── train/     # YOLO format txt files
        ├── val/
        └── test/
```

### `dataset.yaml`
```yaml
path: .  # Root of the dataset
train: images/train 
val: images/val      

names:
  0: egg
  1: egg_tray
  # Optional: expand later
  # 2: paper_tray
  # 3: plastic_tray
  # 4: colored_tray
```

## 5. Instructions for Collecting & Labeling Data

1. **Collection:** Take photos of eggs and trays using normal smartphones. Ensure varied environments:
   - Different colored trays (white, brown, blue, plastic, paper).
   - Different lighting (indoor, outdoor, shadows).
   - Angles and overlap (partial occlusion).
   - Large quantities (100+ eggs).
2. **Labeling:** Use a tool like **Roboflow** or **CVAT**.
   - Draw tight bounding boxes around every single visible egg.
   - Draw tight bounding boxes around the entire perimeter of every visible tray.
   - Do NOT group eggs into one box. 1 Box = 1 Count.
3. **Export:** Export the dataset in **YOLOv8 format** and place the `images` and `labels` folders into your `dataset/` directory.

## 6. Model Training & Retraining

When you have collected your dataset or added new tray colors/types, you need to train/retrain the model.

1. Navigate to the `training/` folder.
2. Run the training script:
   ```bash
   python train.py
   ```
3. The script automatically handles:
   - Loading your `dataset.yaml`.
   - Training for a configurable number of epochs.
   - GPU utilization (if CUDA is available).
4. After training, the script will output the best weights to `runs/detect/train/weights/best.pt`.
5. **Deployment:** Copy `best.pt` to `backend/models/best.pt`. The backend API (`yolo_service.py`) is already configured to prioritize this file.

## 7. Model Evaluation & Count Validation

Do not judge the model strictly on standard classification accuracy. Because this is a counting task, use the custom validation script to evaluate actual counting error margins.

1. Run standard validation (mAP, Precision, Recall):
   ```bash
   python validate.py
   ```
2. Run Count Validation (MAE, Percentage Error on total object counts):
   ```bash
   python count_validation.py
   ```
   *This script compares ground truth counts to predicted counts to ensure the system is not double-counting due to overlapping bounding boxes.*

## 8. API Specifications

**POST `/api/ai/detect`**
- **Input (multipart/form-data):**
  - `file`: The image file.
  - `confidence_threshold`: Float (default 0.35). Filters low-confidence detections.
  - `iou_threshold`: Float (default 0.45). Filters duplicate bounding boxes via NMS.
- **Output (JSON):**
  ```json
  {
      "success": true,
      "egg_count": 120,
      "tray_count": 12,
      "egg_confidence": 0.962,
      "tray_confidence": 0.947,
      "detections": [
          {"class": "egg", "confidence": 0.97, "bbox": [10, 20, 40, 50]},
          {"class": "egg_tray", "confidence": 0.94, "bbox": [5, 5, 200, 300]}
      ],
      "result_image": "base64_encoded_jpeg_string..."
  }
  ```

## 9. Production Deployment

1. For production inference on a VPS (e.g., AWS EC2, DigitalOcean), CPU inference is usually sufficient for single-image processing (YOLOv8 nano/small models take ~100-300ms on modern CPUs).
2. Ensure you deploy behind a reverse proxy (Nginx) and configure upload size limits. 
3. The frontend passes the image directly; ensure HTTPS is enabled for camera permissions to work correctly in mobile browsers (`capture="environment"`).
4. If scaling is required, separate the FastAPI inference worker from the main backend using Celery/Redis, though the current synchronous implementation is highly optimized and perfectly suitable for normal traffic.
