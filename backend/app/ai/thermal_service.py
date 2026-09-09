import cv2
import numpy as np
import base64
import os
import tempfile
from typing import Dict, Any, Tuple, List
import math

class CentroidTracker:
    def __init__(self, max_disappeared=10, max_distance=60):
        self.next_object_id = 1
        self.objects = {}  # {id: (centroid_x, centroid_y)}
        self.disappeared = {}  # {id: count}
        self.max_disappeared = max_disappeared
        self.max_distance = max_distance
        self.max_id_seen = 0
        
    def register(self, centroid):
        self.objects[self.next_object_id] = centroid
        self.disappeared[self.next_object_id] = 0
        if self.next_object_id > self.max_id_seen:
            self.max_id_seen = self.next_object_id
        self.next_object_id += 1
        
    def deregister(self, object_id):
        del self.objects[object_id]
        del self.disappeared[object_id]
        
    def update(self, rects):
        if len(rects) == 0:
            for object_id in list(self.disappeared.keys()):
                self.disappeared[object_id] += 1
                if self.disappeared[object_id] > self.max_disappeared:
                    self.deregister(object_id)
            return self.objects
            
        input_centroids = np.zeros((len(rects), 2), dtype="int")
        for (i, (startX, startY, endX, endY)) in enumerate(rects):
            cX = int((startX + endX) / 2.0)
            cY = int((startY + endY) / 2.0)
            input_centroids[i] = (cX, cY)
            
        if len(self.objects) == 0:
            for i in range(0, len(input_centroids)):
                self.register(input_centroids[i])
        else:
            object_ids = list(self.objects.keys())
            object_centroids = list(self.objects.values())
            
            # Compute distance between each pair of object centroids and input centroids
            D = np.zeros((len(object_centroids), len(input_centroids)), dtype="float32")
            for i in range(len(object_centroids)):
                for j in range(len(input_centroids)):
                    dx = object_centroids[i][0] - input_centroids[j][0]
                    dy = object_centroids[i][1] - input_centroids[j][1]
                    D[i, j] = math.sqrt(dx*dx + dy*dy)
                    
            rows = D.min(axis=1).argsort()
            cols = D.argmin(axis=1)[rows]
            
            used_rows = set()
            used_cols = set()
            
            for (row, col) in zip(rows, cols):
                if row in used_rows or col in used_cols:
                    continue
                    
                if D[row, col] > self.max_distance:
                    continue
                    
                object_id = object_ids[row]
                self.objects[object_id] = input_centroids[col]
                self.disappeared[object_id] = 0
                used_rows.add(row)
                used_cols.add(col)
                
            unused_rows = set(range(0, D.shape[0])).difference(used_rows)
            unused_cols = set(range(0, D.shape[1])).difference(used_cols)
            
            for row in unused_rows:
                object_id = object_ids[row]
                self.disappeared[object_id] += 1
                if self.disappeared[object_id] > self.max_disappeared:
                    self.deregister(object_id)
                    
            for col in unused_cols:
                self.register(input_centroids[col])
                
        return self.objects

