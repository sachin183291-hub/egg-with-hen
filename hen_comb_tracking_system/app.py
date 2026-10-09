import os
import cv2
import time
import subprocess
from flask import Flask, request, render_template, send_from_directory, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from ultralytics import YOLO

app = Flask(__name__)
CORS(app)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['PROCESSED_FOLDER'] = 'processed'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['PROCESSED_FOLDER'], exist_ok=True)

MODEL_PATH = r'c:\Users\sachi\Downloads\giotag project\backend\best.pt'

if not os.path.exists(MODEL_PATH):
    print(f"Warning: {MODEL_PATH} not found.")
    MODEL_PATH = 'yolov8n.pt' 

try:
    model = YOLO(MODEL_PATH)
except Exception as e:
    print(f"Error loading model: {e}")
    model = None

def process_video_fast(input_path, output_path):
    if model is None:
        raise Exception("Model could not be loaded.")

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise Exception("Error opening video")
        
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps == 0 or fps is None: fps = 30.0
    
    temp_output = output_path + '_temp.mp4'
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(temp_output, fourcc, fps, (width, height))
    
    unique_ids = set()
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
            
        frame_start = time.time()
        
        # Inference at 640 for speed and accuracy balance
        results = model.track(
            frame,
            persist=True,
            tracker="bytetrack.yaml",
            conf=0.15,
            iou=0.45,
            classes=[0],
            verbose=False,
            imgsz=640
        )
        
        visible_hens = 0
        if results[0].boxes is not None and results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            track_ids = results[0].boxes.id.int().cpu().tolist()
            confs = results[0].boxes.conf.cpu().numpy()
            
            for box, track_id, conf in zip(boxes, track_ids, confs):
                x1, y1, x2, y2 = map(int, box)
                unique_ids.add(track_id)
                visible_hens += 1
                
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                label = f"HEN {track_id} ({conf:.2f})"
                cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                
        elapsed = time.time() - frame_start
        ai_fps = 1.0 / elapsed if elapsed > 0 else 0
        
        total_hens = len(unique_ids)
        
        overlay = frame.copy()
        cv2.rectangle(overlay, (10, 10), (380, 140), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

        cv2.putText(frame, f"Visible Hens: {visible_hens}", (20, 45), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        cv2.putText(frame, f"Total Unique Hens: {total_hens}", (20, 85), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        cv2.putText(frame, f"AI FPS: {ai_fps:.1f}", (20, 125), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        
        out.write(frame)
        
    cap.release()
    out.release()
    
    # Convert to H264 for perfect smooth browser playback
    try:
        subprocess.run(
            ['ffmpeg', '-y', '-i', temp_output, '-vcodec', 'libx264', '-crf', '23', output_path], 
            check=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE
        )
        os.remove(temp_output)
    except Exception as e:
        print("FFmpeg conversion failed. Serving original mp4.", e)
        if os.path.exists(output_path):
            os.remove(output_path)
        os.rename(temp_output, output_path)

def gen_frames(input_path):
    if model is None: return
    cap = cv2.VideoCapture(input_path)
    unique_ids = set()
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: break
        
        # Super fast tracking
        results = model.track(frame, persist=True, tracker="bytetrack.yaml", conf=0.15, iou=0.45, classes=[0], verbose=False, imgsz=320)
        
        visible_hens = 0
        if results[0].boxes is not None and results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            track_ids = results[0].boxes.id.int().cpu().tolist()
            confs = results[0].boxes.conf.cpu().numpy()
            
            for box, track_id, conf in zip(boxes, track_ids, confs):
                x1, y1, x2, y2 = map(int, box)
                unique_ids.add(track_id)
                visible_hens += 1
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, f"HEN {track_id}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        total_hens = len(unique_ids)
        overlay = frame.copy()
        cv2.rectangle(overlay, (10, 10), (380, 100), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
        cv2.putText(frame, f"Visible Hens: {visible_hens}", (20, 45), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        cv2.putText(frame, f"Total Unique Hens: {total_hens}", (20, 85), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        
        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
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
        
        return jsonify({
            'success': True,
            'filename': safe_filename
        })

@app.route('/stream_video/<filename>')
def stream_video(filename):
    from flask import Response
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    return Response(gen_frames(input_path), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/processed/<filename>')
def serve_video(filename):
    return send_from_directory(app.config['PROCESSED_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False, port=5000, host='0.0.0.0')
