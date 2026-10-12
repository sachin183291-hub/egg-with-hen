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
torch.set_num_threads(2)
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
        roi_y1 = int(frame_h * ref_settings.get('roi_y1_pct', 0.10))
        roi_x2 = frame_w
        roi_y2 = int(frame_h * ref_settings.get('roi_y2_pct', 0.88))
        learned_conf = ref_settings.get('conf_threshold', 0.35)
        avg_ref_hens = ref_settings.get('avg_hen_count', 0)
    else:
        roi_x1 = 0
        roi_y1 = int(frame_h * 0.10)
        roi_x2 = frame_w
        roi_y2 = int(frame_h * 0.88)
        learned_conf = 0.25
        avg_ref_hens = 0
        
    if not is_live:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        
    import math
    import time
    hens = {}
    next_num = 1
    total_counted = 0
    
    global current_total_count
    current_total_count = 0
    
    frame_no = 0
    
    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                if not is_live:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    frame_no = 0
                    hens.clear()
                    next_num = 1
                    continue
                break
                
            frame_no += 1
            
            # Direct YOLO comb/head detection on frame
            results = model.predict(frame, verbose=False, conf=0.08, iou=0.45, imgsz=480)
            raw_dets = []
            if results and results[0].boxes is not None:
                boxes = results[0].boxes.xyxy.cpu().numpy()
                confs = results[0].boxes.conf.cpu().numpy()
                for box, conf in zip(boxes, confs):
                    if conf < 0.10: continue
                    x1, y1, x2, y2 = map(int, box)
                    w, h = x2 - x1, y2 - y1
                    if w <= 8 or h <= 8: continue
                    if w > 175 or h > 175: continue # Exclude whole hen body boxes
                    raw_dets.append({
                        "box": (x1, y1, x2, y2),
                        "center": ((x1 + x2) / 2.0, (y1 + y2) / 2.0),
                        "size": (w, h),
                        "conf": float(conf)
                    })
                    
            raw_dets.sort(key=lambda d: d["conf"], reverse=True)
            detections = []
            for d in raw_dets:
                is_duplicate = False
                for fd in detections:
                    if math.hypot(d["center"][0] - fd["center"][0], d["center"][1] - fd["center"][1]) < 45:
                        is_duplicate = True
                        break
                if not is_duplicate:
                    detections.append(d)
                    
            for num in hens:
                hens[num]["lost"] += 1
                
            used = set()
            for det in detections:
                cx, cy = det["center"]
                best_num, best_dist = None, float("inf")
                for num, data in hens.items():
                    if num in used or data["lost"] > 30: continue
                    hx, hy = data["center"]
                    d = math.hypot(cx - hx, cy - hy)
                    if d <= 130 and d < best_dist:
                        best_dist = d
                        best_num = num
                        
                if best_num is not None:
                    num = best_num
                    hens[num]["center"] = (cx, cy)
                    hens[num]["box"] = det["box"]
                    hens[num]["lost"] = 0
                    hens[num]["hits"] += 1
                else:
                    num = next_num
                    next_num += 1
                    hens[num] = {
                        "center": (cx, cy),
                        "box": det["box"],
                        "lost": 0,
                        "hits": 1
                    }
                used.add(num)
                det["num"] = num
                
            # Accurately count all unique hens verified in at least 2 frames
            verified_hens = [n for n, d in hens.items() if d.get("hits", 0) >= 2]
            total_counted = max(len(verified_hens), len(detections))
            current_total_count = total_counted
            visible_in_zone = len(detections)
            
            display = frame.copy()
            
            # Draw detection zone
            cv2.rectangle(display, (roi_x1, roi_y1), (roi_x2, roi_y2), (0, 200, 255), 2)
            cv2.putText(display, "REF-TUNED DETECTION ZONE" if ref_settings else "DETECTION ZONE",
                        (roi_x1 + 10, roi_y1 + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 200, 255), 2, cv2.LINE_AA)
                        
            # Draw boxes directly on detected combs: locked tightly to each moving comb!
            for det in detections:
                num = det["num"]
                x1, y1, x2, y2 = det["box"]
                
                cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)
                label = f"HEN {num}"
                (w_txt, h_txt), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
                cv2.rectangle(display, (x1, max(y1 - 22, 0)), (x1 + w_txt + 4, max(y1, 22)), (0, 255, 0), -1)
                cv2.putText(display, label, (x1 + 2, max(y1 - 6, 16)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)
                cv2.circle(display, (int((x1 + x2) / 2), int((y1 + y2) / 2)), 4, (0, 255, 0), -1)
                
            time_s = frame_no / fps
            
            # Telemetry HUD
            cv2.rectangle(display, (10, 10), (380, 130), (0, 0, 0), -1)
            cv2.putText(display, f"TIME: {time_s:.1f}s", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(display, f"HENS VISIBLE: {visible_in_zone}", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2, cv2.LINE_AA)
            cv2.putText(display, f"TOTAL UNIQUE HENS: {total_counted}", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2, cv2.LINE_AA)
            if ref_settings:
                ref_label = f"REF CONF:{learned_conf:.2f} | REF AVG:{avg_ref_hens} hens"
                cv2.putText(display, ref_label, (20, 125), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (200, 200, 0), 1, cv2.LINE_AA)
                
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 70]
            ret2, buffer = cv2.imencode('.jpg', display, encode_param)
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.01)
    finally:
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


