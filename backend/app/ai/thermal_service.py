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
    h_img, w_img = image.shape[:2]
    annotated = image.copy()
    
    roi_mask = np.zeros(image.shape[:2], dtype=np.uint8)
    top_margin    = int(h_img * 0.08)
    bottom_margin = int(h_img * 0.92)
    left_margin   = int(w_img * 0.02)
    right_margin  = int(w_img * 0.80)
    
    roi_mask[top_margin:bottom_margin, left_margin:right_margin] = 255
    
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    
    mask_red_low  = cv2.inRange(hsv, np.array([0,   80, 80]),  np.array([12,  255, 255]))
    mask_red_high = cv2.inRange(hsv, np.array([158, 80, 80]),  np.array([180, 255, 255]))
    mask_orange   = cv2.inRange(hsv, np.array([12,  80, 80]),  np.array([28,  255, 255]))
    mask_yellow   = cv2.inRange(hsv, np.array([28,  90, 100]), np.array([42,  255, 255]))
    mask_white    = cv2.inRange(hsv, np.array([0,    0, 210]), np.array([180, 45,  255]))
    
    hot_mask = cv2.bitwise_or(mask_red_low,  mask_red_high)
    hot_mask = cv2.bitwise_or(hot_mask,       mask_orange)
    hot_mask = cv2.bitwise_or(hot_mask,       mask_yellow)
    hot_mask = cv2.bitwise_or(hot_mask,       mask_white)
    hot_mask = cv2.bitwise_and(hot_mask, roi_mask)
    
    kernel_close = np.ones((7, 7), np.uint8)
    kernel_open  = np.ones((3, 3), np.uint8)
    hot_mask = cv2.morphologyEx(hot_mask, cv2.MORPH_CLOSE, kernel_close)
    hot_mask = cv2.morphologyEx(hot_mask, cv2.MORPH_OPEN,  kernel_open)
    
    contours, _ = cv2.findContours(hot_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    frame_area = h_img * w_img
    used_boxes = []
    
    contours = sorted(contours, key=cv2.contourArea, reverse=True)
    
    rects = []
    valid_hens = []
    
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 300 or area > frame_area * 0.18:
            continue
            
        x, y, w, h = cv2.boundingRect(contour)
        aspect_ratio = float(w) / float(h) if h > 0 else 0
        if aspect_ratio < 0.20 or aspect_ratio > 6.0:
            continue
            
        def iou(a, b):
            ax1, ay1, ax2, ay2 = a[0], a[1], a[0]+a[2], a[1]+a[3]
            bx1, by1, bx2, by2 = b[0], b[1], b[0]+b[2], b[1]+b[3]
            ix1, iy1 = max(ax1, bx1), max(ay1, by1)
            ix2, iy2 = min(ax2, bx2), min(ay2, by2)
            inter = max(0, ix2-ix1) * max(0, iy2-iy1)
            union = (ax2-ax1)*(ay2-ay1) + (bx2-bx1)*(by2-by1) - inter
            return inter / union if union > 0 else 0
            
        if any(iou((x, y, w, h), ub) > 0.35 for ub in used_boxes):
            continue
            
        blob_hsv     = hsv[y:y+h, x:x+w]
        blob_mask_roi = hot_mask[y:y+h, x:x+w]
        
        if cv2.countNonZero(blob_mask_roi) == 0:
            continue
            
        mean_hue = cv2.mean(blob_hsv[:, :, 0], mask=blob_mask_roi)[0]
        mean_val = cv2.mean(blob_hsv[:, :, 2], mask=blob_mask_roi)[0]
        mean_sat = cv2.mean(blob_hsv[:, :, 1], mask=blob_mask_roi)[0]
        
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
            used_boxes.append((x, y, w, h))
            rects.append((x, y, x + w, y + h))
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
    temp_dir   = tempfile.gettempdir()
    input_path = os.path.join(temp_dir, "input_thermal.mp4")
    output_path = os.path.join(temp_dir, "output_thermal.mp4")
    
    with open(input_path, "wb") as f:
        f.write(video_bytes)
    
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise ValueError("Could not open video file.")
    
    fps    = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    fourcc = cv2.VideoWriter_fourcc(*'avc1')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    if not out.isOpened():
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    
    tracker = CentroidTracker(max_disappeared=15, max_distance=80)
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        annotated_frame, current_total_count, _ = detect_thermal_hotspots(frame, min_temp, max_temp, tracker)
        out.write(annotated_frame)
    
    total_count = tracker.max_id_seen
    
    cap.release()
    out.release()
    if os.path.exists(input_path):
        os.remove(input_path)
    
    return {
        "success":    True,
        "is_video":   True,
        "hen_count":  total_count,
        "video_path": output_path
    }
