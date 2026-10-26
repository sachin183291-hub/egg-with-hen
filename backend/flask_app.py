import os
import math
import uuid
import time
import json
from flask import Flask, request, render_template_string, jsonify, Response, send_from_directory
from werkzeug.utils import secure_filename
from flask_cors import CORS
import cv2
if hasattr(cv2, 'setNumThreads'):
    cv2.setNumThreads(2)
if os.name == 'nt':
    try:
        import ctypes
        ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception:
        pass

import torch
cpu_cores = os.cpu_count() or 4
torch.set_num_threads(min(8, max(2, cpu_cores - 2)))
try:
    torch.set_num_interop_threads(2)
except Exception:
    pass
import numpy as np
from ultralytics import YOLO

app = Flask(__name__)
CORS(app)
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Global reference video settings (learned from uploaded reference video)
reference_settings = {
    'roi_y1_pct': 0.10,
    'roi_y2_pct': 0.88,
    'conf_threshold': 0.35,
    'avg_hen_count': 0,
    'reference_video': None
}

current_total_count = 0
current_live_count = 0
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
    is_cuda = torch.cuda.is_available()
    if is_cuda:
        possible_paths = [
            os.path.join(_this_dir, 'backend', 'best.pt'),
            os.path.join(_this_dir, 'best.pt'),
            'best.pt',
            os.path.join(_this_dir, 'backend', 'best.onnx'),
            os.path.join(_this_dir, 'best.onnx'),
            'best.onnx',
        ]
    else:
        possible_paths = [
            os.path.join(_this_dir, 'backend', 'best.onnx'),
            os.path.join(_this_dir, 'best.onnx'),
            'best.onnx',
            os.path.join(_this_dir, 'backend', 'best.pt'),
            os.path.join(_this_dir, 'best.pt'),
            'best.pt',
        ]
    for p in possible_paths:
        if os.path.exists(p):
            MODEL_PATH = p
            break
    else:
        nano_paths = [
            os.path.join(_this_dir, 'backend', 'yolov8n.pt'),
            os.path.join(_this_dir, 'yolov8n.pt'),
            os.path.abspath(os.path.join(os.getcwd(), 'yolov8n.pt')),
            'yolov8n.pt'
        ]
        MODEL_PATH = next((p for p in nano_paths if os.path.exists(p)), 'yolov8n.pt')

model = None

def get_tracking_model():
    global model
    if model is None:
        try:
            import sys
            b_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend'))
            if b_dir not in sys.path:
                sys.path.insert(0, b_dir)
            from app.ai.shared_model import get_shared_model
            model = get_shared_model(MODEL_PATH)
        except Exception:
            try:
                print(f"[FLASK] Loading model directly from {MODEL_PATH}...")
                model = YOLO(MODEL_PATH, task="detect") if MODEL_PATH.endswith(".onnx") else YOLO(MODEL_PATH)
                dummy = np.zeros((352, 352, 3), dtype=np.uint8)
                model.predict(dummy, imgsz=352, conf=0.1, verbose=False)
            except Exception as e:
                print(f"[FLASK] Error loading model: {e}")
                model = None
    return model

CONF_THRESHOLD = 0.25
IOU_THRESHOLD = 0.45
MAX_LOST_FRAMES = 180
BASE_MATCH_DISTANCE = 180
MAX_FAST_MATCH_DISTANCE = 400

def center_of(box):
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)

import threading

active_stream_session_id = 0

def generate_frames(video_path):
    return _sync_generate_frames(video_path, None)

def generate_frames_with_ref(video_source, ref_settings):
    return _sync_generate_frames(video_source, ref_settings)

