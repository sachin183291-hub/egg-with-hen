import os
import cv2
import time
import math
import subprocess
from flask import Flask, request, render_template, send_from_directory, jsonify, Response
from flask_cors import CORS
from werkzeug.utils import secure_filename
from ultralytics import YOLO

app = Flask(__name__)
CORS(app)
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['PROCESSED_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'processed')

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['PROCESSED_FOLDER'], exist_ok=True)

# 1. Load the user's trained HEN_COMB YOLO model
MODEL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend', 'best.pt'))
if not os.path.exists(MODEL_PATH):
    possible_paths = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'best.pt')),
        os.path.abspath(os.path.join(os.getcwd(), 'backend', 'best.pt')),
        os.path.abspath(os.path.join(os.getcwd(), 'best.pt')),
        'best.pt'
    ]
    for p in possible_paths:
        if os.path.exists(p):
            MODEL_PATH = p
            break

print(f"[POULTRY TRACKER] Loading model from: {MODEL_PATH}")
try:
    model = YOLO(MODEL_PATH)
except Exception as e:
    print(f"Error loading model: {e}")
    model = None


def extract_comb_detections(res, frame_w, frame_h):
    """
    Extract strictly tiny hen comb bounding boxes from YOLO predictions.
    Filters out any whole hen bodies or multi-hen clusters (e.g. 150-350px boxes).
    """
    if res.boxes is None or len(res.boxes) == 0:
        return []
        
    bx = res.boxes.xyxy.cpu().numpy()
    cf = res.boxes.conf.cpu().numpy()
    
    max_comb_w = int(frame_w * 0.09) if frame_w > 900 else int(frame_w * 0.10)
    max_comb_h = int(frame_h * 0.15) if frame_h > 900 else int(frame_h * 0.16)
    max_area = max_comb_w * max_comb_h
    
    raw_combs = []
    for b, c in zip(bx, cf):
        if c < 0.12:
            continue
        w = b[2] - b[0]
        h = b[3] - b[1]
        # Comb only: discard whole hen bodies and clusters
        if w <= max_comb_w and h <= max_comb_h and (w * h) <= max_area and w >= 6 and h >= 6:
            cx = (b[0] + b[2]) / 2.0
            cy = (b[1] + b[3]) / 2.0
            raw_combs.append({
                'box': [int(b[0]), int(b[1]), int(b[2]), int(b[3])],
                'center': (cx, cy),
                'conf': float(c),
                'size': (w, h)
            })
            
    # Deduplicate overlapping boxes on the same comb
    raw_combs.sort(key=lambda d: d['conf'], reverse=True)
    kept_combs = []
    for d in raw_combs:
        dup = False
        for kd in kept_combs:
            dist = math.hypot(d['center'][0] - kd['center'][0], d['center'][1] - kd['center'][1])
            if dist < 22.0:
                dup = True
                break
        if not dup:
            kept_combs.append(d)
            
    return kept_combs


