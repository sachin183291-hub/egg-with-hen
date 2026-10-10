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

# 1. Use the trained HEN_COMB YOLO model
MODEL_PATH = '/content/gdrive/MyDrive/Poultry_AI_Project/HEN_COMB_1280_TRAINING/hen_comb_1280_100ep/weights/best.pt'
if not os.path.exists(MODEL_PATH):
    local_fallback = os.path.join('backend', 'best.pt')
    if os.path.exists(local_fallback):
        MODEL_PATH = local_fallback
    elif os.path.exists('yolov8n.pt'):
        MODEL_PATH = 'yolov8n.pt'

print(f"Loading YOLO model from {MODEL_PATH}...")
device = "cuda" if torch.cuda.is_available() else "cpu"
try:
    model = YOLO(MODEL_PATH)
except Exception as e:
    print(f"Error loading model: {e}")
    model = None

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
        cap = cv2.VideoCapture(0)
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
    hens = {}
    next_num = 1
    EMA = 0.4
    total_counted = 0
    frame_no = 0
    
    start_time = time.time()
    
    last_frame_no = 0
    while cap.isOpened():
        if not is_live:
            elapsed_time = time.time() - start_time
            target_frame = int(elapsed_time * fps)
            
            if target_frame < frame_no:
                time.sleep((frame_no - target_frame) / fps)
            elif target_frame > frame_no:
                skip_frames = target_frame - frame_no
                for _ in range(skip_frames):
                    cap.grab()
                frame_no = target_frame
                
        ret, frame = cap.read()
        if not ret: break
        
        frame_delta = frame_no - last_frame_no
        if frame_delta == 0: frame_delta = 1
        last_frame_no = frame_no
        frame_no += 1
        
        detections = []
        # Use predict because track breaks when skipping frames
        results = model.predict(frame, verbose=False, conf=0.1, iou=0.45, imgsz=416)
        
        if results and results[0].boxes is not None:
                boxes = results[0].boxes.xyxy.cpu().numpy()
                confs = results[0].boxes.conf.cpu().numpy()
                tids = [None] * len(boxes)
                
                raw_dets = []
                for box, conf, tid in zip(boxes, confs, tids):
                    if conf < 0.15: continue # Increased from 0.10 to 0.15 to filter noise
                    x1, y1, x2, y2 = map(int, box)
                    w, h = x2 - x1, y2 - y1
                    if w <= 0 or h <= 0: continue
                    # Size filter: Disabled to ensure bounding boxes show up for all video scales
                    # if w > 150 or h > 150: continue 
                    
                    raw_dets.append({
                        "box": (x1, y1, x2, y2),
                        "center": ((x1+x2)/2.0, (y1+y2)/2.0),
                        "size": (w, h),
                        "tid": tid,
                        "conf": float(conf)
                    })
                
                # Custom Distance-based NMS to prevent double boxes and new ID creation
                raw_dets.sort(key=lambda d: d["conf"], reverse=True)
                filtered_dets = []
                for d in raw_dets:
                    is_duplicate = False
                    for fd in filtered_dets:
                        dist = math.hypot(d["center"][0] - fd["center"][0], d["center"][1] - fd["center"][1])
                        if dist < 80: # INCREASED from 40 to 80 to merge fragmented boxes of the same hen!
                            is_duplicate = True
                            break
                    if not is_duplicate:
                        filtered_dets.append(d)
                        
                detections = filtered_dets
                
        for num in hens:
            hens[num]["lost"] += frame_delta
            
        used = set()
        detections.sort(key=lambda d: d["conf"], reverse=True)
        
        for det in detections:
            center = det["center"]
            raw = det["box"]
            tid = det["tid"]
            asgn = None
            
            if tid is not None:
                for num, data in hens.items():
                    if num in used: continue
                    if data["tid"] == tid and data["lost"] <= 45: # Max lost frames reduced to 45
                        asgn = num; break
                        
            if asgn is None:
                best_d, best_n = float("inf"), None
                for num, data in hens.items():
                    if num in used or data["lost"] > 45: continue # Max lost frames reduced to 45
                    cx, cy = data["center"]
                    vx, vy = data["vel"]
                    lost = data["lost"]
                    px = cx + vx * min(lost, 10)
                    py = cy + vy * min(lost, 10)
                    d = math.hypot(center[0]-px, center[1]-py)
                    if d <= min(200, 100 + lost*5) and d < best_d: # Max distance reduced from 400 to 200
                        best_d, best_n = d, num
                if best_n is not None:
                    asgn = best_n
                    
            if asgn is None:
                asgn = next_num; next_num += 1
                hens[asgn] = {
                    "center": center, "vel": (0,0), "tid": tid,
                    "lost": 0, "size": det["size"],
                    "smooth_box": [float(v) for v in raw],
                    "counted": False
                }
            else:
                data = hens[asgn]
                old_cx, old_cy = data["center"]
                total_lost = max(1, data["lost"])
                nvx = (center[0] - old_cx) / total_lost
                nvy = (center[1] - old_cy) / total_lost
                ovx, ovy = data["vel"]
                data["center"] = center
                data["vel"] = (0.7*ovx + 0.3*nvx, 0.7*ovy + 0.3*nvy)
                data["tid"] = tid
                data["lost"] = 0
                data["size"] = det["size"]
                sb = data["smooth_box"]
                data["smooth_box"] = [EMA*raw[i] + (1-EMA)*sb[i] for i in range(4)]
                
            used.add(asgn)
            det["num"] = asgn
            
            if roi_x1 <= center[0] <= roi_x2 and roi_y1 <= center[1] <= roi_y2:
                if not hens[asgn].get("counted", False):
                    hens[asgn]["counted"] = True
                    total_counted += 1
                    
        # EXACT box drawing logic from analyze_video.py!
        display = frame.copy()
        visible_in_zone = 0
        
        cv2.rectangle(display, (roi_x1, roi_y1), (roi_x2, roi_y2), (0, 200, 255), 2)
        cv2.putText(display, "REF-TUNED DETECTION ZONE" if ref_settings else "DETECTION ZONE", 
                    (roi_x1 + 10, roi_y1 + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 200, 255), 2, cv2.LINE_AA)
                    
        for det in detections:
            num = det["num"]
            sb = hens[num]["smooth_box"]
            x1, y1, x2, y2 = int(sb[0]), int(sb[1]), int(sb[2]), int(sb[3])
            
            if roi_x1 <= (x1+x2)/2 <= roi_x2 and roi_y1 <= (y1+y2)/2 <= roi_y2:
                visible_in_zone += 1
                
            cv2.rectangle(display, (x1,y1), (x2,y2), (0,255,0), 2)
            label = f"HEN {num}"
            (w_txt, h_txt), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
            cv2.rectangle(display, (x1, max(y1 - 22, 0)), (x1 + w_txt, max(y1, 22)), (0, 255, 0), -1)
            cv2.putText(display, label, (x1, max(y1-6, 16)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)
            cv2.circle(display, (int((sb[0]+sb[2])/2), int((sb[1]+sb[3])/2)), 4, (0,255,0), -1)
            
        for num, data in hens.items():
            if num not in used and 0 < data["lost"] <= 45:
                lost = data["lost"]
                vx, vy = data["vel"]
                sb = data.get("smooth_box")
                if sb:
                    pcx = (sb[0]+sb[2])/2 + vx*min(lost,15)
                    pcy = (sb[1]+sb[3])/2 + vy*min(lost,15)
                    bw = sb[2]-sb[0]; bh = sb[3]-sb[1]
                else:
                    cx, cy = data["center"]
                    pcx = cx + vx*min(lost,15)
                    pcy = cy + vy*min(lost,15)
                    bw, bh = data.get("size", (60,60))
                    
                if roi_x1 <= pcx <= roi_x2 and roi_y1 <= pcy <= roi_y2:
                    visible_in_zone += 1
                    
                x1 = int(pcx - bw/2); y1 = int(pcy - bh/2)
                x2 = int(pcx + bw/2); y2 = int(pcy + bh/2)
                
                # If lost is small, draw it exactly like a normal detection to prevent visual flickering
                if lost <= 10:
                    cv2.rectangle(display, (x1,y1), (x2,y2), (0,255,0), 2)
                    label = f"HEN {num}"
                    (w_txt, h_txt), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
                    cv2.rectangle(display, (x1, max(y1 - 22, 0)), (x1 + w_txt, max(y1, 22)), (0, 255, 0), -1)
                    cv2.putText(display, label, (x1, max(y1-6, 16)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)
                    cv2.circle(display, (int((sb[0]+sb[2])/2) if sb else int(pcx), int((sb[1]+sb[3])/2) if sb else int(pcy)), 4, (0,255,0), -1)
                else:
                    # Fade out if lost for a long time
                    fade = int(255 * max(0.2, 1.0 - lost/60.0))
                    cv2.rectangle(display, (x1,y1), (x2,y2), (0,fade,255), 1)
                    label = f"HEN {num}"
                    cv2.putText(display, label, (x1, max(y1-6, 16)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, fade, 255), 1)
                
        time_s = frame_no / fps
        cv2.rectangle(display, (10, 10), (380, 130), (0, 0, 0), -1)
        cv2.putText(display, f"TIME: {time_s:.1f}s", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(display, f"HENS IN ZONE: {visible_in_zone}", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2, cv2.LINE_AA)
        cv2.putText(display, f"TOTAL COUNT: {total_counted}", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2, cv2.LINE_AA)
        
        if ref_settings:
            ref_label = f"REF CONF:{learned_conf:.2f} | REF AVG:{avg_ref_hens} hens"
            cv2.putText(display, ref_label, (20, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 0), 1, cv2.LINE_AA)
            
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 65]
        ret2, buffer = cv2.imencode('.jpg', display, encode_param)
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
               
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


