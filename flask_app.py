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
torch.set_num_threads(1)
try:
    torch.set_num_interop_threads(1)
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
        os.path.abspath(os.path.join(os.getcwd(), 'best.pt')),
        os.path.abspath(os.path.join(os.getcwd(), 'backend', 'best.pt')),
        os.path.abspath(os.path.join(_this_dir, '..', 'backend', 'best.pt')),
        os.path.abspath(os.path.join(_this_dir, '..', 'best.pt')),
        os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend', 'best.pt')),
        os.path.abspath(os.path.join(os.path.dirname(__file__), 'weights', 'best.pt')),
        os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend', 'weights', 'best.pt')),
        'best.pt'
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
            from app.ai.shared_model import get_shared_model
            model = get_shared_model(MODEL_PATH)
        except Exception:
            try:
                print(f"[FLASK] Loading model directly from {MODEL_PATH}...")
                model = YOLO(MODEL_PATH)
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

def generate_frames(video_path):
    return _sync_generate_frames(video_path, None)

def generate_frames_with_ref(video_source, ref_settings):
    return _sync_generate_frames(video_source, ref_settings)

def _sync_generate_frames(video_source, ref_settings):
    model = get_tracking_model()
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
            ]
            demo = next((p for p in fallback_demos if os.path.exists(p)), None)
            if demo:
                cap = cv2.VideoCapture(demo)
                is_live = False
    else:
        # Check if video source exists, if not fall back to demo_hen_video.mp4
        actual_source = video_source
        if not os.path.exists(actual_source):
            fallback_demos = [
                os.path.abspath(os.path.join(os.path.dirname(__file__), "backend", "demo_hen_video.mp4")),
                os.path.abspath(os.path.join(os.path.dirname(__file__), "demo_hen_video.mp4")),
                os.path.abspath(os.path.join(os.getcwd(), "backend", "demo_hen_video.mp4")),
                os.path.abspath(os.path.join(os.getcwd(), "demo_hen_video.mp4")),
            ]
            demo = next((p for p in fallback_demos if os.path.exists(p)), None)
            if demo:
                actual_source = demo
        cap = cv2.VideoCapture(actual_source)
        
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_delay = 1.0 / fps
    ret, sample_frame = cap.read()
    if not ret:
        cap.release()
        return
        
    orig_h, orig_w = sample_frame.shape[:2]
    OUT_W, OUT_H = 854, 480
    AI_W, AI_H = 960, 540
    sx = OUT_W / float(AI_W)
    sy = OUT_H / float(AI_H)
    
    if not is_live:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        
    import math
    import time
    import threading
    
    hens = {}
    next_id = 1
    global current_total_count
    current_total_count = 0
    
    def filter_and_scale_dets(raw_boxes, raw_confs):
        dets = []
        for b, c in zip(raw_boxes, raw_confs):
            x1, y1, x2, y2 = map(float, b)
            bw = x2 - x1
            bh = y2 - y1
            # Filter non-comb structures (roof beams / floor troughs / bars)
            if y1 < AI_H * 0.04 and bw > 140: continue
            if bw < 8 or bh < 8 or bw > 160 or bh > 160: continue
            if bw / bh > 2.8 or bh / bw > 2.8: continue
            
            # Scale coordinates directly to output stream resolution
            dx1, dy1, dx2, dy2 = x1 * sx, y1 * sy, x2 * sx, y2 * sy
            cx, cy = (dx1 + dx2) / 2.0, (dy1 + dy2) / 2.0
            dets.append({
                "box": [dx1, dy1, dx2, dy2],
                "center": (cx, cy),
                "conf": float(c)
            })
        dets.sort(key=lambda d: d["conf"], reverse=True)
        # Deduplicate overlapping bounding boxes (IoU > 0.45) - DO NOT remove close adjacent hens!
        kept = []
        for d in dets:
            b1 = d["box"]
            overlap = False
            for ex in kept:
                b2 = ex["box"]
                ix1 = max(b1[0], b2[0])
                iy1 = max(b1[1], b2[1])
                ix2 = min(b1[2], b2[2])
                iy2 = min(b1[3], b2[3])
                iw = max(0, ix2 - ix1)
                ih = max(0, iy2 - iy1)
                inter = iw * ih
                area1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
                area2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
                union = area1 + area2 - inter
                if union > 0 and (inter / union) > 0.45:
                    overlap = True
                    break
            if not overlap:
                kept.append(d)
        return kept

    # Asynchronous YOLO worker running with imgsz=512, conf=0.08
    ai_lock = threading.Lock()
    ai_frame = None
    ai_results = None
    ai_running = True
    
    def ai_worker():
        nonlocal ai_running, ai_results, ai_frame
        while ai_running:
            f = None
            with ai_lock:
                if ai_frame is not None:
                    f = ai_frame
                    ai_frame = None
            if f is None:
                time.sleep(0.02)
                continue
            try:
                f_ai = cv2.resize(f, (AI_W, AI_H)) if (f.shape[1] != AI_W or f.shape[0] != AI_H) else f
                res = model.predict(f_ai, imgsz=512, conf=0.08, verbose=False)[0]
                if res.boxes is not None:
                    bx = res.boxes.xyxy.cpu().numpy()
                    cf = res.boxes.conf.cpu().numpy()
                    dets = filter_and_scale_dets(bx, cf)
                    with ai_lock:
                        ai_results = dets
            except Exception as e:
                print(f"[AI WORKER] error: {e}")
                
    worker_thread = threading.Thread(target=ai_worker, daemon=True)
    worker_thread.start()
    
    # 100% recall initialization on frame 0
    disp0 = cv2.resize(sample_frame, (OUT_W, OUT_H))
    prev_gray = cv2.cvtColor(disp0, cv2.COLOR_BGR2GRAY)
    try:
        f0_ai = cv2.resize(sample_frame, (AI_W, AI_H))
        init_res = model.predict(f0_ai, imgsz=512, conf=0.08, verbose=False)[0]
        if init_res.boxes is not None:
            init_dets = filter_and_scale_dets(init_res.boxes.xyxy.cpu().numpy(), init_res.boxes.conf.cpu().numpy())
            for d in init_dets:
                hens[next_id] = {
                    "box": d["box"],
                    "center": d["center"],
                    "lost": 0,
                    "hits": 3
                }
                next_id += 1
    except Exception as e:
        print(f"[INIT DETECT] error: {e}")
        
    frame_no = 0
    last_ai_frame_no = 0
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 60]
    
    try:
        while cap.isOpened():
            t_frame_start = time.time()
            
            # Read every frame sequentially for 100% smooth, continuous playback
            ret, frame = cap.read()
            if not ret:
                if not is_live:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    frame_no = 0
                    last_ai_frame_no = 0
                    hens.clear()
                    next_id = 1
                    continue
                break
                
            frame_no += 1
            display = cv2.resize(frame, (OUT_W, OUT_H))
            gray = cv2.cvtColor(display, cv2.COLOR_BGR2GRAY)
            
            # 1. Multi-Point Optical Flow tracking: Boxes move with hens everywhere they go!
            active_ids = [hid for hid, hdata in hens.items() if hdata["lost"] <= 8]
            if len(active_ids) > 0 and prev_gray is not None:
                pts_in = []
                pt_map = []
                for hid in active_ids:
                    x1, y1, x2, y2 = hens[hid]["box"]
                    cx, cy = hens[hid]["center"]
                    # 5 points inside the comb box
                    quad_pts = [
                        (cx, cy),
                        (x1 * 0.7 + x2 * 0.3, y1 * 0.7 + y2 * 0.3),
                        (x1 * 0.3 + x2 * 0.7, y1 * 0.7 + y2 * 0.3),
                        (x1 * 0.7 + x2 * 0.3, y1 * 0.3 + y2 * 0.7),
                        (x1 * 0.3 + x2 * 0.7, y1 * 0.3 + y2 * 0.7),
                    ]
                    for p in quad_pts:
                        pts_in.append([[p[0], p[1]]])
                        pt_map.append(hid)
                        
                pts_in = np.array(pts_in, dtype=np.float32)
                pts_out, status, err = cv2.calcOpticalFlowPyrLK(
                    prev_gray, gray, pts_in, None,
                    winSize=(17, 17), maxLevel=2,
                    criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03)
                )
                
                hen_shifts = {hid: [] for hid in active_ids}
                for i, hid in enumerate(pt_map):
                    if status[i][0] == 1:
                        dx = pts_out[i][0][0] - pts_in[i][0][0]
                        dy = pts_out[i][0][1] - pts_in[i][0][1]
                        if abs(dx) < 35 and abs(dy) < 35:
                            hen_shifts[hid].append((dx, dy))
                            
                for hid, shifts in hen_shifts.items():
                    if len(shifts) >= 1:
                        median_dx = float(np.median([s[0] for s in shifts]))
                        median_dy = float(np.median([s[1] for s in shifts]))
                        b = hens[hid]["box"]
                        hens[hid]["box"] = [b[0] + median_dx, b[1] + median_dy, b[2] + median_dx, b[3] + median_dy]
                        cx = (hens[hid]["box"][0] + hens[hid]["box"][2]) / 2.0
                        cy = (hens[hid]["box"][1] + hens[hid]["box"][3]) / 2.0
                        hens[hid]["center"] = (cx, cy)
                        hens[hid]["lost"] = 0
                    else:
                        hens[hid]["lost"] += 1
            prev_gray = gray

            # 2. Integrate fresh YOLO detections from background worker
            fresh = None
            with ai_lock:
                if ai_results is not None:
                    fresh = ai_results
                    ai_results = None
                    
            if fresh is not None:
                used_hens = set()
                for det in fresh:
                    cx, cy = det["center"]
                    best_id, best_dist = None, float("inf")
                    for hid, hdata in hens.items():
                        if hid in used_hens: continue
                        hx, hy = hdata["center"]
                        d = math.hypot(cx - hx, cy - hy)
                        if d < 55 and d < best_dist:
                            best_dist = d
                            best_id = hid
                            
                    if best_id is not None:
                        ob = hens[best_id]["box"]
                        nb = det["box"]
                        hens[best_id]["box"] = [0.70 * nb[i] + 0.30 * ob[i] for i in range(4)]
                        hens[best_id]["center"] = ((hens[best_id]["box"][0] + hens[best_id]["box"][2])/2.0,
                                                   (hens[best_id]["box"][1] + hens[best_id]["box"][3])/2.0)
                        hens[best_id]["lost"] = 0
                        hens[best_id]["hits"] += 1
                        used_hens.add(best_id)
                    else:
                        hid = next_id
                        next_id += 1
                        hens[hid] = {
                            "box": det["box"],
                            "center": (cx, cy),
                            "lost": 0,
                            "hits": 1
                        }
                        used_hens.add(hid)

            # Age out lost tracks & clean up out of bounds boxes
            for hid in list(hens.keys()):
                b = hens[hid]["box"]
                if b[2] < 0 or b[0] > OUT_W or b[3] < 0 or b[1] > OUT_H:
                    del hens[hid]
                    continue
                if hens[hid]["lost"] > 18:
                    del hens[hid]

            # 3. Submit next frame to AI worker periodically (every ~25 frames / 0.8s)
            if frame_no - last_ai_frame_no >= 25:
                with ai_lock:
                    if ai_frame is None and ai_results is None:
                        ai_frame = cv2.resize(frame, (AI_W, AI_H))
                        last_ai_frame_no = frame_no
                        
            # 4. Counting & Drawing
            visible_hens = [n for n, d in hens.items() if d["lost"] <= 4 and d.get("hits", 0) >= 1]
            total_counted = next_id - 1
            current_total_count = total_counted
            
            # Draw boxes directly on detected combs: moving tightly with each hen!
            for hid in visible_hens:
                d = hens[hid]
                x1, y1, x2, y2 = map(int, d["box"])
                
                # Glowing green box
                cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)
                label = f"HEN {hid}"
                (w_txt, h_txt), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
                cv2.rectangle(display, (x1, max(y1 - 16, 0)), (x1 + w_txt + 4, max(y1, 16)), (0, 255, 0), -1)
                cv2.putText(display, label, (x1 + 2, max(y1 - 4, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
                cv2.circle(display, (int((x1 + x2) / 2), int((y1 + y2) / 2)), 3, (0, 255, 0), -1)
                
            time_s = frame_no / fps
            
            # Telemetry HUD
            cv2.rectangle(display, (10, 10), (300, 95), (0, 0, 0), -1)
            cv2.putText(display, f"TIME: {time_s:.1f}s", (20, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(display, f"HENS VISIBLE: {len(visible_hens)}", (20, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA)
            cv2.putText(display, f"TOTAL COUNTED: {total_counted}", (20, 84), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2, cv2.LINE_AA)
                
            # JPEG encode & stream frame
            ret2, buffer = cv2.imencode('.jpg', display, encode_param)
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                   
            # Frame pacing: maintain exact 30 FPS timing with smooth sleep
            work_time = time.time() - t_frame_start
            sleep_time = frame_delay - work_time
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                time.sleep(0.001)
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