def detect_thermal_hotspots(image: np.ndarray, min_temp: float = 20.0, max_temp: float = 40.0, tracker: CentroidTracker = None) -> Tuple[np.ndarray, int, List[Dict]]:
    from app.ai.yolo_service import detect_objects_image
    
    h_img, w_img = image.shape[:2]
    annotated = image.copy()
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    
    try:
        yolo_result = detect_objects_image(image)
        detections = yolo_result.get("detections", [])
    except Exception as e:
        print(f"YOLO detection error: {e}")
        detections = []
        
    rects = []
    valid_hens = []
    
    for det in detections:
        # We only care about hens (YOLO may return egg, tray, etc.)
        # Allow 'bird' as well in case the fallback yolov8n model is used
        if det["class"] not in ["hen", "bird"]:
            continue
            
        x, y, x2, y2 = det["bbox"]
        
        # Ensure bounds
        x, y = max(0, x), max(0, y)
        x2, y2 = min(w_img, x2), min(h_img, y2)
        w = x2 - x
        h = y2 - y
        
        if w <= 0 or h <= 0:
            continue
            
        # Get thermal signature from the YOLO box
        blob_hsv = hsv[y:y+h, x:x+w]
        
        mean_hue = cv2.mean(blob_hsv[:, :, 0])[0]
        mean_sat = cv2.mean(blob_hsv[:, :, 1])[0]
        mean_val = cv2.mean(blob_hsv[:, :, 2])[0]
        
        # Same heuristic for temperature
        if mean_sat < 45 and mean_val > 210:
            estimated_temp = 38.5
        elif mean_hue >= 158 or mean_hue <= 5:
            norm = min(1.0, max(0.0, mean_val / 255.0))
            estimated_temp = 36.0 + norm * 4.0
        elif mean_hue <= 28:
            norm = 1.0 - (mean_hue - 5) / 23.0
            estimated_temp = 30.0 + norm * 8.0
        elif mean_hue <= 42:
            norm = 1.0 - (mean_hue - 28) / 14.0
            estimated_temp = 22.0 + norm * 9.0
        else:
            estimated_temp = 21.0
            
        if min_temp <= estimated_temp <= max_temp:
            rects.append((x, y, x2, y2))
            valid_hens.append({
                "temperature": estimated_temp,
                "x": x, "y": y, "w": w, "h": h
            })

    hen_count = len(valid_hens)
    hens_data = []

    if tracker is not None:
        objects = tracker.update(rects)
        current_total = tracker.max_id_seen
        
        # We need to map object IDs back to valid_hens. 
        # Since we just updated the tracker, the centroids of tracker objects should exactly match the centroids of rects.
        for object_id, centroid in objects.items():
            cx, cy = centroid
            # Find which valid_hen it belongs to
            for hen in valid_hens:
                hx, hy, hw, hh = hen["x"], hen["y"], hen["w"], hen["h"]
                hcx = int(hx + hw/2)
                hcy = int(hy + hh/2)
                if abs(cx - hcx) < 2 and abs(cy - hcy) < 2:
                    estimated_temp = hen["temperature"]
                    hens_data.append({
                        "hen_number": object_id,
                        "temperature": round(estimated_temp, 1),
                        "x": hx, "y": hy, "w": hw, "h": hh
                    })
                    
                    # Draw
                    norm_color = min(1.0, max(0.0, (estimated_temp - min_temp) / (max_temp - min_temp)))
                    box_r = int(norm_color * 255)
                    box_g = int((1 - norm_color) * 200)
                    box_color = (0, box_g, box_r)
                    
                    thickness = max(2, int(min(w_img, h_img) * 0.004))
                    cv2.rectangle(annotated, (hx, hy), (hx + hw, hy + hh), box_color, thickness)
                    
                    label = f"ID:{object_id} {estimated_temp:.1f}C"
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    font_scale = max(0.45, min(w_img, h_img) * 0.0012)
                    font_thick = max(1, thickness - 1)
                    (tw, th), _ = cv2.getTextSize(label, font, font_scale, font_thick)
                    
                    lx1 = hx
                    ly1 = max(0, hy - th - 8)
                    lx2 = min(w_img, hx + tw + 6)
                    ly2 = hy
                    cv2.rectangle(annotated, (lx1, ly1), (lx2, ly2), box_color, -1)
                    cv2.putText(annotated, label, (lx1 + 3, ly2 - 4), font, font_scale, (255, 255, 255), font_thick)
                    break
                    
        summary = f"Total Hens: {current_total}"
        hen_count = current_total
    else:
        # Default behavior (no tracker, single image)
        for i, hen in enumerate(valid_hens):
            hen_id = i + 1
            estimated_temp = hen["temperature"]
            hx, hy, hw, hh = hen["x"], hen["y"], hen["w"], hen["h"]
            
            hens_data.append({
                "hen_number": hen_id,
                "temperature": round(estimated_temp, 1),
                "x": hx, "y": hy, "w": hw, "h": hh
            })
            
            norm_color = min(1.0, max(0.0, (estimated_temp - min_temp) / (max_temp - min_temp)))
            box_r = int(norm_color * 255)
            box_g = int((1 - norm_color) * 200)
            box_color = (0, box_g, box_r)
            
            thickness = max(2, int(min(w_img, h_img) * 0.004))
            cv2.rectangle(annotated, (hx, hy), (hx + hw, hy + hh), box_color, thickness)
            
            label = f"Hen #{hen_id} {estimated_temp:.1f}C"
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = max(0.45, min(w_img, h_img) * 0.0012)
            font_thick = max(1, thickness - 1)
            (tw, th), _ = cv2.getTextSize(label, font, font_scale, font_thick)
            
            lx1 = hx
            ly1 = max(0, hy - th - 8)
            lx2 = min(w_img, hx + tw + 6)
            ly2 = hy
            cv2.rectangle(annotated, (lx1, ly1), (lx2, ly2), box_color, -1)
            cv2.putText(annotated, label, (lx1 + 3, ly2 - 4), font, font_scale, (255, 255, 255), font_thick)
            
        summary = f"Total Hens: {hen_count}  ({min_temp:.0f}C-{max_temp:.0f}C)"

    sum_scale = max(0.55, w_img * 0.001)
    (sw, _), _ = cv2.getTextSize(summary, cv2.FONT_HERSHEY_SIMPLEX, sum_scale, 2)
    cv2.rectangle(annotated, (5, 5), (sw + 14, 34), (0, 0, 0), -1)
    cv2.putText(annotated, summary, (9, 28), cv2.FONT_HERSHEY_SIMPLEX, sum_scale, (0, 255, 0), 2)
    
    return annotated, hen_count, hens_data


