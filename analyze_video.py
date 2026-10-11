"""
GioTag Fast Video Analyzer (CPU-optimised)
- imgsz=640  (much faster on CPU vs 1280)
- Processes every frame but shows realtime FPS
- Reports detection quality + saves annotated output
"""

import cv2
import time
import math
import numpy as np
from ultralytics import YOLO

VIDEO_PATH  = r"c:\Users\sachi\Downloads\giotag project\DJI_20260911145654_0003_S_1minute_hen_tracking.mp4"
MODEL_PATH  = r"c:\Users\sachi\Downloads\giotag project\backend\best.pt"
OUTPUT_PATH = r"c:\Users\sachi\Downloads\giotag project\giotag_fast_output.mp4"
MAX_FRAMES  = 150   # ~5 seconds, fast check

print("Loading model ...")
model = YOLO(MODEL_PATH)
print("Warming up (3 passes) ...")
dummy = np.zeros((640, 640, 3), dtype=np.uint8)
for _ in range(3):
    model(dummy, verbose=False, imgsz=640)
print("Ready!\n")

cap     = cv2.VideoCapture(VIDEO_PATH)
fps_src = cap.get(cv2.CAP_PROP_FPS)
w       = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
h       = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
total   = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
limit   = min(MAX_FRAMES, total)

print(f"Video  : {w}x{h} @ {fps_src:.1f}fps  |  {total} total frames")
print(f"Testing: first {limit} frames\n")

fourcc = cv2.VideoWriter_fourcc(*"mp4v")
out    = cv2.VideoWriter(OUTPUT_PATH, fourcc, fps_src, (w, h))

frame_times   = []
det_per_frame = []
conf_values   = []
hens          = {}
next_num      = 1
EMA           = 0.95

