import os
import math
import uuid
import time
import json
from flask import Flask, request, render_template_string, jsonify, Response, send_from_directory
from werkzeug.utils import secure_filename
from flask_cors import CORS
import cv2
import torch
torch.set_num_threads(4)
import numpy as np
from ultralytics import YOLO

app = Flask(__name__)
CORS(app)
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Global reference video settings (learned from uploaded reference video)
reference_settings = {
    'roi_y1_pct': 0.15,
    'roi_y2_pct': 0.85,
    'conf_threshold': 0.40,
    'avg_hen_count': 0,
    'reference_video': None
}

current_total_count = 0
active_stream = None

@app.route('/', methods=['GET'])
def index_route():
    return jsonify({
        "status": "online",
        "service": "GioTag AI Tracking Server",
        "version": "1.0",
        "model": os.path.basename(MODEL_PATH),
        "active_stream": active_stream
    })

# 1. Use the trained HEN_COMB YOLO model
MODEL_PATH = '/content/gdrive/MyDrive/Poultry_AI_Project/HEN_COMB_1280_TRAINING/hen_comb_1280_100ep/weights/best.pt'
_this_dir = os.path.dirname(os.path.abspath(__file__))
if not os.path.exists(MODEL_PATH):
    possible_paths = [
        os.path.join(_this_dir, 'backend', 'best.pt'),
        os.path.join(_this_dir, 'best.pt'),
        'best.pt'
    ]
    for p in possible_paths:
        if os.path.exists(p):
            MODEL_PATH = p
            break
    else:
        MODEL_PATH = 'yolov8n.pt'

print(f"Loading YOLO model from {MODEL_PATH}...")
device = "cuda" if torch.cuda.is_available() else "cpu"
try:
    model = YOLO(MODEL_PATH)
except Exception as e:
    print(f"Error loading model: {e}")
    model = None

if model is not None:
    try:
        _dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        model.predict(_dummy, imgsz=640, verbose=False)
        print("YOLO model warmed up successfully.")
    except Exception as e:
        print(f"Warmup notice: {e}")

CONF_THRESHOLD = 0.25
IOU_THRESHOLD = 0.45
MAX_LOST_FRAMES = 180
BASE_MATCH_DISTANCE = 180
MAX_FAST_MATCH_DISTANCE = 400

def center_of(box):
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)

import threading

def generate_frames(video_path):
    return _sync_generate_frames(video_path, None)

def generate_frames_with_ref(video_source, ref_settings):
    return _sync_generate_frames(video_source, ref_settings)