def _sync_generate_frames(video_source, ref_settings=None):
    global current_total_count, current_live_count, active_stream_session_id
    import math
    import time
    import threading
    from pathlib import Path

    active_stream_session_id += 1
    my_session_id = active_stream_session_id
    current_total_count = 0
    current_live_count = 0

    active_model = get_tracking_model()
    is_live = video_source == 'camera' or str(video_source) == '0'
    if is_live:
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW) if os.name == 'nt' else cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened() or os.environ.get("RENDER") == "true":
            fallback_demos = [
                os.path.abspath(os.path.join(os.path.dirname(__file__), "backend", "demo_hen_video.mp4")),
                os.path.abspath(os.path.join(os.path.dirname(__file__), "demo_hen_video.mp4")),
                os.path.abspath(os.path.join(os.getcwd(), "backend", "demo_hen_video.mp4")),
                os.path.abspath(os.path.join(os.getcwd(), "demo_hen_video.mp4")),
                os.path.abspath(os.path.join(os.path.dirname(__file__), "reference_video.mp4")),
                os.path.abspath(os.path.join(os.getcwd(), "reference_video.mp4")),
            ]
            demo = next((p for p in fallback_demos if os.path.exists(p)), None)
            if demo:
                cap = cv2.VideoCapture(demo)
                is_live = False
    else:
        actual_source = str(video_source)
        if not os.path.exists(actual_source):
            fallback_demos = [
                os.path.abspath(os.path.join(os.path.dirname(__file__), "backend", "demo_hen_video.mp4")),
                os.path.abspath(os.path.join(os.path.dirname(__file__), "demo_hen_video.mp4")),
                os.path.abspath(os.path.join(os.getcwd(), "backend", "demo_hen_video.mp4")),
                os.path.abspath(os.path.join(os.getcwd(), "demo_hen_video.mp4")),
                os.path.abspath(os.path.join(os.path.dirname(__file__), "reference_video.mp4")),
                os.path.abspath(os.path.join(os.getcwd(), "reference_video.mp4")),
            ]
            demo = next((p for p in fallback_demos if os.path.exists(p)), None)
            if demo:
                actual_source = demo

        cap = cv2.VideoCapture(actual_source)

    if not cap.isOpened():
        print(f"[TRACKER ERROR] Could not open video source: {video_source}")
        return

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) if not is_live else 0
    raw_fps = cap.get(cv2.CAP_PROP_FPS)
    try:
        src_fps = float(raw_fps)
        if src_fps <= 0 or src_fps > 120 or src_fps != src_fps:
            src_fps = 30.0
    except Exception:
        src_fps = 30.0

    # True 1.0x Real-Time Normal Speed: exactly matching source recording FPS!
    if is_live:
        fps = min(30.0, max(20.0, float(src_fps)))
    else:
        fps = float(src_fps)
        if fps <= 0 or fps > 60:
            fps = 30.0
    frame_interval = 1.0 / fps

    ret, sample_frame = cap.read()
    if not ret:
        cap.release()
        return

    orig_h, orig_w = sample_frame.shape[:2]
    if orig_w >= orig_h:
        OUT_W = 640
        OUT_H = int(640 * (orig_h / float(orig_w))) // 2 * 2
    else:
        OUT_H = 640
        OUT_W = int(640 * (orig_w / float(orig_h))) // 2 * 2
    OUT_W = max(320, OUT_W)
    OUT_H = max(240, OUT_H)

    # Optical flow grid matched to aspect ratio
    SW = 160
    SH = int(160 * (OUT_H / float(OUT_W))) // 2 * 2
    scale_x = OUT_W / float(SW)
    scale_y = OUT_H / float(SH)

    def compute_iou(b1, b2):
        ix1, iy1 = max(b1[0], b2[0]), max(b1[1], b2[1])
        ix2, iy2 = min(b1[2], b2[2]), min(b1[3], b2[3])
        iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
        inter = iw * ih
        if inter <= 0:
            return 0.0
        a1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
        a2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
        u = a1 + a2 - inter
        return inter / u if u > 0 else 0.0

    # ─── COMB DETECTION ZONE: Dynamic bounds covering the entire cage inspection area
    if orig_w < orig_h:
        # Portrait (mobile phone video along cage aisle) - covers cages & entire feeding trough
        ZONE_X1_PCT = 0.01
        ZONE_Y1_PCT = 0.03
        ZONE_X2_PCT = 0.88
        ZONE_Y2_PCT = 0.98
    else:
        # Landscape (wide camera / drone / battery cage overview)
        ZONE_X1_PCT = 0.02
        ZONE_Y1_PCT = 0.04
        ZONE_X2_PCT = 0.98
        ZONE_Y2_PCT = 0.96

    if ref_settings:
        if ref_settings.get('roi_y1_pct'):
            ZONE_Y1_PCT = float(ref_settings['roi_y1_pct'])
        if ref_settings.get('roi_y2_pct'):
            ZONE_Y2_PCT = float(ref_settings['roi_y2_pct'])
        if ref_settings.get('roi_x1_pct'):
            ZONE_X1_PCT = float(ref_settings['roi_x1_pct'])
        if ref_settings.get('roi_x2_pct'):
            ZONE_X2_PCT = float(ref_settings['roi_x2_pct'])

    ZONE_X1 = int(OUT_W * ZONE_X1_PCT)
    ZONE_Y1 = int(OUT_H * ZONE_Y1_PCT)
    ZONE_X2 = int(OUT_W * ZONE_X2_PCT)
    ZONE_Y2 = int(OUT_H * ZONE_Y2_PCT)

    def is_in_zone(cx, cy):
        """Check if a comb center point is strictly inside the detection zone."""
        return ZONE_X1 <= cx <= ZONE_X2 and ZONE_Y1 <= cy <= ZONE_Y2

    MAX_COMB_W = 180   # Maximum width for hen HEAD/COMB only (scaled for display)
    MAX_COMB_H = 180   # Maximum height for hen HEAD/COMB only (scaled for display)
    MIN_COMB_SZ = 4    # Minimum comb size (captures all hen combs clearly)
    MATCH_RADIUS = 42.0  # Stable radius for cage compartments
    NEW_HEN_MIN_DIST = 22.0  # Allows adjacent hens in cage compartments without suppression
    MAX_LOST_MEMORY = 25  # Frame memory for lost hens before retirement

    def extract_combs(f_img, conf_thresh=0.03, imgsz=352):
        if active_model is None:
            return []
        try:
            in_h, in_w = f_img.shape[:2]
            scale_x_det = OUT_W / float(in_w)
            scale_y_det = OUT_H / float(in_h)

            res = active_model.predict(f_img, imgsz=imgsz, conf=conf_thresh, iou=0.40, verbose=False)[0]
            if res.boxes is None or len(res.boxes) == 0:
                return []

            hsv = cv2.cvtColor(f_img, cv2.COLOR_BGR2HSV)
            h_ch, s_ch, v_ch = cv2.split(hsv)
            b_ch, g_ch, r_ch = cv2.split(f_img.astype(np.float32))

            comb_mask = (
                (((h_ch >= 150) | (h_ch <= 15)) & (s_ch > 32) & (v_ch > 40) & ((r_ch - g_ch) > 12)) |
                (((r_ch - np.maximum(g_ch, b_ch)) > 15) & (s_ch > 30) & (v_ch > 45))
            )

            candidates = []
            bx = res.boxes.xyxy.cpu().numpy()
            cf = res.boxes.conf.cpu().numpy()
            for b, c in zip(bx, cf):
                conf = float(c)
                orig_x1 = max(0, min(in_w - 1, int(float(b[0]))))
                orig_y1 = max(0, min(in_h - 1, int(float(b[1]))))
                orig_x2 = max(0, min(in_w - 1, int(float(b[2]))))
                orig_y2 = max(0, min(in_h - 1, int(float(b[3]))))

                crop = comb_mask[orig_y1:orig_y2, orig_x1:orig_x2]
                if np.count_nonzero(crop) < 12:
                    continue

                ys, xs = np.where(crop)
                if len(xs) < 8:
                    continue

                cx = (orig_x1 + float(np.median(xs))) * scale_x_det
                cy = (orig_y1 + float(np.median(ys))) * scale_y_det

                if cy <= 6 or not is_in_zone(cx, cy):
                    continue

                w_comb = (np.percentile(xs, 90) - np.percentile(xs, 10)) * scale_x_det
                h_comb = (np.percentile(ys, 90) - np.percentile(ys, 10)) * scale_y_det
                base_sz = max(26.0, min(38.0, max(w_comb, h_comb) + 6.0))
                hw, hh = base_sz / 2.0, base_sz / 2.0
                candidates.append({
                    "box": [cx - hw, cy - hh, cx + hw, cy + hh],
                    "center": (cx, cy),
                    "conf": conf
                })

            candidates.sort(key=lambda d: d["conf"], reverse=True)
            dedup = []
            for d in candidates:
                if not any(math.hypot(d["center"][0] - ex["center"][0], d["center"][1] - ex["center"][1]) < 22 for ex in dedup):
                    dedup.append(d)
            return dedup
        except Exception:
            return []

    # Frame 0: Seed only hens strictly inside the detection zone using crisp full-frame
    disp0 = cv2.resize(sample_frame, (OUT_W, OUT_H), interpolation=cv2.INTER_LINEAR)
    hens = {}
    next_id = 1
    try:
        init_dets = extract_combs(sample_frame, conf_thresh=0.03, imgsz=640)
        init_in_zone = [d for d in init_dets if is_in_zone(d["center"][0], d["center"][1])]
        if OUT_W < OUT_H:
            init_in_zone.sort(key=lambda d: -d["center"][1])
        else:
            init_in_zone.sort(key=lambda d: (d["center"][1] // 40, d["center"][0]))
        for d in init_in_zone:
            hid = next_id
            next_id += 1
            hens[hid] = {
                "box": list(d["box"]),
                "center": d["center"],
                "lost": 0,
                "hits": 3
            }
    except Exception as e:
        print(f"[TRACKER Frame 0 Note] {e}")

    current_total_count = max(0, next_id - 1)
    current_live_count = len(hens)

    # Enable 1ms high-precision timer on Windows so video NEVER stutters or drops frames
    import ctypes
    if hasattr(ctypes, 'windll'):
        try:
            ctypes.windll.winmm.timeBeginPeriod(1)
        except Exception:
            pass

    # Background AI worker running continuously at 352 for ultra-fast response (< 100ms)
    ai_lock = threading.Lock()
    ai_frame = None
    ai_results = None
    ai_running = True

    def ai_worker_proc():
        nonlocal ai_frame, ai_results, ai_running
        while ai_running and active_stream_session_id == my_session_id:
            img_to_run = None
            with ai_lock:
                if ai_frame is not None:
                    img_to_run = ai_frame
                    ai_frame = None
            if img_to_run is None:
                time.sleep(0.005)
                continue
            try:
                fresh_dets = extract_combs(img_to_run, conf_thresh=0.03, imgsz=352)
                with ai_lock:
                    ai_results = fresh_dets
            except Exception:
                pass

    ai_worker_thread = threading.Thread(target=ai_worker_proc, daemon=True)
    ai_worker_thread.start()

    f_idx = 0
    step_no = 0
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 65]
    prev_gray = cv2.cvtColor(disp0, cv2.COLOR_BGR2GRAY)
    start_wall = None

    try:
        while cap.isOpened():
            if active_stream_session_id != my_session_id:
                print(f"[STREAM] Stream #{my_session_id} superseded by #{active_stream_session_id}, exiting.")
                break

            if start_wall is None:
                start_wall = time.time()

            t_frame_start = time.time()

            ret, frame = cap.read()
            if not ret:
                print(f"[STREAM COMPLETED] Video completed 1 full pass ({f_idx} frames). Final Total Count: {current_total_count}")
                try:
                    if 'frame_bytes' in locals() and frame_bytes:
                        for _ in range(25):
                            if active_stream_session_id != my_session_id:
                                break
                            time.sleep(0.1)
                            yield (b'--frame\r\n'
                                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                except Exception:
                    pass
                break

            f_idx += 1
            step_no += 1

            display = cv2.resize(frame, (OUT_W, OUT_H), interpolation=cv2.INTER_LINEAR)
            gray = cv2.cvtColor(display, cv2.COLOR_BGR2GRAY)

            # 1. Multi-point Lucas-Kanade Optical Flow on active hen heads inside zone
            active_ids = [hid for hid, h in hens.items() if h["lost"] <= 8 and is_in_zone(*h["center"])]
            if len(active_ids) > 0 and prev_gray is not None:
                pts_in = []
                pt_map = []
                for hid in active_ids:
                    x1, y1, x2, y2 = hens[hid]["box"]
                    cx, cy = hens[hid]["center"]
                    bw, bh = x2 - x1, y2 - y1
                    quad_pts = [
                        (cx, cy),
                        (cx - bw * 0.22, cy - bh * 0.22),
                        (cx + bw * 0.22, cy - bh * 0.22),
                        (cx - bw * 0.22, cy + bh * 0.22),
                        (cx + bw * 0.22, cy + bh * 0.22),
                    ]
                    for p in quad_pts:
                        pts_in.append([[p[0], p[1]]])
                        pt_map.append(hid)

                pts_in_arr = np.array(pts_in, dtype=np.float32)
                pts_out, status, _ = cv2.calcOpticalFlowPyrLK(
                    prev_gray, gray, pts_in_arr, None,
                    winSize=(21, 21), maxLevel=3,
                    criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 12, 0.03)
                )

                hen_shifts = {hid: [] for hid in active_ids}
                for i, hid in enumerate(pt_map):
                    if status[i][0] == 1:
                        dx = float(pts_out[i][0][0] - pts_in_arr[i][0][0])
                        dy = float(pts_out[i][0][1] - pts_in_arr[i][0][1])
                        if abs(dx) < 18 and abs(dy) < 18:
                            hen_shifts[hid].append((dx, dy))

                for hid, shifts in hen_shifts.items():
                    if len(shifts) >= 1:
                        mdx = float(np.median([s[0] for s in shifts]))
                        mdy = float(np.median([s[1] for s in shifts]))
                        b = hens[hid]["box"]
                        hens[hid]["box"] = [b[0] + mdx, b[1] + mdy, b[2] + mdx, b[3] + mdy]
                        hens[hid]["center"] = (
                            (hens[hid]["box"][0] + hens[hid]["box"][2]) / 2.0,
                            (hens[hid]["box"][1] + hens[hid]["box"][3]) / 2.0
                        )
                    else:
                        hens[hid]["lost"] += 1

            prev_gray = gray

            # 2. Integrate fresh YOLO comb detections from background worker
            fresh = None
            with ai_lock:
                if ai_results is not None:
                    fresh = ai_results
                    ai_results = None

            if fresh is not None:
                matched_dets = set()
                used_hens = set()

                cands = []
                for d_idx, d in enumerate(fresh):
                    dcx, dcy = d["center"]
                    for hid, h in hens.items():
                        if h["lost"] > 25:
                            continue
                        hx, hy = h["center"]
                        dist = math.hypot(dcx - hx, dcy - hy)
                        iou = compute_iou(d["box"], h["box"])
                        if dist <= 42.0 or iou > 0.15:
                            cost = (1.0 - iou) * 0.4 + (dist / 42.0) * 0.6
                            cands.append((cost, d_idx, hid))

                cands.sort(key=lambda x: x[0])
                for cost, d_idx, hid in cands:
                    if d_idx in matched_dets or hid in used_hens:
                        continue
                    matched_dets.add(d_idx)
                    used_hens.add(hid)
                    d = fresh[d_idx]
                    nb = d["box"]
                    ob = hens[hid]["box"]
                    hens[hid]["box"] = [
                        0.35 * nb[0] + 0.65 * ob[0],
                        0.35 * nb[1] + 0.65 * ob[1],
                        0.35 * nb[2] + 0.65 * ob[2],
                        0.35 * nb[3] + 0.65 * ob[3],
                    ]
                    hens[hid]["center"] = (
                        (hens[hid]["box"][0] + hens[hid]["box"][2]) / 2.0,
                        (hens[hid]["box"][1] + hens[hid]["box"][3]) / 2.0
                    )
                    hens[hid]["lost"] = 0
                    hens[hid]["hits"] += 1

                for hid in hens:
                    if hid not in used_hens:
                        hens[hid]["lost"] += 1

                # Stage 2: Register New Hens entering the zone (Brand new sequential ID, NEVER reused)
                for d_idx, d in enumerate(fresh):
                    if d_idx in matched_dets:
                        continue
                    dcx, dcy = d["center"]
                    if not is_in_zone(dcx, dcy):
                        continue

                    is_near = any(
                        math.hypot(dcx - h["center"][0], dcy - h["center"][1]) < 25.0 or compute_iou(d["box"], h["box"]) > 0.25
                        for h in hens.values() if h["lost"] <= 25
                    )
                    if not is_near:
                        hid = next_id
                        next_id += 1
                        hens[hid] = {
                            "box": list(d["box"]),
                            "center": d["center"],
                            "lost": 0,
                            "hits": 1
                        }

            # 3. Dispatch current crisp frame to AI worker
            with ai_lock:
                if ai_frame is None:
                    ai_frame = frame.copy()

            # 4. Immediate retirement: when a hen leaves the zone or is lost, remove its box immediately!
            for hid in list(hens.keys()):
                b = hens[hid]["box"]
                cx, cy = hens[hid]["center"]
                out_of_screen = (b[2] < -10 or b[0] > OUT_W + 10 or b[3] < -10 or b[1] > OUT_H + 10)
                out_of_zone = not is_in_zone(cx, cy)
                lost_too_long = hens[hid]["lost"] > 15
                if out_of_screen or out_of_zone or lost_too_long:
                    del hens[hid]

            # 5. Visible hens: actively detected/tracked strictly inside the detection zone
            render_hens = [
                hid for hid, h in hens.items()
                if h["lost"] <= 8 and is_in_zone(*h["center"])
            ]
            
            # Sort for stable rendering order
            render_hens.sort(key=lambda hid: hid)

            current_live_count = len(render_hens)
            current_total_count = max(0, next_id - 1)

            # ─── DRAW DETECTION ZONE (Visual boundary & exterior dimming) ───
            zone_overlay = display.copy()
            cv2.rectangle(zone_overlay, (0, 0), (OUT_W, ZONE_Y1), (0, 0, 0), -1)
            cv2.rectangle(zone_overlay, (0, ZONE_Y2), (OUT_W, OUT_H), (0, 0, 0), -1)
            cv2.rectangle(zone_overlay, (0, ZONE_Y1), (ZONE_X1, ZONE_Y2), (0, 0, 0), -1)
            cv2.rectangle(zone_overlay, (ZONE_X2, ZONE_Y1), (OUT_W, ZONE_Y2), (0, 0, 0), -1)
            cv2.addWeighted(zone_overlay, 0.25, display, 0.75, 0, display)

            # Zone yellow border & label
            cv2.rectangle(display, (ZONE_X1, ZONE_Y1), (ZONE_X2, ZONE_Y2), (0, 240, 255), 2)
            cv2.putText(display, "DETECTION ZONE", (ZONE_X1 + 6, ZONE_Y1 + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 240, 255), 1, cv2.LINE_AA)

            # Render Hen Head Bounding Boxes with permanent unique sequential IDs
            for hid in render_hens:
                disp_b = hens[hid]["box"]
                x1, y1, x2, y2 = map(int, disp_b)
                x1 = max(0, min(OUT_W - 1, x1))
                y1 = max(0, min(OUT_H - 1, y1))
                x2 = max(0, min(OUT_W - 1, x2))
                y2 = max(0, min(OUT_H - 1, y2))
                bw, bh = x2 - x1, y2 - y1
                if bw < 4 or bh < 4:
                    continue

                cx_dot = (x1 + x2) // 2
                cy_dot = (y1 + y2) // 2

                # 1. Glowing green box outline
                cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)

                # 2. White corner brackets
                c_len = max(5, int(min(bw, bh) * 0.28))
                for px, py, dx, dy in [(x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)]:
                    cv2.line(display, (px, py), (px + dx * c_len, py), (255, 255, 255), 2, cv2.LINE_AA)
                    cv2.line(display, (px, py), (px + dy * c_len), (255, 255, 255), 2, cv2.LINE_AA)

                # 3. Center target reticle dot
                cv2.circle(display, (cx_dot, cy_dot), 3, (0, 255, 0), -1)
                cv2.circle(display, (cx_dot, cy_dot), 1, (255, 255, 255), -1)

                # 4. Solid green badge Hen #{hid} (PERMANENT UNIQUE ID, NEVER REPEATS!)
                lbl_text = f"Hen #{hid}"
                (tw, th), _ = cv2.getTextSize(lbl_text, cv2.FONT_HERSHEY_SIMPLEX, 0.40, 1)
                badge_y1 = max(0, y1 - th - 6)
                badge_y2 = y1
                badge_x1 = x1
                badge_x2 = min(OUT_W - 1, x1 + tw + 8)
                cv2.rectangle(display, (badge_x1, badge_y1), (badge_x2, badge_y2), (0, 255, 0), -1)
                cv2.putText(display, lbl_text, (badge_x1 + 4, badge_y2 - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 0, 0), 1, cv2.LINE_AA)

            # Top-Left Telemetry HUD (smooth continuous time display)
            time_s = (f_idx / fps) if fps > 0 else 0.0
            total_sec = (total_frames / fps) if (total_frames and fps > 0) else 5.0
            cv2.rectangle(display, (8, 12), (195, 74), (0, 0, 0), -1)
            cv2.rectangle(display, (8, 12), (195, 74), (0, 255, 0), 1)
            cv2.putText(display, f"TIME: {time_s:.1f}s / {total_sec:.1f}s", (14, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (220, 220, 220), 1, cv2.LINE_AA)
            cv2.putText(display, f"LIVE HENS: {current_live_count}", (14, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 128), 1, cv2.LINE_AA)
            cv2.putText(display, f"TOTAL COUNTED: {current_total_count}", (14, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 235, 255), 2, cv2.LINE_AA)

            ret2, buffer = cv2.imencode('.jpg', display, encode_param)
            frame_bytes = buffer.tobytes()

            if not is_live:
                work_time = time.time() - t_frame_start
                sleep_time = frame_interval - work_time
                if sleep_time > 0.001:
                    time.sleep(sleep_time)
                else:
                    time.sleep(0.001)

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    finally:
        ai_running = False
        cap.release()
        if hasattr(ctypes, 'windll'):
            try:
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass

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
@app.route('/api/tracker/upload', methods=['POST'])
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

@app.route('/stream_count', methods=['GET'])
@app.route('/api/tracker/stream_count', methods=['GET'])
def get_stream_count():
    global current_total_count, current_live_count
    return jsonify({
        "success": True,
        "count": current_total_count,
        "live_count": current_live_count
    })

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
@app.route('/api/tracker/stream_video/<filename>')
def stream_video(filename):
    if filename == 'camera':
        if reference_settings.get('reference_video') is not None:
            return Response(generate_frames_with_ref('camera', reference_settings), mimetype='multipart/x-mixed-replace; boundary=frame')
        return Response(generate_frames('camera'), mimetype='multipart/x-mixed-replace; boundary=frame')
        
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(filepath):
        possible = [
            os.path.abspath(os.path.join(os.path.dirname(__file__), "backend", filename)),
            os.path.abspath(os.path.join(os.path.dirname(__file__), filename)),
            os.path.abspath(os.path.join(os.getcwd(), "backend", filename)),
            os.path.abspath(os.path.join(os.getcwd(), filename)),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "uploads", filename)),
        ]
        found = next((p for p in possible if os.path.exists(p)), None)
        if found:
            filepath = found
        else:
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