def process_video_fast(input_path, output_path):
    """
    Process video with ByteTrack velocity momentum and permanent Hen numbering.
    Combines strict comb detection, stable ID persistence across head movements,
    and H.264 video rendering for seamless web playback.
    """
    if model is None:
        raise Exception("Model could not be loaded.")

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise Exception("Error opening video")
        
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0 or fps is None or math.isnan(fps):
        fps = 30.0
    
    temp_output = output_path + '_temp.mp4'
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(temp_output, fourcc, fps, (width, height))
    
    hens = {}
    next_id = 1
    all_unique_ids = set()
    reach_radius = 110.0 if width > 900 else 65.0
    frame_no = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        frame_no += 1
        frame_start = time.time()
        
        # Inference with user's best.pt
        res = model(frame, conf=0.12, imgsz=640, verbose=False)[0]
        combs = extract_comb_detections(res, width, height)
        
        matched_dets = set()
        used_hens = set()
        
        # Velocity-guided spatial matching
        cands = []
        for d_idx, det in enumerate(combs):
            cx, cy = det['center']
            for hid, hdata in hens.items():
                if hdata['lost'] > 150:  # 5-second persistence across occlusions & head dips
                    continue
                hx, hy = hdata['center']
                vx, vy = hdata.get('vel', (0.0, 0.0))
                pred_hx, pred_hy = hx + vx, hy + vy
                d_last = math.hypot(cx - hx, cy - hy)
                d_pred = math.hypot(cx - pred_hx, cy - pred_hy)
                eff_dist = min(d_last, d_pred)
                if eff_dist <= reach_radius:
                    cands.append((eff_dist, d_idx, hid))
                    
        cands.sort(key=lambda x: x[0])
        for dist, d_idx, hid in cands:
            if d_idx in matched_dets or hid in used_hens:
                continue
            matched_dets.add(d_idx)
            used_hens.add(hid)
            det = combs[d_idx]
            old_cx, old_cy = hens[hid]['center']
            new_cx, new_cy = det['center']
            raw_vx = max(-35.0, min(35.0, new_cx - old_cx))
            raw_vy = max(-35.0, min(35.0, new_cy - old_cy))
            ovx, ovy = hens[hid].get('vel', (0.0, 0.0))
            hens[hid]['vel'] = (0.6 * raw_vx + 0.4 * ovx, 0.6 * raw_vy + 0.4 * ovy)
            hens[hid]['center'] = (new_cx, new_cy)
            hens[hid]['box'] = list(det['box'])
            hens[hid]['lost'] = 0
            hens[hid]['hits'] += 1
            det['hen_id'] = hid

        for hid, hdata in hens.items():
            if hid not in used_hens:
                hdata['lost'] += 1

        # Truly new hen gating (must be distinct from all known hens)
        for d_idx, det in enumerate(combs):
            if d_idx in matched_dets:
                continue
            cx, cy = det['center']
            far = all(math.hypot(cx - h['center'][0], cy - h['center'][1]) > reach_radius * 1.1 for h in hens.values())
            if far:
                hid = next_id
                next_id += 1
                hens[hid] = {'center': (cx, cy), 'box': list(det['box']), 'vel': (0.0, 0.0), 'lost': 0, 'hits': 1}
                all_unique_ids.add(hid)
                used_hens.add(hid)
                det['hen_id'] = hid

        # Draw comb boxes & badges
        visible_hens = 0
        for det in combs:
            hid = det.get('hen_id')
            if not hid:
                continue
            x1, y1, x2, y2 = det['box']
            visible_hens += 1
            
            # Glowing green comb box
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            
            # Viewfinder corner brackets
            c_len = max(4, min(8, int(min(x2 - x1, y2 - y1) * 0.35)))
            cv2.line(frame, (x1, y1), (x1 + c_len, y1), (255, 255, 255), 2)
            cv2.line(frame, (x1, y1), (x1, y1 + c_len), (255, 255, 255), 2)
            cv2.line(frame, (x2, y1), (x2 - c_len, y1), (255, 255, 255), 2)
            cv2.line(frame, (x2, y1), (x2, y1 + c_len), (255, 255, 255), 2)
            cv2.line(frame, (x1, y2), (x1 + c_len, y2), (255, 255, 255), 2)
            cv2.line(frame, (x1, y2), (x1, y2 - c_len), (255, 255, 255), 2)
            cv2.line(frame, (x2, y2), (x2 - c_len, y2), (255, 255, 255), 2)
            cv2.line(frame, (x2, y2), (x2, y2 - c_len), (255, 255, 255), 2)
            
            # Center comb dot
            cx_dot, cy_dot = int((x1 + x2) / 2), int((y1 + y2) / 2)
            cv2.circle(frame, (cx_dot, cy_dot), 3, (0, 255, 0), -1)
            
            # Hen badge: Hen 1, Hen 2...
            label = f"Hen {hid}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            badge_y = max(y1 - 18, 0)
            cv2.rectangle(frame, (x1, badge_y), (x1 + tw + 6, badge_y + 16), (0, 255, 0), -1)
            cv2.putText(frame, label, (x1 + 3, badge_y + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
            
        elapsed = time.time() - frame_start
        ai_fps = 1.0 / elapsed if elapsed > 0 else 0
        total_hens = len(all_unique_ids)
        
        # Telemetry HUD
        overlay = frame.copy()
        cv2.rectangle(overlay, (15, 15), (340, 125), (10, 15, 22), -1)
        cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)
        cv2.rectangle(frame, (15, 15), (340, 125), (0, 255, 128), 1)

        cv2.putText(frame, f"VISIBLE COMBS: {visible_hens}", (28, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2, cv2.LINE_AA)
        cv2.putText(frame, f"TOTAL UNIQUE HENS: {total_hens}", (28, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(frame, f"AI INFERENCE FPS: {ai_fps:.1f}", (28, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1, cv2.LINE_AA)
        
        out.write(frame)
        
    cap.release()
    out.release()
    
    # Convert to H.264 for perfect smooth browser playback
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run(
            [ffmpeg_exe, '-y', '-i', temp_output, '-vcodec', 'libx264', '-pix_fmt', 'yuv420p', '-preset', 'fast', '-crf', '22', output_path], 
            check=True, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL
        )
        if os.path.exists(temp_output):
            os.remove(temp_output)
    except Exception as e:
        print("FFmpeg conversion fallback notice:", e)
        if os.path.exists(output_path):
            os.remove(output_path)
        os.rename(temp_output, output_path)

    return len(all_unique_ids)


def gen_frames(input_path):
    """
    Live streaming generator with strict comb filtering and persistent hen IDs.
    """
    if model is None:
        return
    cap = cv2.VideoCapture(input_path)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
    reach_radius = 110.0 if width > 900 else 65.0
    
    hens = {}
    next_id = 1
    all_unique_ids = set()
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
            
        t_start = time.time()
        res = model(frame, conf=0.12, imgsz=640, verbose=False)[0]
        combs = extract_comb_detections(res, width, height)
        
        matched_dets = set()
        used_hens = set()
        
        cands = []
        for d_idx, det in enumerate(combs):
            cx, cy = det['center']
            for hid, hdata in hens.items():
                if hdata['lost'] > 150:
                    continue
                hx, hy = hdata['center']
                vx, vy = hdata.get('vel', (0.0, 0.0))
                pred_hx, pred_hy = hx + vx, hy + vy
                eff_dist = min(math.hypot(cx - hx, cy - hy), math.hypot(cx - pred_hx, cy - pred_hy))
                if eff_dist <= reach_radius:
                    cands.append((eff_dist, d_idx, hid))
                    
        cands.sort(key=lambda x: x[0])
        for dist, d_idx, hid in cands:
            if d_idx in matched_dets or hid in used_hens:
                continue
            matched_dets.add(d_idx)
            used_hens.add(hid)
            det = combs[d_idx]
            new_cx, new_cy = det['center']
            old_cx, old_cy = hens[hid]['center']
            raw_vx = max(-35.0, min(35.0, new_cx - old_cx))
            raw_vy = max(-35.0, min(35.0, new_cy - old_cy))
            ovx, ovy = hens[hid].get('vel', (0.0, 0.0))
            hens[hid]['vel'] = (0.6 * raw_vx + 0.4 * ovx, 0.6 * raw_vy + 0.4 * ovy)
            hens[hid]['center'] = (new_cx, new_cy)
            hens[hid]['box'] = list(det['box'])
            hens[hid]['lost'] = 0
            hens[hid]['hits'] += 1
            det['hen_id'] = hid

        for hid, hdata in hens.items():
            if hid not in used_hens:
                hdata['lost'] += 1

        for d_idx, det in enumerate(combs):
            if d_idx in matched_dets:
                continue
            cx, cy = det['center']
            far = all(math.hypot(cx - h['center'][0], cy - h['center'][1]) > reach_radius * 1.1 for h in hens.values())
            if far:
                hid = next_id
                next_id += 1
                hens[hid] = {'center': (cx, cy), 'box': list(det['box']), 'vel': (0.0, 0.0), 'lost': 0, 'hits': 1}
                all_unique_ids.add(hid)
                used_hens.add(hid)
                det['hen_id'] = hid

        visible_hens = 0
        for det in combs:
            hid = det.get('hen_id')
            if not hid:
                continue
            visible_hens += 1
            x1, y1, x2, y2 = det['box']
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = f"Hen {hid}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            badge_y = max(y1 - 18, 0)
            cv2.rectangle(frame, (x1, badge_y), (x1 + tw + 6, badge_y + 16), (0, 255, 0), -1)
            cv2.putText(frame, label, (x1 + 3, badge_y + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
            
        elapsed = time.time() - t_start
        ai_fps = 1.0 / elapsed if elapsed > 0 else 0
        
        # Overlay
        overlay = frame.copy()
        cv2.rectangle(overlay, (15, 15), (340, 115), (10, 15, 22), -1)
        cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)
        cv2.rectangle(frame, (15, 15), (340, 115), (0, 255, 128), 1)

        cv2.putText(frame, f"VISIBLE COMBS: {visible_hens}", (28, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2, cv2.LINE_AA)
        cv2.putText(frame, f"TOTAL UNIQUE HENS: {len(all_unique_ids)}", (28, 78), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(frame, f"AI FPS: {ai_fps:.1f}", (28, 104), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1, cv2.LINE_AA)
        
        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        frame_bytes = buffer.tobytes()
        
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
               
    cap.release()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_video():
    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400
    
    file = request.files['video']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    if file:
        filename = secure_filename(file.filename)
        timestamp = str(int(time.time()))
        safe_filename = f"{timestamp}_{filename}"
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
        file.save(input_path)
        
        output_filename = f"tracked_{safe_filename}"
        output_path = os.path.join(app.config['PROCESSED_FOLDER'], output_filename)
        
        try:
            total_hens = process_video_fast(input_path, output_path)
            return jsonify({
                'success': True,
                'filename': safe_filename,
                'video_url': f'/processed/{output_filename}',
                'total_hens': total_hens
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/stream_video/<filename>')
def stream_video(filename):
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
    if not os.path.exists(input_path):
        return "Video not found", 404
    return Response(gen_frames(input_path), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/processed/<filename>')
def serve_video(filename):
    return send_from_directory(app.config['PROCESSED_FOLDER'], secure_filename(filename))


if __name__ == '__main__':
    app.run(debug=False, use_reloader=False, port=5000, host='0.0.0.0')