def _sync_generate_frames(video_source, ref_settings):
    is_live = video_source == 'camera' or str(video_source) == '0'
    if is_live:
        # Use DirectShow on Windows for faster webcam init and set buffer to 1 to prevent latency/lag
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW) if os.name == 'nt' else cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    else:
        cap = cv2.VideoCapture(video_source)
        
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    ret, sample_frame = cap.read()
    if not ret:
        cap.release()
        return
        
    frame_h, frame_w = sample_frame.shape[:2]
    
    if ref_settings:
        roi_x1 = 0
        roi_y1 = int(frame_h * ref_settings.get('roi_y1_pct', 0.15))
        roi_x2 = frame_w
        roi_y2 = int(frame_h * ref_settings.get('roi_y2_pct', 0.85))
        learned_conf = ref_settings.get('conf_threshold', 0.40)
        avg_ref_hens = ref_settings.get('avg_hen_count', 0)
    else:
        roi_x1 = 0
        roi_y1 = int(frame_h * 0.15)
        roi_x2 = frame_w
        roi_y2 = int(frame_h * 0.85)
        learned_conf = 0.25
        avg_ref_hens = 0
        
    if not is_live:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        
    import math
    import time
    import threading
    hens = {}
    next_num = 1
    total_counted = 0
    
    global current_total_count
    current_total_count = 0
    
    total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) if not is_live else 0
    frame_delay = 1.0 / fps if fps > 0 else 1.0 / 30.0
    t_stream_start = time.time()
    
    prev_small_gray = None
    frame_no = 0

    # Thread-safe AI background worker
    ai_lock = threading.Lock()
    ai_pending = None
    ai_pending_fno = 0
    ai_result = None
    ai_result_fno = 0
    ai_running = True
    cam_positions = {0: (0.0, 0.0)}

    def is_pure_comb(box, img):
        x1, y1, x2, y2 = map(int, box)
        w = x2 - x1
        h = y2 - y1
        area = w * h
        # Strict comb / head dimensions (25-165px) - excludes large hen body (200-500px)
        if w < 25 or h < 25 or w > 165 or h > 165:
            return False
        if area < 900 or area > 22000:
            return False
        aspect = w / float(max(h, 1))
        if aspect < 0.35 or aspect > 2.2:
            return False
        # Red comb color verification in HSV
        crop = img[max(0, y1):min(img.shape[0], y2), max(0, x1):min(img.shape[1], x2)]
        if crop.size > 0:
            hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
            mask1 = cv2.inRange(hsv, np.array([0, 35, 35]), np.array([16, 255, 255]))
            mask2 = cv2.inRange(hsv, np.array([150, 35, 35]), np.array([180, 255, 255]))
            red_ratio = (cv2.countNonZero(mask1) + cv2.countNonZero(mask2)) / float(crop.shape[0] * crop.shape[1])
            if red_ratio < 0.10:
                return False
        return True

    def ai_worker():
        nonlocal ai_running, ai_result, ai_result_fno, ai_pending, ai_pending_fno
        while ai_running:
            f_proc = None
            f_proc_no = 0
            with ai_lock:
                if ai_pending is not None:
                    f_proc = ai_pending
                    f_proc_no = ai_pending_fno
                    ai_pending = None
            if f_proc is None:
                time.sleep(0.005)
                continue

            try:
                res = model.predict(f_proc, verbose=False, conf=0.15, iou=0.35, imgsz=512)
                raw = []
                if res and len(res) > 0 and res[0].boxes is not None:
                    bx = res[0].boxes.xyxy.cpu().numpy()
                    cf = res[0].boxes.conf.cpu().numpy()
                    for b, c in zip(bx, cf):
                        if c < 0.15: continue
                        if not is_pure_comb(b, f_proc): continue
                        x1, y1, x2, y2 = map(int, b)
                        raw.append({
                            "box": (x1, y1, x2, y2),
                            "center": ((x1 + x2) / 2.0, (y1 + y2) / 2.0),
                            "size": (x2 - x1, y2 - y1),
                            "conf": float(c)
                        })
                with ai_lock:
                    ai_result = raw
                    ai_result_fno = f_proc_no
            except Exception:
                pass

    threading.Thread(target=ai_worker, daemon=True).start()

    def deduplicate_detections(raw_list):
        raw_list.sort(key=lambda d: d["conf"], reverse=True)
        dets = []
        for r_det in raw_list:
            rcx, rcy = r_det["center"]
            is_dup = False
            for ex in dets:
                if math.hypot(rcx - ex["center"][0], rcy - ex["center"][1]) < 45:
                    is_dup = True; break
            if not is_dup:
                dets.append(r_det)
        return dets

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                if not is_live and total_video_frames > 0:
                    # Clean video loop: reset state so Hen IDs never collide or duplicate across loops
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    hens.clear()
                    next_num = 1
                    frame_no = 0
                    prev_small_gray = None
                    cam_positions = {0: (0.0, 0.0)}
                    t_stream_start = time.time()
                    continue
                break
            
            frame_no += 1

            # Downscaled grayscale for sub-2ms optical flow head tracking (640x360)
            small_gray = cv2.cvtColor(cv2.resize(frame, (640, 360)), cv2.COLOR_BGR2GRAY)
            scale_x = frame.shape[1] / 640.0
            scale_y = frame.shape[0] / 360.0

            # Estimate camera translation for latency compensation
            cam_dx, cam_dy = 0.0, 0.0
            if prev_small_gray is not None:
                shift, resp = cv2.phaseCorrelate(prev_small_gray.astype(np.float32), small_gray.astype(np.float32))
                if resp > 0.04 and abs(shift[0]) < 25 and abs(shift[1]) < 25:
                    cam_dx = shift[0] * scale_x
                    cam_dy = shift[1] * scale_y
            last_cam = cam_positions.get(frame_no - 1, (0.0, 0.0))
            cam_positions[frame_no] = (last_cam[0] + cam_dx, last_cam[1] + cam_dy)

            if frame_no == 1:
                # Frame 1 Synchronous Initialization: clean spatial sorting (Hen 1, 2, 3...)
                try:
                    res0 = model.predict(frame, verbose=False, conf=0.15, iou=0.35, imgsz=512)
                    raw0 = []
                    if res0 and len(res0) > 0 and res0[0].boxes is not None:
                        bx = res0[0].boxes.xyxy.cpu().numpy()
                        cf = res0[0].boxes.conf.cpu().numpy()
                        for b, c in zip(bx, cf):
                            if c < 0.15: continue
                            if not is_pure_comb(b, frame): continue
                            x1, y1, x2, y2 = map(int, b)
                            raw0.append({
                                "box": (x1, y1, x2, y2),
                                "center": ((x1 + x2) / 2.0, (y1 + y2) / 2.0),
                                "size": (x2 - x1, y2 - y1),
                                "conf": float(c)
                            })
                    dets0 = deduplicate_detections(raw0)
                    dets0.sort(key=lambda d: d["center"][1] * 2.0 + d["center"][0])
                    for det in dets0:
                        num = next_num
                        next_num += 1
                        hens[num] = {
                            "center": det["center"], "lost": 0, "hits": 2,
                            "size": det["size"], "smooth_box": [float(v) for v in det["box"]],
                            "counted": True
                        }
                except Exception:
                    pass
                prev_small_gray = small_gray
                t_stream_start = time.time()
            else:
                # ─── Frame 2+: Ultra-fast LK Optical Flow (1.8 ms) ───
                # Tracks every active hen's head motion on every single frame smoothly at 30 FPS
                if prev_small_gray is not None and len(hens) > 0:
                    active_ids = [n for n, d in hens.items() if d["lost"] <= 5 and d["center"][1] <= (roi_y2 + 25)]
                    if len(active_ids) > 0:
                        pts_small = np.array([[[hens[n]["center"][0] / scale_x, hens[n]["center"][1] / scale_y]] for n in active_ids], dtype=np.float32)
                        new_pts, status, _ = cv2.calcOpticalFlowPyrLK(
                            prev_small_gray, small_gray, pts_small, None,
                            winSize=(19, 19), maxLevel=2,
                            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03)
                        )
                        for idx, num in enumerate(active_ids):
                            if status[idx][0] == 1:
                                nx = float(new_pts[idx][0][0]) * scale_x
                                ny = float(new_pts[idx][0][1]) * scale_y
                                ox, oy = hens[num]["center"]
                                dx = nx - ox
                                dy = ny - oy
                                if abs(dx) < 30 and abs(dy) < 30:
                                    hens[num]["center"] = (nx, ny)
                                    sb = hens[num]["smooth_box"]
                                    hens[num]["smooth_box"] = [sb[0] + dx, sb[1] + dy, sb[2] + dx, sb[3] + dy]
                                    # Active comb check: if head turned away or vanished, mark lost
                                    if frame_no % 3 == 0:
                                        crop = frame[max(0, int(sb[1])):min(frame.shape[0], int(sb[3])),
                                                     max(0, int(sb[0])):min(frame.shape[1], int(sb[2]))]
                                        if crop.size > 0:
                                            hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
                                            m1 = cv2.inRange(hsv, np.array([0, 35, 35]), np.array([16, 255, 255]))
                                            m2 = cv2.inRange(hsv, np.array([150, 35, 35]), np.array([180, 255, 255]))
                                            rr = (cv2.countNonZero(m1) + cv2.countNonZero(m2)) / float(crop.shape[0]*crop.shape[1])
                                            if rr < 0.08:
                                                hens[num]["lost"] += 2
                            else:
                                hens[num]["lost"] += 1
                prev_small_gray = small_gray

                # Check if background AI returned fresh detections
                fresh_ai = None
                fresh_fno = 0
                with ai_lock:
                    if ai_result is not None:
                        fresh_ai = ai_result
                        fresh_fno = ai_result_fno
                        ai_result = None

                if fresh_ai is not None:
                    # Latency motion compensation: advance AI detections from fresh_fno to current frame_no
                    delta_cam_x = cam_positions[frame_no][0] - cam_positions.get(fresh_fno, (0.0, 0.0))[0]
                    delta_cam_y = cam_positions[frame_no][1] - cam_positions.get(fresh_fno, (0.0, 0.0))[1]

                    dets = deduplicate_detections(fresh_ai)
                    for det in dets:
                        bx = det["box"]
                        det["box"] = (bx[0] + delta_cam_x, bx[1] + delta_cam_y, bx[2] + delta_cam_x, bx[3] + delta_cam_y)
                        det["center"] = (det["center"][0] + delta_cam_x, det["center"][1] + delta_cam_y)

                    det_to_hen = {}
                    for d_idx, det in enumerate(dets):
                        best_n, best_d = None, float("inf")
                        for num, data in hens.items():
                            if data["lost"] > 25: continue
                            d = math.hypot(det["center"][0] - data["center"][0], det["center"][1] - data["center"][1])
                            if d <= 90.0 and d < best_d: best_d = d; best_n = num
                        if best_n is not None: det_to_hen[d_idx] = (best_n, best_d)

                    hen_to_det = {}
                    for num, data in hens.items():
                        if data["lost"] > 25: continue
                        best_idx, best_d = None, float("inf")
                        for d_idx, det in enumerate(dets):
                            d = math.hypot(det["center"][0] - data["center"][0], det["center"][1] - data["center"][1])
                            if d <= 90.0 and d < best_d: best_d = d; best_idx = d_idx
                        if best_idx is not None: hen_to_det[num] = (best_idx, best_d)

                    matched = set()
                    used = set()
                    for d_idx, (num, dist) in det_to_hen.items():
                        if num in hen_to_det and hen_to_det[num][0] == d_idx:
                            matched.add(d_idx); used.add(num)
                            det = dets[d_idx]
                            data = hens[num]
                            data["lost"] = 0
                            data["hits"] = data.get("hits", 1) + 1
                            raw = det["box"]
                            sb = data["smooth_box"]
                            data["smooth_box"] = [0.50 * raw[i] + 0.50 * sb[i] for i in range(4)]
                            data["center"] = ((data["smooth_box"][0] + data["smooth_box"][2]) / 2.0, (data["smooth_box"][1] + data["smooth_box"][3]) / 2.0)

                    for d_idx, det in enumerate(dets):
                        if d_idx in matched: continue
                        # Only register new hens if inside the detection zone
                        if not (roi_y1 - 10 <= det["center"][1] <= roi_y2 + 10):
                            continue
                        reassigned = None
                        closest_d = float("inf")
                        for num, data in hens.items():
                            if num in used or data["lost"] > 25: continue
                            d = math.hypot(det["center"][0] - data["center"][0], det["center"][1] - data["center"][1])
                            if d <= 90.0 and d < closest_d: closest_d = d; reassigned = num
                        if reassigned is not None:
                            num = reassigned
                            data = hens[num]
                            data["center"] = det["center"]
                            data["lost"] = 0
                            data["hits"] = data.get("hits", 1) + 1
                            data["smooth_box"] = [float(v) for v in det["box"]]
                        else:
                            num = next_num; next_num += 1
                            hens[num] = {
                                "center": det["center"], "lost": 0, "hits": 2,
                                "size": det["size"], "smooth_box": [float(v) for v in det["box"]],
                                "counted": True
                            }
                        used.add(num)

                # Continuous background AI dispatch: whenever AI is idle, immediately feed next frame
                with ai_lock:
                    if ai_pending is None and fresh_ai is None:
                        ai_pending = frame.copy()
                        ai_pending_fno = frame_no

            # Expire any hens that have exited below the detection zone or bottom of screen
            for num, data in hens.items():
                cy = data["center"][1]
                if cy > (roi_y2 + 25) or cy > (frame.shape[0] - 40):
                    data["lost"] = 999

            total_counted = len([h for h in hens.values() if h.get("hits", 0) >= 2])
            current_total_count = total_counted
            visible_in_zone = len([
                h for h in hens.values()
                if h["lost"] <= 5 and (roi_y1 <= h["center"][1] <= roi_y2)
            ])

            # Fast 720p display rendering & JPEG encoding (6ms total!)
            display = cv2.resize(frame, (1280, 720))
            scale_disp_x = 1280.0 / frame.shape[1]
            scale_disp_y = 720.0 / frame.shape[0]

            r_x1 = int(roi_x1 * scale_disp_x); r_y1 = int(roi_y1 * scale_disp_y)
            r_x2 = int(roi_x2 * scale_disp_x); r_y2 = int(roi_y2 * scale_disp_y)
            cv2.rectangle(display, (r_x1, r_y1), (r_x2, r_y2), (0, 200, 255), 2)
            cv2.putText(display, "REF-TUNED DETECTION ZONE" if ref_settings else "DETECTION ZONE", 
                        (r_x1 + 10, r_y1 + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 200, 255), 2, cv2.LINE_AA)

            for num, data in hens.items():
                if data["lost"] <= 5 and data.get("hits", 0) >= 2:
                    cy = data["center"][1]
                    # NEVER draw outside the detection zone or at the bottom border!
                    if not (roi_y1 <= cy <= roi_y2):
                        continue
                    if cy > (frame.shape[0] - 50):
                        continue

                    sb = data["smooth_box"]
                    x1 = int(sb[0] * scale_disp_x); y1 = int(sb[1] * scale_disp_y)
                    x2 = int(sb[2] * scale_disp_x); y2 = int(sb[3] * scale_disp_y)
                    
                    cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    label = f"HEN {num}"
                    (w_txt, h_txt), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
                    cv2.rectangle(display, (x1, max(y1 - 22, 0)), (x1 + w_txt + 4, max(y1, 22)), (0, 255, 0), -1)
                    cv2.putText(display, label, (x1 + 2, max(y1 - 6, 16)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)
                    cv2.circle(display, (int((x1 + x2) / 2), int((y1 + y2) / 2)), 4, (0, 255, 0), -1)

            time_s = frame_no / fps

            # HUD Telemetry
            hud_w, hud_h = 360, 140
            overlay = display.copy()
            cv2.rectangle(overlay, (15, 15), (15 + hud_w, 15 + hud_h), (15, 23, 42), -1)
            cv2.addWeighted(overlay, 0.75, display, 0.25, 0, display)
            
            cv2.rectangle(display, (15, 15), (15 + hud_w, 15 + hud_h), (16, 185, 129), 2)
            cv2.putText(display, "LIVE POULTRY VISION AI", (28, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (16, 185, 129), 2, cv2.LINE_AA)
            cv2.line(display, (28, 46), (15 + hud_w - 15, 46), (71, 85, 105), 1)
            
            cv2.putText(display, "VISIBLE IN ZONE:", (28, 68), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (148, 163, 184), 1, cv2.LINE_AA)
            cv2.putText(display, f"{visible_in_zone}", (195, 68), cv2.FONT_HERSHEY_SIMPLEX, 0.54, (0, 255, 128), 2, cv2.LINE_AA)
            
            cv2.putText(display, "TOTAL UNIQUE HENS:", (28, 92), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (148, 163, 184), 1, cv2.LINE_AA)
            cv2.putText(display, f"{total_counted}", (195, 92), cv2.FONT_HERSHEY_SIMPLEX, 0.54, (0, 220, 255), 2, cv2.LINE_AA)
            
            cv2.putText(display, "SESSION TIME:", (28, 116), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (148, 163, 184), 1, cv2.LINE_AA)
            cv2.putText(display, f"{time_s:.1f}s", (195, 116), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (241, 245, 249), 2, cv2.LINE_AA)
            
            cv2.putText(display, "TRACKING ENGINE:", (28, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (148, 163, 184), 1, cv2.LINE_AA)
            cv2.putText(display, "HYBRID 30FPS [ACTIVE]", (195, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (16, 185, 129), 2, cv2.LINE_AA)
            
            disp_w = display.shape[1]
            cv2.rectangle(display, (disp_w - 150, 15), (disp_w - 20, 45), (16, 185, 129), -1)
            cv2.putText(display, "[* LIVE AI]", (disp_w - 140, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2, cv2.LINE_AA)
            
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 70]
            ret2, buffer = cv2.imencode('.jpg', display, encode_param)
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                   
            # Pacing to exact video speed (30 FPS normal speed!)
            if not is_live:
                target_time = t_stream_start + (frame_no - 1) * frame_delay
                sleep_time = target_time - time.time()
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    
    finally:
        ai_running = False
        cap.release()


def analyze_reference_video(video_path):
    """Analyze reference video: sample frames, run YOLO, extract average
    detection zone and hen count to tune live camera parameters."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError("Cannot open reference video")
    
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    
    sample_count = min(30, max(5, total_frames // 30))
    sample_interval = max(1, total_frames // sample_count)
    
    all_centers_y = []
    hen_counts_per_frame = []
    all_confs = []
    
    frame_idx = 0
    analyzed = 0
    
    while analyzed < sample_count:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            break
        
        if model is not None:
            results = model.predict(frame, verbose=False, conf=0.25, iou=0.45, imgsz=640)
            if results and results[0].boxes is not None:
                boxes = results[0].boxes.xyxy.cpu().numpy()
                confs = results[0].boxes.conf.cpu().numpy()
                count = 0
                for box, conf in zip(boxes, confs):
                    if conf < 0.25:
                        continue
                    x1, y1, x2, y2 = box
                    cy = (y1 + y2) / 2.0
                    cy_pct = cy / frame_h
                    all_centers_y.append(cy_pct)
                    all_confs.append(float(conf))
                    count += 1
                hen_counts_per_frame.append(count)
        
        frame_idx += sample_interval
        analyzed += 1
    
    cap.release()
    
    if all_centers_y:
        sorted_y = sorted(all_centers_y)
        p5 = sorted_y[max(0, int(len(sorted_y) * 0.05))]
        p95 = sorted_y[min(len(sorted_y)-1, int(len(sorted_y) * 0.95))]
        roi_y1_pct = max(0.05, p5 - 0.10)
        roi_y2_pct = min(0.95, p95 + 0.10)
        avg_conf = sum(all_confs) / len(all_confs)
        learned_conf = max(0.25, min(0.55, avg_conf * 0.85))
    else:
        roi_y1_pct = 0.15
        roi_y2_pct = 0.85
        learned_conf = 0.35
        
    avg_hen_count = int(sum(hen_counts_per_frame) / len(hen_counts_per_frame)) if hen_counts_per_frame else 0
    
    global reference_settings
    reference_settings.update({
        'roi_y1_pct': roi_y1_pct,
        'roi_y2_pct': roi_y2_pct,
        'conf_threshold': learned_conf,
        'avg_hen_count': avg_hen_count
    })
    return True

@app.route('/upload_reference', methods=['POST'])
def upload_reference():
    file = request.files.get('video') or request.files.get('file')
    if not file:
        return jsonify({"success": False, "error": "No file uploaded"}), 400
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    global reference_settings
    try:
        # Analyze it for parameters synchronously (should be relatively fast for small sample)
        analyze_reference_video(filepath)
        reference_settings['reference_video'] = filename
        
        output_filename = filename.replace(".mp4", "_output.mp4").replace(".MP4", "_output.mp4")
        if "_output" not in output_filename:
            output_filename += "_output.mp4"
            
        def background_process_reference():
            try:
                import sys
                if os.path.abspath('backend') not in sys.path:
                    sys.path.append(os.path.abspath('backend'))
                from app.ai.tracking import process_video
                
                # Process the video; this creates filepath_output.mp4
                process_video(filepath)
            except Exception as e:
                import traceback
                traceback.print_exc()
        
        # Run process_video in the background so upload doesn't hang
        threading.Thread(target=background_process_reference).start()
        
        return jsonify({
            "success": True,
            "filename": output_filename,
            "stats": reference_settings,
            "message": "Video uploaded and is processing in the background."
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('video') or request.files.get('file')
    if not file:
        return jsonify({"success": False, "error": "No file uploaded"}), 400
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    return jsonify({"success": True, "filename": filename})

@app.route('/stream/<filename>')
def serve_video(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/start_stream', methods=['POST'])
def start_stream():
    global active_stream
    data = request.get_json() or {}
    video_source = data.get('video_source', 'camera')
    
    if video_source != 'camera':
        video_source = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(video_source))
        if not os.path.exists(video_source):
            return jsonify({"success": False, "error": "Video file not found"}), 404
            
    active_stream = video_source
    return jsonify({"success": True, "active_stream": active_stream})

@app.route('/stop_stream', methods=['POST'])
def stop_stream():
    global active_stream
    active_stream = None
    return jsonify({"success": True})

@app.route('/stream_status', methods=['GET'])
def stream_status():
    global active_stream
    return jsonify({"active": active_stream is not None, "source": active_stream})

@app.route('/stream_video', methods=['GET'])
def stream_video_route():
    global active_stream
    if not active_stream:
        return "No active stream", 404
        
    return Response(_sync_generate_frames(active_stream, reference_settings if reference_settings.get('reference_video') else None),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/get_reference_settings', methods=['GET'])
def get_reference_settings():
    """Return the current reference video settings."""
    return jsonify({
        "has_reference": reference_settings.get('reference_video') is not None,
        "avg_hen_count": reference_settings.get('avg_hen_count', 0),
        "roi_y1_pct": round(reference_settings.get('roi_y1_pct', 0.15), 3),
        "roi_y2_pct": round(reference_settings.get('roi_y2_pct', 0.85), 3),
        "conf_threshold": round(reference_settings.get('conf_threshold', 0.40), 3)
    })


@app.route('/stream/<filename>')
@app.route('/stream_video/<filename>')
def stream_video(filename):
    if filename == 'camera':
        if reference_settings.get('reference_video') is not None:
            return Response(generate_frames_with_ref('camera', reference_settings), mimetype='multipart/x-mixed-replace; boundary=frame')
        return Response(generate_frames('camera'), mimetype='multipart/x-mixed-replace; boundary=frame')
        
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(filepath):
        return "Video not found", 404
    
    # Use reference-tuned streaming if a reference video was previously analyzed
    if reference_settings.get('reference_video') is not None:
        return Response(
            generate_frames_with_ref(filepath, reference_settings),
            mimetype='multipart/x-mixed-replace; boundary=frame'
        )
    
    return Response(generate_frames(filepath), mimetype='multipart/x-mixed-replace; boundary=frame')



import subprocess

processing_status = {}

@app.route('/process_live_video', methods=['POST'])
def process_live_video():
    data = request.get_json() or {}
    filename = data.get('filename')
    if not filename:
        return jsonify({'success': False, 'error': 'No filename provided'})
        
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
    if not os.path.exists(filepath):
        return jsonify({'success': False, 'error': 'File not found'})
        
    processing_status[filename] = 'processing'
    
    def background_process():
        try:
            import sys
            if os.path.abspath('backend') not in sys.path:
                sys.path.append(os.path.abspath('backend'))
            from app.ai.tracking import process_video
            
            process_video(filepath)
            
            output_filename = filename.replace('.mp4', '_output.webm').replace('.MP4', '_output.webm')
            if '_output' not in output_filename:
                 output_filename += '_output.webm'
                 
            processing_status[filename] = {'status': 'done', 'url': '/download/' + output_filename}
        except Exception as e:
            import traceback
            traceback.print_exc()
            processing_status[filename] = {'status': 'error', 'error': str(e)}

    threading.Thread(target=background_process).start()
    return jsonify({'success': True, 'status': 'processing'})

@app.route('/check_process_status/<filename>', methods=['GET'])
def check_process_status(filename):
    status = processing_status.get(filename)
    if not status:
        return jsonify({'status': 'not_found'})
    if isinstance(status, str):
        return jsonify({'status': status})
    return jsonify(status)

@app.route('/download/<filename>')
def download_video(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)


