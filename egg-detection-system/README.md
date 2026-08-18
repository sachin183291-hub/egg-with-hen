# AI Egg Tray Detection & Counting System

A full-stack web application for automatically **counting physical egg trays** in uploaded photographs using a YOLO object detection model.

## What It Counts

**ONLY EGG TRAYS** — not eggs, not cavities, not holes, not background.

- ✅ Green plastic trays
- ✅ Brown cardboard/paper trays  
- ✅ Grey paper trays
- ✅ Stacked trays (each layer counted separately)
- ✅ Partially visible trays
- ✅ Different lighting and camera angles
- ❌ Individual eggs (ignored completely)
- ❌ Egg holes or cavities (ignored completely)

## Counting Rule

**One physical tray = one count.**

```
Stack of 5 trays → Total Egg Trays: 5
Stack of 25 trays → Total Egg Trays: 25
```

## Features

- **Frontend**: React, TypeScript, Vite. Smartphone camera upload or gallery selection.
- **Backend**: FastAPI (Python), Ultralytics YOLOv8s.
- **Tray-Only Detection**: Ignores eggs entirely. Only counts physical tray boundaries.
- **Duplicate Prevention**: NMS + IoU threshold prevents double-counting the same tray.
- **Training Support**: `train.py` trains a custom YOLOv8s model on your annotated tray dataset.
- **Active Learning**: Each upload is saved to the training dataset automatically for continuous improvement.

## API

```
POST /api/ai/count-trays
```

**Input**: multipart/form-data with `image` or `file` field + optional `confidence_threshold` (default 0.40)

**Output**:
```json
{
  "success": true,
  "tray_count": 25,
  "confidence": 0.948,
  "detections": [
    {"id": 1, "class": "egg_tray", "confidence": 0.96, "bbox": [x1, y1, x2, y2]},
    {"id": 2, "class": "egg_tray", "confidence": 0.94, "bbox": [x1, y1, x2, y2]}
  ],
  "result_image": "<base64 annotated JPEG>"
}
```

## Setup Instructions

### Backend Setup

1. Navigate to the `backend` directory.
2. Create a virtual environment (recommended):
   ```bash
   python -m venv venv
   ```
3. Activate the virtual environment:
   - Windows: `venv\Scripts\activate`
   - Linux/Mac: `source venv/bin/activate`
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
5. Run the server:
   ```bash
   python app/main.py
   ```
   The backend will be available at `http://localhost:8000`

## Training a Custom Tray Model

### 1. Prepare Dataset

Collect real photographs of egg trays. Annotate **each physical tray** with a separate bounding box using a tool like [LabelImg](https://github.com/heartexlabs/labelImg) or [Roboflow](https://roboflow.com/).

**Annotation rules:**
- One bounding box per physical tray layer
- Class: `egg_tray` (class ID: 0)
- Do NOT annotate eggs, holes, or background

Place annotated data in:
```
dataset/
├── images/
│   ├── train/   ← training images (.jpg / .png)
│   └── val/     ← validation images
└── labels/
    ├── train/   ← YOLO format .txt label files
    └── val/
```

### 2. Update `data.yaml`

```yaml
path: /absolute/path/to/dataset
train: images/train
val: images/val

names:
  0: egg_tray
```

### 3. Train

```bash
cd backend
python train.py
```

Training will:
- Use YOLOv8s with high-resolution (1280px) inference
- Apply augmentation tuned for stacked trays (colour shifts, rotation, perspective)
- Save best weights to `models/egg_tray_best.pt`

### 4. Verify Model

After training, the model is automatically picked up by the application. Upload a test photo via the web interface and verify:
- Each tray is labelled `TRAY 1`, `TRAY 2`, etc.
- Total count matches the actual physical tray count

## Model Path Configuration

The application looks for the model in this order:
1. `models/egg_tray_best.pt` — trained custom model (preferred)
2. `models/egg_detector.pt` — legacy name
3. YOLO-World zero-shot fallback (no training required, lower accuracy)