def process_thermal_image(image_bytes: bytes, min_temp: float = 20.0, max_temp: float = 40.0) -> Dict[str, Any]:
    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not decode image bytes.")
    
    annotated, hen_count, hens_data = detect_thermal_hotspots(image, min_temp, max_temp)
    
    _, buffer = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 92])
    encoded_img = base64.b64encode(buffer).decode('utf-8')
    
    return {
        "success":      True,
        "is_video":     False,
        "hen_count":    hen_count,
        "hens":         hens_data,
        "result_image": encoded_img
    }


def process_thermal_video(video_bytes: bytes, min_temp: float = 20.0, max_temp: float = 40.0) -> Dict[str, Any]:
    temp_dir        = tempfile.gettempdir()
    input_path      = os.path.join(temp_dir, "input_thermal.mp4")
    output_path_mp4 = os.path.join(temp_dir, "output_thermal.mp4")
    output_path_avi = os.path.join(temp_dir, "output_thermal.avi")

    with open(input_path, "wb") as f:
        f.write(video_bytes)

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise ValueError("Could not open video file.")

    fps    = max(cap.get(cv2.CAP_PROP_FPS), 1.0) or 25.0
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Try codecs in order until one works
    out = None
    final_output = output_path_mp4
    for codec_str, out_path in [('mp4v', output_path_mp4), ('MJPG', output_path_avi), ('DIVX', output_path_avi)]:
        fourcc = cv2.VideoWriter_fourcc(*codec_str)
        candidate = cv2.VideoWriter(out_path, fourcc, fps, (width, height))
        if candidate.isOpened():
            out = candidate
            final_output = out_path
            break
        candidate.release()

    if out is None:
        cap.release()
        raise ValueError("Could not open VideoWriter with any available codec.")

    tracker     = CentroidTracker(max_disappeared=15, max_distance=80)
    frame_idx   = 0
    YOLO_EVERY  = 5  # Run YOLO every N frames, track in between for speed

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % YOLO_EVERY == 0:
            annotated_frame, _, _ = detect_thermal_hotspots(frame, min_temp, max_temp, tracker)
        else:
            # Between YOLO frames: draw tracker centroids cheaply
            annotated_frame = frame.copy()
            for obj_id, centroid in tracker.objects.items():
                cx, cy = int(centroid[0]), int(centroid[1])
                cv2.circle(annotated_frame, (cx, cy), 20, (0, 200, 100), 2)
                cv2.putText(annotated_frame, f"ID:{obj_id}", (cx - 20, cy - 28),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # Overlay total count on every frame
        total   = tracker.max_id_seen
        s_scale = max(0.55, width * 0.001)
        summary = f"Hens Detected: {total}"
        (sw, _), _ = cv2.getTextSize(summary, cv2.FONT_HERSHEY_SIMPLEX, s_scale, 2)
        cv2.rectangle(annotated_frame, (5, 5), (sw + 14, 34), (0, 0, 0), -1)
        cv2.putText(annotated_frame, summary, (9, 28), cv2.FONT_HERSHEY_SIMPLEX, s_scale, (0, 255, 0), 2)

        out.write(annotated_frame)
        frame_idx += 1

    total_count = tracker.max_id_seen
    cap.release()
    out.release()

    if os.path.exists(input_path):
        try:
            os.remove(input_path)
        except Exception:
            pass

    # If written as AVI, try to convert to MP4 using ffmpeg for browser playback
    if final_output.endswith('.avi') and os.path.exists(final_output):
        try:
            import subprocess
            converted = output_path_mp4
            res = subprocess.run(
                ["ffmpeg", "-y", "-i", final_output, "-vcodec", "libx264", "-crf", "28", converted],
                capture_output=True, timeout=180
            )
            if res.returncode == 0 and os.path.exists(converted):
                os.remove(final_output)
                final_output = converted
        except Exception as ffmpeg_err:
            print(f"ffmpeg conversion skipped: {ffmpeg_err}")

    return {
        "success":    True,
        "is_video":   True,
        "hen_count":  total_count,
        "video_path": final_output
    }

# Global variable to store latest stream results
LATEST_STREAM_RECORD = {
    "video_path": None,
    "final_count": 0
}

async def generate_thermal_stream(url: str, min_temp: float = 20.0, max_temp: float = 40.0):
    import asyncio
    import os
    from datetime import datetime
    global LATEST_STREAM_RECORD
    
    cap = cv2.VideoCapture(url)
    if not cap.isOpened():
        placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(placeholder, "Connecting to drone stream...", (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,255), 2)
        _, buffer = cv2.imencode('.jpg', placeholder)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        
        await asyncio.sleep(2)
        cap = cv2.VideoCapture(url)
        if not cap.isOpened():
            return
            
    tracker = CentroidTracker(max_disappeared=15, max_distance=80)
    
    # Setup VideoWriter
    os.makedirs('storage', exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_video_path = f"storage/drone_record_{timestamp}.mp4"
    out = None
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                await asyncio.sleep(0.1)
                continue
                
            annotated_frame, _, _ = detect_thermal_hotspots(frame, min_temp, max_temp, tracker)
            
            # Initialize VideoWriter after reading the first valid frame to get dimensions
            if out is None:
                h, w = annotated_frame.shape[:2]
                fourcc = cv2.VideoWriter_fourcc(*'avc1') # Wait avc1 is compatible with HTML5 video
                out = cv2.VideoWriter(out_video_path, fourcc, 30.0, (w, h))
            
            out.write(annotated_frame)
            
            ret, buffer = cv2.imencode('.jpg', annotated_frame)
            if not ret:
                continue
                
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            
            await asyncio.sleep(0.01)
    finally:
        # Save final state when generator stops
        LATEST_STREAM_RECORD["final_count"] = tracker.max_id_seen
        LATEST_STREAM_RECORD["video_path"] = out_video_path
        
        if out is not None:
            out.release()
        cap.release()

