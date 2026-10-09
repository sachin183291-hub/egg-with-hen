import cv2
import time
import math
import numpy as np
from ultralytics import YOLO

class FastHenTracker:
    def __init__(self, model_path, device=None):
        self.model = YOLO(model_path)
        self.device = device
        # Warmup
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        for _ in range(3):
            self.model(dummy, verbose=False, imgsz=320)

    def process_video(self, video_path, progress_callback=None):
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError("Cannot open video")

        fps_src = cap.get(cv2.CAP_PROP_FPS)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if fps_src <= 0: fps_src = 30.0

        output_path = video_path.replace(".mp4", "_output.webm").replace(".MP4", "_output.webm")
        if "_output" not in output_path:
            output_path += "_output.webm"

        fourcc = cv2.VideoWriter_fourcc(*"vp09")
        out = cv2.VideoWriter(output_path, fourcc, fps_src, (w, h))

        hens = {}
        next_num = 1
        EMA = 0.4
        frame_no = 0

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                frame_no += 1

                t0 = time.perf_counter()
                results = self.model.track(
                    frame, persist=True, verbose=False,
                    conf=0.05, iou=0.3, imgsz=320, device=self.device
                )
                elapsed = time.perf_counter() - t0

                detections = []
                if results and results[0].boxes is not None:
                    boxes = results[0].boxes.xyxy.cpu().numpy()
                    confs = results[0].boxes.conf.cpu().numpy()
                    tids  = (results[0].boxes.id.int().cpu().tolist()
                             if results[0].boxes.id is not None
                             else [None] * len(boxes))
                    raw_dets = []
                    for box, conf, tid in zip(boxes, confs, tids):
                        if conf < 0.15: continue
                        x1, y1, x2, y2 = map(int, box)
                        w, h = x2 - x1, y2 - y1
                        if w <= 0 or h <= 0: continue
                        if w > 150 or h > 150: continue 
                        
                        raw_dets.append({
                            "box": (x1, y1, x2, y2),
                            "center": ((x1+x2)/2.0, (y1+y2)/2.0),
                            "size": (w, h),
                            "tid": tid,
                            "conf": float(conf)
                        })
                    
                    raw_dets.sort(key=lambda d: d["conf"], reverse=True)
                    for d in raw_dets:
                        is_duplicate = False
                        for fd in detections:
                            dist = math.hypot(d["center"][0] - fd["center"][0], d["center"][1] - fd["center"][1])
                            if dist < 80:
                                is_duplicate = True
                                break
                        if not is_duplicate:
                            detections.append(d)

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
                            if data["tid"] == tid and data["lost"] <= 45:
                                asgn = num
                                break

                    if asgn is None:
                        best_d, best_n = float("inf"), None
                        for num, data in hens.items():
                            if num in used or data["lost"] > 45: continue
                            cx, cy = data["center"]
                            vx, vy = data["vel"]
                            lost = data["lost"]
                            px = cx + vx * min(lost, 10)
                            py = cy + vy * min(lost, 10)
                            d = math.hypot(center[0]-px, center[1]-py)
                            if d <= min(200, 100 + lost*5) and d < best_d:
                                best_d, best_n = d, num
                        if best_n is not None:
                            asgn = best_n

                    if asgn is None:
                        asgn = next_num
                        next_num += 1
                        hens[asgn] = {
                            "center": center, "vel": (0,0), "tid": tid,
                            "lost": 0, "size": det["size"],
                            "smooth_box": [float(v) for v in raw]
                        }
                    else:
                        data = hens[asgn]
                        old_cx, old_cy = data["center"]
                        nvx = center[0]-old_cx
                        nvy = center[1]-old_cy
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

                # Draw
                display = frame.copy()
                for det in detections:
                    num = det["num"]
                    sb = hens[num]["smooth_box"]
                    x1, y1, x2, y2 = int(sb[0]), int(sb[1]), int(sb[2]), int(sb[3])
                    cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(display, f"C{num} {det['conf']:.0%}",
                                (x1, max(y1-8, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
                    cv2.circle(display, (int((sb[0]+sb[2])/2), int((sb[1]+sb[3])/2)), 4, (0, 255, 0), -1)

                for num, data in hens.items():
                    if num not in used and 0 < data["lost"] <= 45:
                        lost = data["lost"]
                        vx, vy = data["vel"]
                        sb = data.get("smooth_box")
                        if sb:
                            pcx = (sb[0]+sb[2])/2 + vx*min(lost, 15)
                            pcy = (sb[1]+sb[3])/2 + vy*min(lost, 15)
                            bw = sb[2]-sb[0]
                            bh = sb[3]-sb[1]
                        else:
                            cx, cy = data["center"]
                            pcx = cx + vx*min(lost, 15)
                            pcy = cy + vy*min(lost, 15)
                            bw, bh = data.get("size", (60, 60))
                        x1, y1 = int(pcx - bw/2), int(pcy - bh/2)
                        x2, y2 = int(pcx + bw/2), int(pcy + bh/2)
                        fade = int(255 * max(0.2, 1.0 - lost/60.0))
                        cv2.rectangle(display, (x1, y1), (x2, y2), (0, fade, 255), 1)

                inf_fps = 1.0 / elapsed if elapsed > 0 else 0
                fps_color = (0, 255, 0) if inf_fps >= fps_src else (0, 80, 255)

                cv2.rectangle(display, (10, 10), (820, 80), (0, 0, 0), -1)
                cv2.putText(display,
                            f"Frame {frame_no}/{total_frames}  Det:{len(detections)}  Unique:{next_num-1}  "
                            f"Inf:{inf_fps:.1f}fps",
                            (18, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.8, fps_color, 2)

                out.write(display)

                if progress_callback:
                    progress = (frame_no / total_frames * 100) if total_frames > 0 else 0
                    progress_callback({
                        "type": "progress",
                        "frame": frame_no,
                        "total_frames": total_frames,
                        "time": round(frame_no / fps_src, 2),
                        "visible_hens": len(detections),
                        "total_hens": next_num - 1,
                        "progress": round(progress, 2)
                    })

            final_result = {
                "type": "completed",
                "total_hens": next_num - 1,
                "frames_processed": frame_no,
                "duration_seconds": round(frame_no / fps_src, 2),
                "output_video": output_path
            }
            if progress_callback:
                progress_callback(final_result)

            return final_result

        finally:
            cap.release()
            out.release()