_flask_live_tracker = None

@app.route('/live_frame', methods=['POST'])
@app.route('/api/tracker/live_frame', methods=['POST'])
def flask_live_frame():
    global _flask_live_tracker
    try:
        if 'frame' not in request.files:
            return jsonify({"success": False, "error": "No frame file uploaded"}), 400
        
        file = request.files['frame']
        frame_number = int(request.form.get('frame_number', 0))
        video_time = float(request.form.get('video_time', 0.0))
        
        if _flask_live_tracker is None:
            import sys
            b_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend'))
            if b_dir not in sys.path:
                sys.path.insert(0, b_dir)
            from app.ai.optical_tracker import OpticalHenTracker
            _flask_live_tracker = OpticalHenTracker(MODEL_PATH)
            
        raw = file.read()
        np_arr = np.frombuffer(raw, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if img is None:
            return jsonify({"success": False, "error": "Cannot decode frame"}), 400
            
        res = _flask_live_tracker.process_live_frame(img, frame_number, video_time)
        return jsonify(res)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/reset', methods=['POST'])
@app.route('/api/tracker/reset', methods=['POST'])
def flask_reset():
    global _flask_live_tracker
    if _flask_live_tracker is not None:
        _flask_live_tracker.reset_state()
    return jsonify({"success": True})

if __name__ == '__main__':
    import socket
    target_port = int(os.environ.get('PORT', 5000))
    if target_port == 5000:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if s.connect_ex(('127.0.0.1', 5000)) == 0:
            target_port = 5001
        s.close()
    print(f"Starting GioTag Flask AI Tracking Server on port {target_port}...")
    app.run(host='0.0.0.0', port=target_port, debug=False)


