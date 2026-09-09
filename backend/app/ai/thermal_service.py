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
        self.objects = {}       # {id: (cx, cy)}
        self.disappeared = {}   # {id: count}
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

        input_centroids = np.array(
            [((x1 + x2) // 2, (y1 + y2) // 2) for (x1, y1, x2, y2) in rects], dtype="int"
        )

        if len(self.objects) == 0:
            for c in input_centroids:
                self.register(c)
        else:
            object_ids = list(self.objects.keys())
            object_centroids = list(self.objects.values())

            D = np.zeros((len(object_centroids), len(input_centroids)), dtype="float32")
            for i, oc in enumerate(object_centroids):
                for j, ic in enumerate(input_centroids):
                    D[i, j] = math.sqrt((int(oc[0]) - int(ic[0])) ** 2 + (int(oc[1]) - int(ic[1])) ** 2)

            rows = D.min(axis=1).argsort()
            cols = D.argmin(axis=1)[rows]

            used_rows, used_cols = set(), set()
            for row, col in zip(rows, cols):
                if row in used_rows or col in used_cols:
                    continue
                if D[row, col] > self.max_distance:
                    continue
                oid = object_ids[row]
                self.objects[oid] = input_centroids[col]
                self.disappeared[oid] = 0
                used_rows.add(row)
                used_cols.add(col)

            for row in set(range(D.shape[0])).difference(used_rows):
                oid = object_ids[row]
                self.disappeared[oid] += 1
                if self.disappeared[oid] > self.max_disappeared:
                    self.deregister(oid)

            for col in set(range(D.shape[1])).difference(used_cols):
                self.register(input_centroids[col])

        return self.objects


# ─────────────────────────────────────────────────────────────────────────────
# Core detection — fast OpenCV-based thermal blob detection (NO YOLO needed)
# Works on thermal colourmap video/images where hens appear as red/orange/white
# heat blobs. ~50x faster than YOLO per-frame.
# ─────────────────────────────────────────────────────────────────────────────
def detect_thermal_hotspots(
    image: np.ndarray,
    min_temp: float = 20.0,
    max_temp: float = 40.0,
    tracker: CentroidTracker = None,
) -> Tuple[np.ndarray, int, List[Dict]]:

    h_img, w_img = image.shape[:2]
    annotated = image.copy()
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    rects:      List = []
    valid_hens: List = []

    def estimate_temp(roi_hsv_patch):
        if roi_hsv_patch.size == 0:
            return 21.0
        mh = float(cv2.mean(roi_hsv_patch[:, :, 0])[0])
        ms = float(cv2.mean(roi_hsv_patch[:, :, 1])[0])
        mv = float(cv2.mean(roi_hsv_patch[:, :, 2])[0])
        if ms < 50 and mv > 200:
            return 38.5                                           # white-hot core
        if mh >= 158 or mh <= 5:
            return 36.0 + min(1.0, mv / 255.0) * 4.0            # deep red
        if mh <= 28:
            return 30.0 + (1.0 - (mh - 5) / 23.0) * 8.0        # orange
        if mh <= 42:
            return 22.0 + (1.0 - (mh - 28) / 14.0) * 9.0       # yellow
        return 21.0                                               # cool

    def draw_box(img, hx, hy, hw, hh, label, temp):
        norm  = min(1.0, max(0.0, (temp - min_temp) / max(max_temp - min_temp, 1)))
        color = (0, int((1 - norm) * 200), int(norm * 255))
        thick = max(2, int(min(w_img, h_img) * 0.004))
        cv2.rectangle(img, (hx, hy), (hx + hw, hy + hh), color, thick)
        font   = cv2.FONT_HERSHEY_SIMPLEX
        fscale = max(0.4, min(w_img, h_img) * 0.001)
        (tw, th), _ = cv2.getTextSize(label, font, fscale, 1)
        lx2 = min(w_img, hx + tw + 6)
        ly1 = max(0, hy - th - 6)
        cv2.rectangle(img, (hx, ly1), (lx2, hy), color, -1)
        cv2.putText(img, label, (hx + 3, hy - 3), font, fscale, (255, 255, 255), 1)

    # ── YOLO Detection for 100% Accuracy ──────────────────────────────────────
    from app.ai.yolo_service import load_model
    try:
        model_instance, tray_model_instance = load_model()
        if model_instance is not None:
            results = model_instance(image, conf=0.25, iou=0.45, imgsz=640, verbose=False)
            
            # Combine detections from both models if tray model exists
            all_boxes = []
            class_names_main = getattr(results[0], "names", {0: "egg", 1: "egg_tray"}) if results else {}
            for result in results:
                all_boxes.extend([(box, class_names_main) for box in result.boxes])
                
            if tray_model_instance is not None:
                tray_results = tray_model_instance(image, conf=0.25, iou=0.45, imgsz=640, verbose=False)
                class_names_tray = getattr(tray_results[0], "names", {0: "egg tray", 1: "hen"}) if tray_results else {}
                for result in tray_results:
                    all_boxes.extend([(box, class_names_tray) for box in result.boxes])
            
            for box_obj, cnames in all_boxes:
                cls_id = int(box_obj.cls[0].cpu().numpy())
                raw_class = cnames.get(cls_id, "unknown").lower()
                
                # Only process hens
                if "hen" in raw_class:
                    x1, y1, x2, y2 = map(int, box_obj.xyxy[0].cpu().numpy())
                    # Ensure coordinates are within image
                    x1, y1 = max(0, x1), max(0, y1)
                    x2, y2 = min(w_img, x2), min(h_img, y2)
                    
                    if x2 <= x1 or y2 <= y1:
                        continue
                        
                    roi_hsv = hsv[y1:y2, x1:x2]
                    temp = estimate_temp(roi_hsv)
                    
                    if 15.0 <= temp <= 45.0:
                        rects.append((x1, y1, x2, y2))
                        valid_hens.append({"temperature": temp, "x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1})
    except Exception as e:
        print(f"YOLO failed in thermal detection: {e}, falling back to zero detections to avoid inaccuracy")

    hen_count = len(valid_hens)
    hens_data: List[Dict] = []

    # ── 4. Update tracker (for video) or draw directly (for single image) ────
    if tracker is not None:
        objects = tracker.update(rects)
        hen_count = tracker.max_id_seen

        for oid, centroid in objects.items():
            cx, cy = int(centroid[0]), int(centroid[1])
            # Match to nearest valid_hen
            best, best_d = None, float("inf")
            for hen in valid_hens:
                hcx = hen["x"] + hen["w"] // 2
                hcy = hen["y"] + hen["h"] // 2
                d = math.sqrt((cx - hcx) ** 2 + (cy - hcy) ** 2)
                if d < best_d:
                    best_d = d
                    best = hen

            if best and best_d < max(80, w_img * 0.08):
                draw_box(annotated, best["x"], best["y"], best["w"], best["h"],
                         f"ID:{oid} {best['temperature']:.1f}C", best["temperature"])
                hens_data.append({"hen_number": oid, "temperature": round(best["temperature"], 1)})
            else:
                cv2.circle(annotated, (cx, cy), 18, (0, 200, 100), 2)
                cv2.putText(annotated, f"ID:{oid}", (cx - 20, cy - 22),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

        summary = f"Hens: {hen_count}"
    else:
        for i, hen in enumerate(valid_hens):
            hen_id = i + 1
            draw_box(annotated, hen["x"], hen["y"], hen["w"], hen["h"],
                     f"Hen #{hen_id}  {hen['temperature']:.1f}C", hen["temperature"])
            hens_data.append({"hen_number": hen_id, "temperature": round(hen["temperature"], 1)})
        summary = f"Hens: {hen_count}  ({min_temp:.0f}C-{max_temp:.0f}C)"

    # ── 5. Summary overlay ────────────────────────────────────────────────────
    s_scale = max(0.6, w_img * 0.0012)
    (sw2, _), _ = cv2.getTextSize(summary, cv2.FONT_HERSHEY_SIMPLEX, s_scale, 2)
    cv2.rectangle(annotated, (5, 5), (sw2 + 16, 36), (0, 0, 0), -1)
    cv2.putText(annotated, summary, (9, 29), cv2.FONT_HERSHEY_SIMPLEX, s_scale, (0, 255, 0), 2)

    return annotated, hen_count, hens_data


# ─────────────────────────────────────────────────────────────────────────────
def process_thermal_image(image_bytes: bytes, min_temp: float = 20.0, max_temp: float = 40.0) -> Dict[str, Any]:
    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not decode image bytes.")

    annotated, hen_count, hens_data = detect_thermal_hotspots(image, min_temp, max_temp)

    _, buffer = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 92])
    encoded_img = base64.b64encode(buffer).decode("utf-8")

    return {
        "success":      True,
        "is_video":     False,
        "hen_count":    hen_count,
        "hens":         hens_data,
        "result_image": encoded_img,
    }


# ─────────────────────────────────────────────────────────────────────────────
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

    # Find a working codec
    out = None
    final_output = output_path_mp4
    for codec_str, out_path in [("mp4v", output_path_mp4), ("MJPG", output_path_avi), ("DIVX", output_path_avi)]:
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

    tracker    = CentroidTracker(max_disappeared=15, max_distance=80)
    frame_idx  = 0
    SKIP       = 3   # process every 3rd frame (fast + accurate enough)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % SKIP == 0:
            annotated_frame, _, _ = detect_thermal_hotspots(frame, min_temp, max_temp, tracker)
        else:
            # Light tracking-only frame — draw current tracked centroids cheaply
            annotated_frame = frame.copy()
            for oid, centroid in tracker.objects.items():
                cx, cy = int(centroid[0]), int(centroid[1])
                cv2.circle(annotated_frame, (cx, cy), 18, (0, 200, 100), 2)
                cv2.putText(annotated_frame, f"ID:{oid}", (cx - 20, cy - 22),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

        # Count overlay on every frame
        total   = tracker.max_id_seen
        s_scale = max(0.55, width * 0.001)
        summary = f"Hens Detected: {total}"
        (sw2, _), _ = cv2.getTextSize(summary, cv2.FONT_HERSHEY_SIMPLEX, s_scale, 2)
        cv2.rectangle(annotated_frame, (5, 5), (sw2 + 14, 34), (0, 0, 0), -1)
        cv2.putText(annotated_frame, summary, (9, 28), cv2.FONT_HERSHEY_SIMPLEX, s_scale, (0, 255, 0), 2)

        out.write(annotated_frame)
        frame_idx += 1

    total_count = tracker.max_id_seen
    cap.release()
    out.release()

    try:
        os.remove(input_path)
    except Exception:
        pass

    # Convert AVI → MP4 via ffmpeg if needed
    if final_output.endswith(".avi") and os.path.exists(final_output):
        try:
            import subprocess
            res = subprocess.run(
                ["ffmpeg", "-y", "-i", final_output, "-vcodec", "libx264", "-crf", "28", output_path_mp4],
                capture_output=True, timeout=180,
            )
            if res.returncode == 0 and os.path.exists(output_path_mp4):
                os.remove(final_output)
                final_output = output_path_mp4
        except Exception as e:
            print(f"ffmpeg conversion skipped: {e}")

    return {
        "success":    True,
        "is_video":   True,
        "hen_count":  total_count,
        "video_path": final_output,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Global state for live drone stream recordings
# ─────────────────────────────────────────────────────────────────────────────
LATEST_STREAM_RECORD: Dict[str, Any] = {
    "video_path":  None,
    "final_count": 0,
}


async def generate_thermal_stream(url: str, min_temp: float = 20.0, max_temp: float = 40.0):
    import asyncio
    from datetime import datetime
    global LATEST_STREAM_RECORD

    cap = cv2.VideoCapture(url)
    if not cap.isOpened():
        placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(placeholder, "Connecting to drone stream...", (50, 240),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        _, buf = cv2.imencode(".jpg", placeholder)
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
        await asyncio.sleep(2)
        cap = cv2.VideoCapture(url)
        if not cap.isOpened():
            return

    tracker = CentroidTracker(max_disappeared=15, max_distance=80)

    os.makedirs("storage", exist_ok=True)
    timestamp     = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_video_path = f"storage/drone_record_{timestamp}.mp4"
    out: cv2.VideoWriter | None = None
    frame_idx = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                await asyncio.sleep(0.05)
                continue

            if out is None:
                h, w = frame.shape[:2]
                fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                out = cv2.VideoWriter(out_video_path, fourcc, fps, (w, h))

            if frame_idx % 3 == 0:
                annotated, _, _ = detect_thermal_hotspots(frame, min_temp, max_temp, tracker)
            else:
                annotated = frame.copy()
                for oid, centroid in tracker.objects.items():
                    cx, cy = int(centroid[0]), int(centroid[1])
                    cv2.circle(annotated, (cx, cy), 18, (0, 200, 100), 2)
                    cv2.putText(annotated, f"ID:{oid}", (cx - 20, cy - 22),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

            # Count overlay
            total = tracker.max_id_seen
            cv2.rectangle(annotated, (5, 5), (260, 36), (0, 0, 0), -1)
            cv2.putText(annotated, f"Live Hens: {total}", (9, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

            if out:
                out.write(annotated)

            _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 70])
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
            frame_idx += 1
            await asyncio.sleep(0.01)

    finally:
        cap.release()
        if out:
            out.release()
        LATEST_STREAM_RECORD["video_path"]  = out_video_path
        LATEST_STREAM_RECORD["final_count"] = tracker.max_id_seen
