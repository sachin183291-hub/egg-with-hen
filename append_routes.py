import os

def append_routes():
    filepath = r"c:\Users\sachi\Downloads\giotag project\flask_app.py"
    
    routes = """
def analyze_reference_video(video_path):
    \"\"\"Analyze reference video: sample frames, run YOLO, extract average
    detection zone and hen count to tune live camera parameters.\"\"\"
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
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400
    file = request.files['file']
    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    
    global reference_settings
    try:
        analyze_reference_video(filepath)
        reference_settings['reference_video'] = filename
        return jsonify({
            "success": True,
            "filename": filename,
            "settings": reference_settings
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400
    file = request.files['file']
    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    return jsonify({"success": True, "filename": filename})

@app.route('/stream/<filename>')
def serve_video(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/start_stream', methods=['POST'])
def start_stream():
    global active_stream
    data = request.get_json() or {}
    video_source = data.get('video_source', 'camera')
    
    if video_source != 'camera':
        video_source = os.path.join(UPLOAD_FOLDER, secure_filename(video_source))
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
"""
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    end_idx = content.find("@app.route('/get_reference_settings'")
    if end_idx == -1:
        print("Could not find get_reference_settings endpoint")
        return
        
    new_content = content[:end_idx] + routes + "\n" + content[end_idx:]
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)

append_routes()
