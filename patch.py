import os

def patch_file():
    filepath = r"c:\Users\sachi\Downloads\giotag project\flask_app.py"
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # We will replace generate_frames and generate_frames_with_ref
    # Let's find the start of `def generate_frames(video_path):`
    start_idx = content.find("def generate_frames(video_path):")
    
    # Let's find the end of `generate_frames_with_ref` which is before `@app.route('/get_reference_settings'`
    end_idx = content.find("@app.route('/get_reference_settings'")
    
    if start_idx == -1 or end_idx == -1:
        print("Could not find start or end index.")
        return
        
    replacement = """def generate_frames(video_path):
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
    hens = {}
    next_num = 1
    EMA = 0.4
    total_counted = 0
    frame_no = 0
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: break
        frame_no += 1
        
        # Synchronous tracking on the exact frame (like analyze_video.py)
        results = model.track(frame, persist=True, verbose=False, conf=learned_conf, iou=0.45, imgsz=640)
        
        detections = []
        if results and results[0].boxes is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            confs = results[0].boxes.conf.cpu().numpy()
            tids = (results[0].boxes.id.int().cpu().tolist() if results[0].boxes.id is not None else [None] * len(boxes))
            for box, conf, tid in zip(boxes, confs, tids):
                if conf < learned_conf: continue
                x1, y1, x2, y2 = map(int, box)
                if x2 <= x1 or y2 <= y1: continue
                detections.append({
                    "box": (x1, y1, x2, y2),
                    "center": ((x1+x2)/2.0, (y1+y2)/2.0),
                    "size": (x2-x1, y2-y1),
                    "tid": tid,
                    "conf": float(conf)
                })
                
        for num in hens:
            hens[num]["lost"] += 1
            
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
                    if data["tid"] == tid and data["lost"] <= 180:
                        asgn = num; break
                        
            if asgn is None:
                best_d, best_n = float("inf"), None
                for num, data in hens.items():
                    if num in used or data["lost"] > 180: continue
                    cx, cy = data["center"]
                    vx, vy = data["vel"]
                    lost = data["lost"]
                    px = cx + vx * min(lost, 10)
                    py = cy + vy * min(lost, 10)
                    d = math.hypot(center[0]-px, center[1]-py)
                    if d <= min(400, 180 + lost*8) and d < best_d:
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
                nvx = center[0] - old_cx; nvy = center[1] - old_cy
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
            if num not in used and 0 < data["lost"] <= 60:
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
        yield (b'--frame\\r\\n'
               b'Content-Type: image/jpeg\\r\\n\\r\\n' + frame_bytes + b'\\r\\n')
               
    cap.release()

"""
    
    new_content = content[:start_idx] + replacement + content[end_idx:]
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
        
patch_file()