frame_no = 0
while cap.isOpened() and frame_no < limit:
    ret, frame = cap.read()
    if not ret:
        break
    frame_no += 1

    t0 = time.perf_counter()
    results = model.track(
        frame, persist=True, verbose=False,
        conf=0.05, iou=0.3, imgsz=640   # 640 = fast on CPU
    )
    t1 = time.perf_counter()
    elapsed = t1 - t0
    frame_times.append(elapsed)

    detections = []
    if results and results[0].boxes is not None:
        boxes = results[0].boxes.xyxy.cpu().numpy()
        confs = results[0].boxes.conf.cpu().numpy()
        tids  = (results[0].boxes.id.int().cpu().tolist()
                 if results[0].boxes.id is not None
                 else [None] * len(boxes))
        for box, conf, tid in zip(boxes, confs, tids):
            if conf < 0.05: continue
            x1, y1, x2, y2 = map(int, box)
            if x2 <= x1 or y2 <= y1: continue
            detections.append({
                "box": (x1, y1, x2, y2),
                "center": ((x1+x2)/2.0, (y1+y2)/2.0),
                "size":   (x2-x1, y2-y1),
                "tid":    tid,
                "conf":   float(conf)
            })
            conf_values.append(float(conf))

    det_per_frame.append(len(detections))

    for num in hens:
        hens[num]["lost"] += 1

    used = set()
    detections.sort(key=lambda d: d["conf"], reverse=True)

    for det in detections:
        center = det["center"]
        raw    = det["box"]
        tid    = det["tid"]
        asgn   = None

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
                lost   = data["lost"]
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
                "smooth_box": [float(v) for v in raw]
            }
        else:
            data = hens[asgn]
            old_cx, old_cy = data["center"]
            nvx = center[0]-old_cx; nvy = center[1]-old_cy
            ovx, ovy = data["vel"]
            data["center"]     = center
            data["vel"]        = (0.7*ovx+0.3*nvx, 0.7*ovy+0.3*nvy)
            data["tid"]        = tid
            data["lost"]       = 0
            data["size"]       = det["size"]
            sb = data["smooth_box"]
            data["smooth_box"] = [EMA*raw[i]+(1-EMA)*sb[i] for i in range(4)]

        used.add(asgn)
        det["num"] = asgn

    # Draw
    display = frame.copy()
    for det in detections:
        num = det["num"]
        sb  = hens[num]["smooth_box"]
        x1, y1, x2, y2 = int(sb[0]), int(sb[1]), int(sb[2]), int(sb[3])
        cv2.rectangle(display, (x1,y1),(x2,y2),(0,255,0),2)
        
        label = f"HEN {num}"
        (w_txt, h_txt), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        cv2.rectangle(display, (x1, max(y1 - 22, 0)), (x1 + w_txt, max(y1, 22)), (0, 255, 0), -1)
        cv2.putText(display, label,
                    (x1, max(y1-6, 16)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)
        cv2.circle(display, (int((sb[0]+sb[2])/2), int((sb[1]+sb[3])/2)), 4, (0,255,0), -1)

    for num, data in hens.items():
        if num not in used and 0 < data["lost"] <= 60:
            lost = data["lost"]
            vx, vy = data["vel"]
            sb = data.get("smooth_box")
            if sb:
                pcx = (sb[0]+sb[2])/2 + vx*min(lost,15)
                pcy = (sb[1]+sb[3])/2 + vy*min(lost,15)
                bw  = sb[2]-sb[0]; bh = sb[3]-sb[1]
            else:
                cx, cy = data["center"]
                pcx = cx+vx*min(lost,15); pcy = cy+vy*min(lost,15)
                bw, bh = data.get("size",(60,60))
            x1=int(pcx-bw/2); y1=int(pcy-bh/2)
            x2=int(pcx+bw/2); y2=int(pcy+bh/2)
            fade = int(255*max(0.2,1.0-lost/60.0))
            cv2.rectangle(display,(x1,y1),(x2,y2),(0,fade,255),1)
            # Add ghost label to match format
            label = f"HEN {num}"
            cv2.putText(display, label, (x1, max(y1-6, 16)), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, fade, 255), 1)

    inf_fps = 1.0/elapsed if elapsed > 0 else 0
    src_fps = fps_src

    # Colour: green if fast enough, red if too slow
    fps_color = (0, 255, 0) if inf_fps >= src_fps else (0, 80, 255)

    # Time calculation
    time_s = frame_no / fps_src if fps_src > 0 else 0
    visible_count = len(detections) + sum(1 for num, data in hens.items() if num not in used and 0 < data["lost"] <= 60)

    # Top-left status box
    cv2.rectangle(display, (10, 10), (280, 110), (0, 0, 0), -1)
    cv2.putText(display, f"TIME: {time_s:.1f}s", (20, 40), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(display, f"VISIBLE HENS: {visible_count}", (20, 70), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2, cv2.LINE_AA)
    cv2.putText(display, f"TOTAL HENS: {next_num-1}", (20, 100), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
    
    # We can still print fps debug info on the console instead of drawing it.

    out.write(display)

    # Print every 10 frames
    if frame_no % 10 == 0 or frame_no == 1:
        rt_ratio = inf_fps / src_fps
        status   = "REAL-TIME OK" if rt_ratio >= 1.0 else f"SLOW ({rt_ratio:.2f}x)"
        print(f"  Frame {frame_no:>4}/{limit}  det:{len(detections):>3}  "
              f"InfFPS:{inf_fps:>5.1f}  status:{status}  unique:{next_num-1}")

cap.release()
out.release()

# ─── Report ────────────────────────────────────────────────────────────────────
avg_ms  = 1000*sum(frame_times)/len(frame_times)
avg_fps = 1000/avg_ms
avg_det = sum(det_per_frame)/len(det_per_frame)
avg_c   = sum(conf_values)/len(conf_values) if conf_values else 0
rt_ok   = avg_fps >= fps_src

print("\n" + "="*65)
print("          GioTag Fast Video Analysis Report")
print("="*65)
print(f"  Device           : CPU (no GPU found)")
print(f"  Model imgsz      : 640 (CPU-fast mode)")
print(f"  Video            : {w}x{h} @ {fps_src:.1f} fps")
print(f"  Frames analyzed  : {frame_no}")
print()
print(f"  Avg inference    : {avg_ms:.1f} ms/frame")
print(f"  Avg InfFPS       : {avg_fps:.1f} fps")
print(f"  Source FPS       : {fps_src:.1f} fps")
print(f"  Real-time ratio  : {avg_fps/fps_src:.2f}x  {'✅ REAL-TIME!' if rt_ok else '⚠️ BELOW REAL-TIME'}")
print()
print(f"  Avg combs/frame  : {avg_det:.1f}")
print(f"  Max combs/frame  : {max(det_per_frame)}")
print(f"  Total unique hens: {next_num-1}")
print()
print(f"  Avg confidence   : {avg_c:.1%}")
print(f"  Low conf (<30%)  : {sum(1 for c in conf_values if c<0.3)}/{len(conf_values)}")
print()
print(f"  Output saved     : {OUTPUT_PATH}")
print("="*65)

if not rt_ok:
    print("\n  SPEED TIPS (to reach real-time on CPU):")
    print("   1. Reduce imgsz to 480 or 320 for even faster inference")
    print("   2. Process every 2nd frame (frame_skip=2)")
    print("   3. Install GPU + CUDA PyTorch for 10-20x speedup")
    ratio_640 = avg_fps
    print(f"\n   At imgsz=640 you get {ratio_640:.1f} fps.")
    print(f"   You need {fps_src:.1f} fps for real-time.")
    need_skip = math.ceil(fps_src / ratio_640)
    if need_skip > 1:
        print(f"   With frame_skip={need_skip}, effective rate = {ratio_640:.1f} fps (covers {fps_src:.1f}fps source)")
