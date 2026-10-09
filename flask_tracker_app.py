import os
import cv2
import time
import math
import numpy as np
from flask import Flask, request, render_template_string, send_from_directory, jsonify
from ultralytics import YOLO
import subprocess

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 1. Use the requested trained model
# The prompt mentions: /content/gdrive/MyDrive/.../best.pt
# Since we are running locally on Windows, we will use the local best.pt 
# with a fallback to the path mentioned in the prompt.
LOCAL_MODEL = "best.pt"
COLAB_MODEL = "/content/gdrive/MyDrive/Poultry_AI_Project/HEN_COMB_1280_TRAINING/hen_comb_1280_100ep/weights/best.pt"
model_path = LOCAL_MODEL if os.path.exists(LOCAL_MODEL) else COLAB_MODEL

print(f"Loading model from: {model_path}")
try:
    model = YOLO(model_path)
except Exception as e:
    print(f"Warning: Could not load model {model_path}. Please ensure it exists.")
    model = None

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HEN_COMB Tracker</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #121212; color: #ffffff; margin: 0; padding: 20px; text-align: center; }
        .container { max-width: 800px; margin: 0 auto; background: #1e1e1e; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.5); }
        h1 { color: #4ade80; }
        .upload-btn { background: #4ade80; color: #000; padding: 10px 20px; border: none; font-size: 16px; font-weight: bold; cursor: pointer; border-radius: 5px; }
        .upload-btn:hover { background: #22c55e; }
        video { width: 100%; max-width: 800px; border-radius: 5px; border: 2px solid #4ade80; margin-top: 20px; }
        #status { margin-top: 20px; font-weight: bold; color: #fbbf24; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Poultry HEN_COMB Real-Time Tracking</h1>
        <p>Upload a video to process with YOLO & ByteTrack</p>
        
        <form id="uploadForm" enctype="multipart/form-data">
            <input type="file" id="videoFile" name="video" accept="video/mp4,video/x-m4v,video/*" required />
            <button type="submit" class="upload-btn">Upload & Track</button>
        </form>
        
        <div id="status"></div>
        <div id="videoContainer" style="display: none;">
            <video id="resultVideo" controls autoplay loop>
                <source src="" type="video/mp4">
                Your browser does not support the video tag.
            </video>
        </div>
    </div>

    <script>
        document.getElementById('uploadForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const fileInput = document.getElementById('videoFile');
            if (fileInput.files.length === 0) return;
            
            const formData = new FormData();
            formData.append('video', fileInput.files[0]);
            
            document.getElementById('status').innerText = 'Processing video... Please wait. This may take a while depending on video length.';
            document.getElementById('videoContainer').style.display = 'none';
            document.getElementById('resultVideo').src = '';
            
            try {
                const response = await fetch('/process', {
                    method: 'POST',
                    body: formData
                });
                
                const result = await response.json();
                
                if (result.success) {
                    document.getElementById('status').innerText = 'Processing complete! Total unique hens tracked: ' + result.total_hens;
                    const videoUrl = '/uploads/' + result.filename;
                    
                    const videoPlayer = document.getElementById('resultVideo');
                    videoPlayer.src = videoUrl;
                    document.getElementById('videoContainer').style.display = 'block';
                    videoPlayer.load();
                } else {
                    document.getElementById('status').innerText = 'Error: ' + result.error;
                }
            } catch (error) {
                document.getElementById('status').innerText = 'Error processing video.';
                console.error(error);
            }
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/process', methods=['POST'])
def process_video():
    if 'video' not in request.files:
        return jsonify({"success": False, "error": "No video uploaded"})
        
    file = request.files['video']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"})

    input_filename = f"input_{int(time.time())}.mp4"
    input_path = os.path.join(UPLOAD_FOLDER, input_filename)
    file.save(input_path)
    
    output_filename = f"output_{int(time.time())}.mp4"
    output_path = os.path.join(UPLOAD_FOLDER, output_filename)
    
    # Process video with tracker
    try:
        total_hens = run_tracker(input_path, output_path)
        
        # Browsers require H264 encoded MP4 to play in the <video> tag. 
        # OpenCV's default mp4v creates an MPEG-4 video which fails to play on web.
        # We use ffmpeg to quickly convert the output for browser compatibility.
        web_output_filename = f"web_{output_filename}"
        web_output_path = os.path.join(UPLOAD_FOLDER, web_output_filename)
        
        subprocess.run([
            "ffmpeg", "-y", "-i", output_path, 
            "-vcodec", "libx264", "-f", "mp4", web_output_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Cleanup intermediate files to save space
        if os.path.exists(web_output_path):
            os.remove(input_path)
            os.remove(output_path)
            final_served_file = web_output_filename
        else:
            final_served_file = output_filename
            
        return jsonify({"success": True, "filename": final_served_file, "total_hens": total_hens})
        
    except Exception as e:
        print(f"Error during processing: {e}")
        return jsonify({"success": False, "error": str(e)})

@app.route('/uploads/<filename>')
def serve_video(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


def run_tracker(input_video_path, output_video_path):
    cap = cv2.VideoCapture(input_video_path)
    if not cap.isOpened():
        raise RuntimeError("Failed to open uploaded video.")
        
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0: fps = 30.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_video_path, fourcc, fps, (w, h))
    
    hens = {}
    next_hen_id = 1
    EMA = 0.5  # Smoothing factor
    frame_no = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        frame_no += 1
        t0 = time.perf_counter()
        
        # 7, 12, 13: YOLO object detection + ByteTrack on every frame
        # Only class 0 (HEN_COMB), Conf = 0.15, IoU = 0.45
        results = model.track(
            frame, 
            persist=True, 
            verbose=False,
            conf=0.15, 
            iou=0.45,
            classes=[0] 
        )
        
        elapsed = time.perf_counter() - t0
        detections = []
        
        if results and results[0].boxes is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            confs = results[0].boxes.conf.cpu().numpy()
            tids = (results[0].boxes.id.int().cpu().tolist() if results[0].boxes.id is not None else [None] * len(boxes))
            
            for box, conf, tid in zip(boxes, confs, tids):
                x1, y1, x2, y2 = map(int, box)
                detections.append({
                    "box": (x1, y1, x2, y2),
                    "center": ((x1+x2)/2.0, (y1+y2)/2.0),
                    "size": (x2-x1, y2-y1),
                    "tid": tid,
                    "conf": float(conf)
                })
        
        # 10, 11: Stable permanent numbering & prediction logic
        for num in hens:
            hens[num]["lost"] += 1
            
        used_ids = set()
        detections.sort(key=lambda d: d["conf"], reverse=True)
        
        for det in detections:
            center = det["center"]
            raw_box = det["box"]
            tid = det["tid"]
            assigned_num = None
            
            # Match by ByteTrack ID first
            if tid is not None:
                for num, data in hens.items():
                    if num in used_ids: continue
                    if data["tid"] == tid and data["lost"] <= 150:
                        assigned_num = num
                        break
                        
            # Distance based matching as fallback (if tracker loses identity briefly)
            if assigned_num is None:
                best_dist, best_num = float("inf"), None
                for num, data in hens.items():
                    if num in used_ids or data["lost"] > 150: continue
                    cx, cy = data["center"]
                    vx, vy = data["vel"]
                    lost = data["lost"]
                    
                    # Predict position
                    px = cx + vx * min(lost, 15)
                    py = cy + vy * min(lost, 15)
                    
                    dist = math.hypot(center[0]-px, center[1]-py)
                    if dist <= min(300, 100 + lost * 5) and dist < best_dist:
                        best_dist, best_num = dist, num
                        
                if best_num is not None:
                    assigned_num = best_num
                    
            # 8: Create new ID if it's completely new
            if assigned_num is None:
                assigned_num = next_hen_id
                next_hen_id += 1
                hens[assigned_num] = {
                    "center": center, "vel": (0,0), "tid": tid,
                    "lost": 0, "size": det["size"],
                    "smooth_box": [float(v) for v in raw_box]
                }
            else:
                data = hens[assigned_num]
                old_cx, old_cy = data["center"]
                new_vx = center[0] - old_cx
                new_vy = center[1] - old_cy
                old_vx, old_vy = data["vel"]
                
                data["center"] = center
                data["vel"] = (0.7*old_vx + 0.3*new_vx, 0.7*old_vy + 0.3*new_vy)
                data["tid"] = tid
                data["lost"] = 0
                data["size"] = det["size"]
                sb = data["smooth_box"]
                data["smooth_box"] = [EMA*raw_box[i] + (1-EMA)*sb[i] for i in range(4)]
                
            used_ids.add(assigned_num)
            det["num"] = assigned_num
            
        display_frame = frame.copy()
        
        # 14, 15, 16: Draw GREEN bounding box and permanent number
        for det in detections:
            num = det["num"]
            sb = hens[num]["smooth_box"]
            x1, y1, x2, y2 = int(sb[0]), int(sb[1]), int(sb[2]), int(sb[3])
            
            cv2.rectangle(display_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = f"HEN {num}"
            
            # Text background
            (text_w, text_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(display_frame, (x1, y1 - 25), (x1 + text_w, y1), (0, 255, 0), -1)
            cv2.putText(display_frame, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
            
        # 22: Provide visible hen count, total unique hen count, and AI FPS
        visible_hens = len(detections)
        total_unique = next_hen_id - 1
        inf_fps = 1.0 / elapsed if elapsed > 0 else 0
        
        # Draw stats bar at the top
        cv2.rectangle(display_frame, (0, 0), (w, 50), (0, 0, 0), -1)
        stats_text = f"Frame {frame_no}/{total_frames} | Visible Hens: {visible_hens} | Total Unique: {total_unique} | AI FPS: {inf_fps:.1f}"
        cv2.putText(display_frame, stats_text, (20, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        
        out.write(display_frame)
        
    cap.release()
    out.release()
    
    return next_hen_id - 1

if __name__ == '__main__':
    # Start the Flask web interface on port 5000
    app.run(host='0.0.0.0', port=5000, debug=False)
