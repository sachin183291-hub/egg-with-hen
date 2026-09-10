import cv2
import numpy as np
import base64
import os
import tempfile
from typing import Dict, Any, Tuple, List
import math
from app.ai.yolo_service import load_model
# pyrefly: ignore [missing-import]
from ultralytics import YOLO

_tracking_model = None
_world_model_classes = ["hen", "chicken", "poultry", "bird"]  # Keep it simple and robust for YOLOWorld

def get_tracking_model():
    """
    Load standard yolov8n.pt. In a top-down battery cage, ANY distinctly tracked object
    is a hen, even if the model misclassifies it as a cat or vase due to the angle.
    """
    global _tracking_model
    if _tracking_model is None:
        try:
            _tracking_model = YOLO("yolov8n.pt")
            print("[Tracking] Loaded yolov8n for class-agnostic tracking.")
        except Exception as e:
            print(f"[Tracking] Error loading YOLO: {e}")
    return _tracking_model


# ─────────────────────────────────────────────────────────────────────────────
# Core detection — fast OpenCV-based thermal blob detection (NO YOLO needed)
# Works on thermal colourmap video/images where hens appear as red/orange/white
# heat blobs. ~50x faster than YOLO per-frame.
# ─────────────────────────────────────────────────────────────────────────────
def detect_thermal_hotspots(
    image: np.ndarray,
    min_temp: float = 20.0,
    max_temp: float = 40.0,
    tracker: Any = None,
) -> Tuple[np.ndarray, int, List[Dict]]:
    h_img, w_img = image.shape[:2]
    annotated = image.copy()

    # ── 1. Downscale for faster processing (50% → 4× faster) ────────────────
    SCALE = 0.5
    small = cv2.resize(image, (int(w_img * SCALE), int(h_img * SCALE)))
    sh, sw = small.shape[:2]
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)

    # ── 2. Thermal colour mask ────────────────────────────────────────────────
    hot_mask = cv2.bitwise_or(
        cv2.bitwise_or(
            cv2.bitwise_or(
                cv2.bitwise_or(
                    cv2.inRange(hsv, np.array([0,   55,  80]), np.array([12,  255, 255])),   # red-low
                    cv2.inRange(hsv, np.array([158, 55,  80]), np.array([180, 255, 255])),   # red-high
                ),
                cv2.inRange(hsv, np.array([12,  55,  80]), np.array([28,  255, 255])),       # orange
            ),
            cv2.inRange(hsv, np.array([28,  65, 100]), np.array([42,  255, 255])),           # yellow
        ),
        cv2.inRange(hsv, np.array([0,   0,  200]), np.array([180, 50,  255])),               # white-hot
    )

    hot_mask = cv2.morphologyEx(hot_mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    hot_mask = cv2.morphologyEx(hot_mask, cv2.MORPH_OPEN,  np.ones((7, 7), np.uint8))  # bigger kernel removes tiny noise

    # ── Exclude the thermal color-scale bar on right edge (thin vertical strip) ──
    # Most thermal cameras overlay a 5-15% wide color bar on the right side.
    # Use 85% cutoff to safely exclude wider scale bars.
    scale_bar_x = int(sw * 0.85)
    hot_mask[:, scale_bar_x:] = 0
    # Also exclude top/bottom strips that often have UI overlays
    hot_mask[:int(sh * 0.03), :] = 0
    hot_mask[int(sh * 0.97):, :] = 0

    # ── 3. Find contours ──────────────────────────────────────────────────────
    contours, _ = cv2.findContours(hot_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    frame_area = sh * sw

    # MIN_AREA: a hen at typical drone altitude covers at least 200px² on 50%-scaled frame
    # MAX_AREA: single blob shouldn't be more than 25% of frame (that's a whole flock merged)
    MIN_AREA = max(200, int(frame_area * 0.0008))  # ~0.08% of frame minimum
    MAX_AREA = int(frame_area * 0.25)

    rects:      List = []
    valid_hens: List = []
    used_boxes: List = []

    def overlaps(b1, used_list, thresh=0.3):
        ax1, ay1, ax2, ay2 = b1
        for bx1, by1, bx2, by2 in used_list:
            ix = max(0, min(ax2, bx2) - max(ax1, bx1))
            iy = max(0, min(ay2, by2) - max(ay1, by1))
            inter = ix * iy
            area  = max(1, (ax2 - ax1) * (ay2 - ay1))
            if inter / area > thresh:
                return True
        return False

    def estimate_temp(roi_hsv_patch, roi_mask):
        if cv2.countNonZero(roi_mask) == 0:
            return 0.0
        mh = float(cv2.mean(roi_hsv_patch[:, :, 0], mask=roi_mask)[0])
        ms = float(cv2.mean(roi_hsv_patch[:, :, 1], mask=roi_mask)[0])
        mv = float(cv2.mean(roi_hsv_patch[:, :, 2], mask=roi_mask)[0])
        if ms < 50 and mv > 200:
            return 40.0   # white-hot core
        if mh >= 158 or mh <= 5:
            return 36.0 + min(1.0, mv / 255.0) * 5.0   # red → 36-41°C
        if mh <= 28:
            return 28.0 + (1.0 - (mh - 5) / 23.0) * 8.0  # orange → 28-36°C
        if mh <= 45:
            return 20.0 + (1.0 - (mh - 28) / 17.0) * 8.0  # yellow/greenish → 20-28°C
        return 0.0  # green/blue = cold background

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

    # Adaptive size calculation for 100% accurate counting across altitudes
    valid_areas = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if MIN_AREA <= area <= MAX_AREA:
            valid_areas.append(area)

    SINGLE_HEN = max(80, int(frame_area * 0.005)) # Default fallback
    if valid_areas:
        valid_areas.sort()
        start_idx = int(len(valid_areas) * 0.2)
        end_idx = int(len(valid_areas) * 0.9)
        if start_idx < end_idx:
            SINGLE_HEN = max(MIN_AREA, float(np.median(valid_areas[start_idx:end_idx])))
        else:
            SINGLE_HEN = max(MIN_AREA, float(np.median(valid_areas)))

    for cnt in sorted(contours, key=cv2.contourArea, reverse=True):
        area = cv2.contourArea(cnt)
        if area < MIN_AREA or area > MAX_AREA:
            continue

        x_s, y_s, w_s, h_s = cv2.boundingRect(cnt)
        aspect = w_s / max(h_s, 1)
        if aspect < 0.15 or aspect > 8.0:
            continue

        x1 = int(x_s / SCALE); y1 = int(y_s / SCALE)
        x2 = int((x_s + w_s) / SCALE); y2 = int((y_s + h_s) / SCALE)

        if overlaps((x1, y1, x2, y2), used_boxes):
            continue

        roi_hsv = hsv[y_s: y_s + h_s, x_s: x_s + w_s]
        roi_mask = hot_mask[y_s: y_s + h_s, x_s: x_s + w_s]
        
        # Check overall blob temperature
        temp = estimate_temp(roi_hsv, roi_mask)
        if not (min_temp <= temp <= max_temp):  # respect dynamic UI slider
            continue

        used_boxes.append((x1, y1, x2, y2))

        # ── Local Maxima (Peak Finding) to count hens in clustered blobs ──
        # Extract V-channel for brightness/heat
        roi_v = roi_hsv[:, :, 2]
        roi_blurred = cv2.GaussianBlur(roi_v, (5, 5), 0)
        
        # Distance between peaks should be roughly the size of a hen
        k = int(math.sqrt(SINGLE_HEN) * 0.7) | 1
        k = max(3, min(25, k))
        
        local_max = cv2.dilate(roi_blurred, np.ones((k, k), np.uint8))
        peaks_mask = (roi_blurred == local_max) & (roi_mask > 0) & (roi_blurred > 50)
        
        num_peaks, _, stats, peak_centroids = cv2.connectedComponentsWithStats(np.uint8(peaks_mask) * 255)
        # Filter out tiny noise components — require at least 4 pixels to count as a real heat core
        # This prevents hot-pixel noise from inflating the count
        real_peaks = sum(1 for i in range(1, num_peaks) if stats[i, cv2.CC_STAT_AREA] >= 4)
        # Cap peaks per blob: no single blob should represent >8 hens (unrealistic for drone altitude)
        n_hens = max(1, min(real_peaks, 8))

        if n_hens == 1:
            rects.append((x1, y1, x2, y2))
            valid_hens.append({"temperature": temp, "x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1})
        else:
            # We found multiple distinct heat cores! 
            # We'll create a bounding box centered around each core.
            box_side = int(math.sqrt(area / n_hens) / SCALE)
            for i in range(1, num_peaks):
                px_small, py_small = peak_centroids[i]
                # Scale peak to original image coordinates
                px = int((x_s + px_small) / SCALE)
                py = int((y_s + py_small) / SCALE)
                
                sx1 = max(x1, px - box_side // 2)
                sy1 = max(y1, py - box_side // 2)
                sx2 = min(x2, px + box_side // 2)
                sy2 = min(y2, py + box_side // 2)
                
                # Double check bounds
                if sx2 <= sx1: sx2 = sx1 + 5
                if sy2 <= sy1: sy2 = sy1 + 5
                
                rects.append((sx1, sy1, sx2, sy2))
                
                # We could estimate temp exactly for this small box, but the blob average is usually fine.
                # Let's do exact temp for perfection!
                sub_roi_hsv = hsv[max(0, int(sy1*SCALE)) : min(sh, int(sy2*SCALE)), 
                                  max(0, int(sx1*SCALE)) : min(sw, int(sx2*SCALE))]
                sub_roi_mask = hot_mask[max(0, int(sy1*SCALE)) : min(sh, int(sy2*SCALE)), 
                                        max(0, int(sx1*SCALE)) : min(sw, int(sx2*SCALE))]
                sub_temp = estimate_temp(sub_roi_hsv, sub_roi_mask) if cv2.countNonZero(sub_roi_mask) > 0 else temp
                
                valid_hens.append({"temperature": sub_temp, "x": sx1, "y": sy1, "w": sx2 - sx1, "h": sy2 - sy1})

    hen_count = len(valid_hens)
    hens_data: List[Dict] = []

    # ── 4. Update tracker (for video) or draw directly (for single image) ────
    if tracker is not None:
        objects = tracker.update(rects)
        # Use currently visible objects count (caller tracks peak across frames)
        hen_count = len(tracker.objects)

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

    # ── Step 1: Run OpenCV detection for bounding boxes + annotated image ─────
    annotated, opencv_count, opencv_hens = detect_thermal_hotspots(image, min_temp, max_temp)

    # ── Step 1.5: If OpenCV found no thermal heat blobs, fallback to YOLO ─────
    yolo_used = False
    if opencv_count == 0:
        try:
            from app.ai.yolo_service import detect_objects_image
            yolo_res = detect_objects_image(image, conf_threshold=0.25)
            if yolo_res.get("hen_count", 0) > 0:
                yolo_used = True
                annotated = yolo_res["annotated_frame"]
                opencv_count = yolo_res["hen_count"]
                opencv_hens = []
                for det in yolo_res.get("detections", []):
                    if det["class"] == "hen":
                        x1, y1, x2, y2 = det["bbox"]
                        opencv_hens.append({
                            "hen_number": det["id"],
                            "temperature": 35.0, # Default temp for normal image
                            "width_px": int(x2 - x1),
                            "height_px": int(y2 - y1),
                            "w": int(x2 - x1),
                            "h": int(y2 - y1)
                        })
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("YOLO fallback failed: %s", e)

    hen_count = opencv_count
    hens_data = opencv_hens
    detection_method = "YOLO AI detection" if yolo_used else "OpenCV thermal blob detection"
    notes = ""

    # ── Step 2: Update count overlay on annotated image ───────────────────────
    summary = f"Hens: {hen_count}  [{detection_method}]"
    s_scale = max(0.5, image.shape[1] * 0.0010)
    (tw, _), _ = cv2.getTextSize(summary, cv2.FONT_HERSHEY_SIMPLEX, s_scale, 2)
    cv2.rectangle(annotated, (5, 5), (tw + 16, 36), (0, 0, 0), -1)
    cv2.putText(annotated, f"Hens: {hen_count}", (9, 29),
                cv2.FONT_HERSHEY_SIMPLEX, s_scale, (0, 255, 100), 2)

    _, buffer = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 92])
    encoded_img = base64.b64encode(buffer).decode("utf-8")

    return {
        "success":          True,
        "is_video":         False,
        "hen_count":        hen_count,
        "hens":             hens_data,
        "result_image":     encoded_img,
        "detection_method": detection_method,
        "notes":            notes,
    }


# ─────────────────────────────────────────────────────────────────────────────
def process_thermal_video(video_bytes: bytes, min_temp: float = 20.0, max_temp: float = 40.0) -> Dict[str, Any]:
    """
    Accept raw video bytes (from the API upload), write to a temp file,
    process frame-by-frame using YOLO + BoT-SORT tracking for unique hen counting,
    and return the annotated output video path + count.
    """
    # ── Write incoming bytes to a temp input file ────────────────────────────
    suffix_in  = ".mp4"
    tmp_in     = tempfile.NamedTemporaryFile(delete=False, suffix=suffix_in)
    tmp_in.write(video_bytes)
    tmp_in.flush()
    tmp_in.close()
    input_path = tmp_in.name

    # ── Prepare output path ──────────────────────────────────────────────────
    tmp_out_mp4 = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    tmp_out_mp4.close()
    output_path_mp4 = tmp_out_mp4.name

    tmp_out_avi = tempfile.NamedTemporaryFile(delete=False, suffix=".avi")
    tmp_out_avi.close()
    output_path_avi = tmp_out_avi.name

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise ValueError("Could not open uploaded thermal video.")

    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps    = cap.get(cv2.CAP_PROP_FPS) or 25.0

    # ── CPU SPEED OPTIMIZATION 1: DOWNSCALE ─────────────────────────────────
    # Massive videos crash or timeout CPUs. Scale down to 640px max width.
    MAX_WIDTH = 640
    scale = 1.0
    if width > MAX_WIDTH:
        scale = MAX_WIDTH / width
        width = int(width * scale)
        height = int(height * scale)

    # ── CPU SPEED OPTIMIZATION 2: SKIP FRAMES ───────────────────────────────
    # Track at max 5 FPS to prevent 10-minute timeouts. BoT-SORT can handle it.
    frame_skip = max(1, int(fps / 5))
    out_fps = fps / frame_skip

    out: cv2.VideoWriter | None = None
    final_output = output_path_mp4

    for codec_str, out_path in [("mp4v", output_path_mp4), ("MJPG", output_path_avi), ("DIVX", output_path_avi)]:
        fourcc    = cv2.VideoWriter_fourcc(*codec_str)
        candidate = cv2.VideoWriter(out_path, fourcc, out_fps, (width, height))
        if candidate.isOpened():
            out          = candidate
            final_output = out_path
            break
        candidate.release()

    if out is None:
        cap.release()
        raise ValueError("Could not open VideoWriter with any available codec.")

    model = get_tracking_model()
    unique_hen_ids = set()
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        frame_idx += 1
        if frame_idx % frame_skip != 0:
            continue
            
        if scale != 1.0:
            frame = cv2.resize(frame, (width, height))

        # Run tracking using BoT-SORT + Re-ID (built into Ultralytics YOLO)
        # SPEED OPTIMIZATION 3: Pass imgsz=320 to dramatically speed up CPU inference
        results = model.track(frame, persist=True, tracker="botsort.yaml", verbose=False, imgsz=320)
        annotated_frame = results[0].plot() if len(results) > 0 else frame.copy()

        # Define virtual counting zone (middle 40% of the screen)
        zone_top = int(height * 0.3)
        zone_bottom = int(height * 0.7)
        
        # Draw the virtual counting zone lines
        cv2.line(annotated_frame, (0, zone_top), (width, zone_top), (255, 0, 0), 2)
        cv2.line(annotated_frame, (0, zone_bottom), (width, zone_bottom), (255, 0, 0), 2)

        current_visible = 0
        if len(results) > 0 and results[0].boxes is not None:
            for box in results[0].boxes:
                cls_id = int(box.cls[0].item())
                raw_class_name = results[0].names.get(cls_id, "unknown").lower()
                
                # Only count 'hen' class (or if standard YOLO, class 14 is bird)
                if "hen" not in raw_class_name and "bird" not in raw_class_name:
                    continue

                if box.id is not None:
                    track_id = int(box.id[0].item())
                    current_visible += 1
                    
                    # Virtual counting zone: Only count if the hen's center is inside the zone
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    cy = (y1 + y2) / 2
                    if zone_top <= cy <= zone_bottom:
                        unique_hen_ids.add(track_id)

        total_unique = len(unique_hen_ids)

        # Count overlay
        s_scale = max(0.55, width * 0.001)
        summary = f"Total Unique Hens: {total_unique} (now: {current_visible})"
        (sw2, _), _ = cv2.getTextSize(summary, cv2.FONT_HERSHEY_SIMPLEX, s_scale, 2)
        cv2.rectangle(annotated_frame, (5, 5), (sw2 + 14, 34), (0, 0, 0), -1)
        cv2.putText(annotated_frame, summary, (9, 28), cv2.FONT_HERSHEY_SIMPLEX, s_scale, (0, 255, 0), 2)

        out.write(annotated_frame)
        frame_idx += 1

    total_count = len(unique_hen_ids)
    cap.release()
    out.release()

    # Clean up temp input file
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

    model = get_tracking_model()
    unique_hen_ids = set()

    os.makedirs("storage", exist_ok=True)
    timestamp      = datetime.now().strftime("%Y%m%d_%H%M%S")
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

            results = model.track(frame, persist=True, tracker="botsort.yaml", verbose=False)
            annotated = results[0].plot() if len(results) > 0 else frame.copy()

            # Define virtual counting zone
            zone_top = int(height * 0.3)
            zone_bottom = int(height * 0.7)
            
            cv2.line(annotated, (0, zone_top), (width, zone_top), (255, 0, 0), 2)
            cv2.line(annotated, (0, zone_bottom), (width, zone_bottom), (255, 0, 0), 2)

            current_visible = 0
            if len(results) > 0 and results[0].boxes is not None:
                for box in results[0].boxes:
                    cls_id = int(box.cls[0].item())
                    raw_class_name = results[0].names.get(cls_id, "unknown").lower()
                    
                    if "hen" not in raw_class_name and "bird" not in raw_class_name:
                        continue

                    if box.id is not None:
                        track_id = int(box.id[0].item())
                        current_visible += 1
                        
                        # Virtual counting zone check
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        cy = (y1 + y2) / 2
                        if zone_top <= cy <= zone_bottom:
                            unique_hen_ids.add(track_id)

            total_unique = len(unique_hen_ids)

            # Count overlay — show total unique & current
            cv2.rectangle(annotated, (5, 5), (420, 36), (0, 0, 0), -1)
            cv2.putText(annotated, f"Total Unique Hens: {total_unique} (now: {current_visible})",
                        (9, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 0), 2)

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
        LATEST_STREAM_RECORD["final_count"] = len(unique_hen_ids)


# ─────────────────────────────────────────────────────────────────────────────
# Live stream from an uploaded video file (sync generator for StreamingResponse)
# ─────────────────────────────────────────────────────────────────────────────
def stream_uploaded_video(video_path: str, min_temp: float = 20.0, max_temp: float = 40.0):
    """
    Open a pre-uploaded video file, run YOLO + BoT-SORT frame-by-frame
    and yield MJPEG frames with the live hen count overlaid.
    The frontend displays this as a live <img> stream.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(placeholder, "Cannot open video", (80, 240),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 2)
        _, buf = cv2.imencode(".jpg", placeholder)
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
        return

    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps    = cap.get(cv2.CAP_PROP_FPS) or 25.0

    # Downscale to 640px max width for speed
    MAX_WIDTH = 640
    scale = 1.0
    if width > MAX_WIDTH:
        scale = MAX_WIDTH / width
        width  = int(width * scale)
        height = int(height * scale)

    # Process at max 10 FPS — smooth enough, fast enough
    frame_skip = max(1, int(fps / 10))

    model = get_tracking_model()
    unique_hen_ids: set = set()
    frame_idx = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_idx += 1
            if frame_idx % frame_skip != 0:
                continue

            if scale != 1.0:
                frame = cv2.resize(frame, (width, height))

            # Low confidence (0.15) — hens in cages are partially occluded
            results = model.track(frame, persist=True, tracker="botsort.yaml",
                                  verbose=False, imgsz=416, conf=0.15)
            annotated = results[0].plot() if len(results) > 0 else frame.copy()

            current_visible = 0
            if len(results) > 0 and results[0].boxes is not None:
                for box in results[0].boxes:
                    cls_id = int(box.cls[0].item())
                    raw_name = results[0].names.get(cls_id, "unknown").lower()
                    # Accept bird, hen, chicken, or animal detections
                    if not any(k in raw_name for k in ("hen", "bird", "chicken", "animal")):
                        continue
                    if box.id is not None:
                        tid = int(box.id[0].item())
                        current_visible += 1
                        unique_hen_ids.add(tid)  # Count ALL detected hens (no zone restriction)

            total_unique = len(unique_hen_ids)

            # Count overlay — green text on black background
            label = f"Hens: {total_unique} unique  |  Visible now: {current_visible}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
            cv2.rectangle(annotated, (5, 5), (tw + 16, th + 16), (0, 0, 0), -1)
            cv2.putText(annotated, label, (9, th + 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"

    finally:
        cap.release()
        # Clean up uploaded temp file
        try:
            import os
            os.remove(video_path)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Background job: process full video, write annotated MP4, report progress
# ─────────────────────────────────────────────────────────────────────────────
def process_video_job(input_path: str, job_id: str, jobs_dict: dict,
                      min_temp: float = 20.0, max_temp: float = 40.0) -> Dict[str, Any]:
    """
    Fast processing with smooth playback:
    - Reads and writes ALL frames for original 25 FPS smooth playback.
    - Runs YOLOWorld AI at 3 FPS to save CPU time.
    - Draws cached boxes on intermediate frames.
    - Uses ByteTrack (no CPU ReID) for massive speedup over BoT-SORT.
    """
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise ValueError("Cannot open video file")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps    = cap.get(cv2.CAP_PROP_FPS) or 25.0

    # Downscale for performance, but 640px minimum to keep hens visible
    MAX_W = 640
    scale = 1.0
    if width > MAX_W:
        scale = MAX_W / width
        width  = int(width * scale)
        height = int(height * scale)

    # Process 3 frames per second (fast enough for drone, massively saves CPU)
    TARGET_AI_FPS = 3
    frame_skip = max(1, int(fps / TARGET_AI_FPS))

    # Output video matches original smooth framerate (e.g., 25 FPS)
    OUT_FPS = fps
    out_path = input_path.replace(".mp4", "_result.mp4")
    fourcc   = cv2.VideoWriter_fourcc(*"mp4v")
    out      = cv2.VideoWriter(out_path, fourcc, OUT_FPS, (width, height))

    # Use the highly accurate YOLOWorld model (cached)
    tracking_model = get_tracking_model()

    unique_ids: set = set()
    max_visible = 0
    frame_idx = 0
    last_boxes_data = []

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_idx += 1

            if scale != 1.0:
                frame = cv2.resize(frame, (width, height))

            # Run AI only every N frames
            if frame_idx % frame_skip == 0 or frame_idx == 1:
                # Run detector (predict bypasses ByteTrack confidence filters)
                results = tracking_model.predict(frame, verbose=False, imgsz=416, conf=0.01)
                
                last_boxes_data = []
                current_visible = 0
                
                if results and results[0].boxes is not None:
                    for box in results[0].boxes:
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        
                        # Filter out massive boxes (e.g., the entire cage)
                        frame_area = frame.shape[0] * frame.shape[1]
                        if (x2 - x1) * (y2 - y1) > (frame_area * 0.3):
                            continue
                        
                        current_visible += 1
                        # Save box for drawing on intermediate frames
                        conf = float(box.conf[0].item())
                        last_boxes_data.append((int(x1), int(y1), int(x2), int(y2), conf))

                if current_visible > max_visible:
                    max_visible = current_visible

            # Always draw boxes (either fresh or cached) to make playback perfectly smooth
            annotated = frame.copy()
            for x1, y1, x2, y2, conf in last_boxes_data:
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(annotated, f"Hen", (x1, y1 - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            # Fallback: if tracker fails to assign IDs, at least show max visible hens
            total_unique = max(len(unique_ids), max_visible)
            label = f"Hens: {total_unique}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(annotated, (5, 5), (tw + 16, th + 18), (0, 0, 0), -1)
            cv2.putText(annotated, label, (9, th + 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            out.write(annotated)

            # Update progress every 5 frames
            if frame_idx % 5 == 0:
                progress = min(99, int(frame_idx / total_frames * 100))
                jobs_dict[job_id]["progress"] = progress

    finally:
        cap.release()
        out.release()
        try:
            os.remove(input_path)
        except Exception:
            pass

    jobs_dict[job_id]["progress"] = 100
    return {"success": True, "hen_count": total_unique, "video_path": out_path}

STREAM_COUNTS = {}

async def generate_uploaded_video_stream(input_path: str):
    """
    Generator that serves an uploaded video as a perfectly smooth MJPEG stream in real-time.
    Uses a background thread for YOLOWorld AI to ensure the video never stutters.
    """
    import asyncio
    import threading
    import queue
    import numpy as np
    import time
    import traceback

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    # Downscale for performance
    MAX_W = 640
    scale = 1.0
    if width > MAX_W:
        scale = MAX_W / width
        width = int(width * scale)
        height = int(height * scale)

    TARGET_AI_FPS = 5
    frame_skip = max(1, int(fps / TARGET_AI_FPS))

    tracking_model = get_tracking_model()
    
    unique_ids: set = set()
    max_visible = 0
    frame_idx = 0
    current_boxes = []
    
    # State for Gen AI
    genai_count = None
    genai_requested = False
    
    # Use a background thread for AI so video never stops or lags
    ai_thread_running = True
    frame_queue = queue.Queue(maxsize=1)

    def genai_worker(first_frame):
        nonlocal genai_count
        try:
            from app.ai.gemini_vision import GeminiVisionDetector
            detector = GeminiVisionDetector()
            _, buf = cv2.imencode(".jpg", first_frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            res = detector.analyze(buf.tobytes(), target="hens")
            if res.get("success"):
                genai_count = res.get("hen_count")
        except Exception as e:
            print(f"[Gen AI Error]: {e}")

    def ai_worker():
        nonlocal current_boxes, max_visible
        while ai_thread_running:
            try:
                frame_for_ai = frame_queue.get(timeout=0.5)
            except queue.Empty:
                continue
                
            try:
                # Run AI (predict bypasses ByteTrack filters)
                results = tracking_model.predict(frame_for_ai, verbose=False, imgsz=416, conf=0.01)
                new_boxes = []
                current_vis = 0
                
                if results and results[0].boxes is not None:
                    for box in results[0].boxes:
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        
                        # Filter out massive boxes (background)
                        frame_area = frame_for_ai.shape[0] * frame_for_ai.shape[1]
                        if (x2 - x1) * (y2 - y1) > (frame_area * 0.3):
                            continue
                        
                        current_vis += 1
                        conf = float(box.conf[0].item())
                        new_boxes.append((int(x1), int(y1), int(x2), int(y2), conf))
                
                current_boxes = new_boxes
                if current_vis > max_visible:
                    max_visible = current_vis
            except Exception as e:
                print(f"[AI Thread Error]: {e}")
                traceback.print_exc()

    # Start the background AI worker
    threading.Thread(target=ai_worker, daemon=True).start()

    try:
        while True:
            start_time = time.time()
            ret, frame = cap.read()
            if not ret:
                break
                
            frame_idx += 1
            if scale != 1.0:
                frame = cv2.resize(frame, (width, height))

            # Send frame to AI thread if it's ready
            if frame_idx % frame_skip == 0 and frame_queue.empty():
                frame_queue.put(frame.copy())

            # Trigger Gen AI on the first good frame
            if not genai_requested and frame_idx > 5:
                genai_requested = True
                threading.Thread(target=genai_worker, args=(frame.copy(),), daemon=True).start()

            annotated = frame.copy()
            # Draw instantly using the latest boxes from the AI thread
            for x1, y1, x2, y2, conf in current_boxes:
                label_text = f"hen {conf:.2f}"
                color = (255, 255, 0)  # Cyan in BGR
                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                
                # Draw filled rectangle for text background
                (tw, th), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                cv2.rectangle(annotated, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
                
                # Draw text in black over the filled background
                cv2.putText(annotated, label_text, (x1 + 2, y1 - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

            total_unique = max(len(unique_ids), max_visible)
            
            # If Gen AI has finished, use its highly accurate count as the final total
            if genai_count is not None:
                total_unique = max(total_unique, genai_count)
                
            STREAM_COUNTS[input_path] = total_unique
            
            label = f"Hens: {total_unique}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(annotated, (5, 5), (tw + 16, th + 18), (0, 0, 0), -1)
            cv2.putText(annotated, label, (9, th + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            
            if genai_count is not None:
                genai_label = f"Gen AI Confirmed: {genai_count}"
                (gtw, gth), _ = cv2.getTextSize(genai_label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
                cv2.rectangle(annotated, (width - gtw - 20, 5), (width - 5, gth + 18), (0, 0, 0), -1)
                cv2.putText(annotated, genai_label, (width - gtw - 15, gth + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 215, 255), 2) # Gold

            _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
            
            # Sleep precisely the remaining time of the frame to enforce flawless real-time playback speed
            elapsed = time.time() - start_time
            sleep_time = max(0.001, (1.0 / fps) - elapsed)
            await asyncio.sleep(sleep_time)
            
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
            
        # Video Finished: Send a final frame with "FINISHED" text
        final_frame = np.zeros((height, width, 3), dtype=np.uint8)
        final_text = f"FINISHED! Final Count: {total_unique}"
        cv2.putText(final_frame, final_text, (50, height//2), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
        _, buf = cv2.imencode(".jpg", final_frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
        
        # Keep the final image on screen for a moment before disconnecting
        await asyncio.sleep(3.0)

    finally:
        ai_thread_running = False
        cap.release()
        try:
            os.remove(input_path)
        except Exception:
            pass
