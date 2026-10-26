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
                        if conf < 0.06: continue
                        x1, y1, x2, y2 = map(float, box)
                        bw, bh = x2 - x1, y2 - y1
                        if bw < 14 or bh < 14: continue
                        max_comb_w = int(w * 0.09) if w > 900 else int(w * 0.10)
                        max_comb_h = int(h * 0.15) if h > 900 else int(h * 0.16)
                        if bw > max_comb_w or bh > max_comb_h or (bw * bh) > (max_comb_w * max_comb_h): continue
                        
                        raw_dets.append({
                            "box": (x1, y1, x2, y2),
                            "center": ((x1+x2)/2.0, (y1+y2)/2.0),
                            "size": (bw, bh),
                            "tid": tid,
                            "conf": float(conf)
                        })
                    
                    raw_dets.sort(key=lambda d: d["conf"], reverse=True)
                    for d in raw_dets:
                        is_duplicate = False
                        for fd in detections:
                            dist = math.hypot(d["center"][0] - fd["center"][0], d["center"][1] - fd["center"][1])
                            # Check IoU
                            ix1 = max(d["box"][0], fd["box"][0])
                            iy1 = max(d["box"][1], fd["box"][1])
                            ix2 = min(d["box"][2], fd["box"][2])
                            iy2 = min(d["box"][3], fd["box"][3])
                            inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
                            a1 = (d["box"][2] - d["box"][0]) * (d["box"][3] - d["box"][1])
                            a2 = (fd["box"][2] - fd["box"][0]) * (fd["box"][3] - fd["box"][1])
                            iou = inter / float(a1 + a2 - inter) if (a1 + a2 - inter) > 0 else 0
                            if dist < 18 or iou > 0.45:
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

                # Draw matching track_028imnwx_output.mp4
                display = frame.copy()
                for det in detections:
                    num = det["num"]
                    sb = hens[num]["smooth_box"]
                    x1, y1, x2, y2 = int(sb[0]), int(sb[1]), int(sb[2]), int(sb[3])
                    # Snug green box on comb
                    cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    # Green ID text above the box
                    cv2.putText(display, f"ID: {num}",
                                (x1, max(y1 - 10, 15)), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (0, 255, 0), 2)

                # Draw red Total Hens on top right
                total_text = f"Total Hens: {next_num - 1}"
                (tw, th), _ = cv2.getTextSize(total_text, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)
                cv2.putText(display, total_text, (w - tw - 20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

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
