import time
import math
import threading
import traceback
import cv2
import numpy as np
import os
import torch
from ultralytics import YOLO

class OpticalHenTracker:
    def __init__(self, model_path):
        self.MODEL_PATH = model_path
        self.DEVICE = 0 if torch.cuda.is_available() else "cpu"
        
        print(f"Loading YOLO model from {model_path} on {self.DEVICE}...")
        self.model = YOLO(model_path)
        
        print("Warming up AI model...")
        dummy_img = np.zeros((640, 640, 3), dtype=np.uint8)
        self.model(dummy_img, verbose=False, imgsz=640)
        
        # ByteTrack config
        possible_yamls = [
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../../bytetrack_hen.yaml")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../bytetrack_hen.yaml")),
            os.path.abspath(os.path.join(os.getcwd(), "bytetrack_hen.yaml")),
            os.path.abspath(os.path.join(os.getcwd(), "backend", "bytetrack_hen.yaml")),
        ]
        self.TRACKER_YAML = next((y for y in possible_yamls if os.path.exists(y)), "bytetrack.yaml")
            
        self.state_lock = threading.RLock()
        self.inference_lock = threading.Lock()
        
        self.reset_state()
        
    def reset_state(self):
        with self.state_lock:
            self.hens = {}
            self.next_hen_number = 1
            self.prev_small_gray = None
            
            self.latest_detections = []
            self.latest_frame_number = 0
            self.latest_video_time = 0.0
            self.total_inference_count = 0
            self.ai_fps = 0.0
            self.ai_error = None
            
            try:
                if getattr(self.model, "predictor", None) is not None:
                    self.model.predictor = None
            except:
                pass

    def is_pure_comb(self, box, frame):
        x1, y1, x2, y2 = map(int, box)
        w = x2 - x1
        h = y2 - y1
        area = w * h
        # Strict comb / head dimensions (25-165px) - excludes large hen body (200-500px)
        if w < 25 or h < 25 or w > 165 or h > 165:
            return False
        if area < 900 or area > 22000:
            return False
        aspect = w / float(max(h, 1))
        if aspect < 0.35 or aspect > 2.2:
            return False
        # Red comb color verification in HSV
        crop = frame[max(0, y1):min(frame.shape[0], y2), max(0, x1):min(frame.shape[1], x2)]
        if crop.size > 0:
            hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
            mask1 = cv2.inRange(hsv, np.array([0, 35, 35]), np.array([16, 255, 255]))
            mask2 = cv2.inRange(hsv, np.array([150, 35, 35]), np.array([180, 255, 255]))
            red_ratio = (cv2.countNonZero(mask1) + cv2.countNonZero(mask2)) / float(crop.shape[0] * crop.shape[1])
            if red_ratio < 0.10:
                return False
        return True

    def process_live_frame(self, frame, frame_number, video_time):
        # Auto-reset if user rewinds or replays video from start
        if video_time < (self.latest_video_time - 0.8) and self.latest_video_time > 1.0:
            self.reset_state()

        # Non-blocking lock for fast UI
        if not self.inference_lock.acquire(blocking=False):
            with self.state_lock:
                verified_total = len([h for h in self.hens.values() if h.get("hits", 0) >= (1 if frame_number <= 3 else 2)])
                return {
                    "success": True, "busy": True, "video_time": video_time,
                    "detections": self.latest_detections,
                    "total_hens": verified_total,
                    "visible_hens": len(self.latest_detections),
                    "ai_frames": self.total_inference_count,
                    "ai_fps": round(self.ai_fps, 2)
                }
        
        started = time.time()
        try:
            fh, fw = frame.shape[:2]

            # ─── 0. Fast Camera Motion Compensation ───
            small_gray = cv2.cvtColor(cv2.resize(frame, (320, 180)), cv2.COLOR_BGR2GRAY).astype(np.float32)
            cam_dx, cam_dy = 0.0, 0.0
            if getattr(self, "prev_small_gray", None) is not None:
                shift, response = cv2.phaseCorrelate(self.prev_small_gray, small_gray)
                if response > 0.04 and abs(shift[0]) < 25 and abs(shift[1]) < 25:
                    cam_dx = shift[0] * (fw / 320.0)
                    cam_dy = shift[1] * (fh / 180.0)
            self.prev_small_gray = small_gray

            # Update existing tracks with camera translation
            with self.state_lock:
                for num, data in self.hens.items():
                    data["lost_frames"] += 1
                    data["seen"] = False
                    cx, cy = data["center"]
                    data["center"] = (cx + cam_dx, cy + cam_dy)
                    if "smooth_box" in data:
                        sb = data["smooth_box"]
                        data["smooth_box"] = [sb[0] + cam_dx, sb[1] + cam_dy, sb[2] + cam_dx, sb[3] + cam_dy]

            # ─── 1. Run YOLO inference ───
            results = self.model.predict(
                source=frame,
                verbose=False, 
                conf=0.15,
                iou=0.35,
                imgsz=640,
                device=self.DEVICE
            )

            raw_detections = []
            if results and len(results) > 0 and results[0].boxes is not None:
                boxes = results[0].boxes.xyxy.cpu().numpy()
                confs = results[0].boxes.conf.cpu().numpy()

                for box, conf in zip(boxes, confs):
                    if conf < 0.15: continue
                    if not self.is_pure_comb(box, frame): continue
                    x1, y1, x2, y2 = map(int, box)
                    raw_detections.append({
                        "box": [x1, y1, x2, y2],
                        "center": ((x1 + x2) / 2.0, (y1 + y2) / 2.0),
                        "size": (x2 - x1, y2 - y1),
                        "conf": float(conf)
                    })

            # Sort purely by confidence so compact comb boxes are preferred over any stray large boxes
            raw_detections.sort(key=lambda d: d["conf"], reverse=True)

            # ─── 2. Strict 1-Box-Per-Hen Deduplication ───
            detections = []
            for r_det in raw_detections:
                rx1, ry1, rx2, ry2 = r_det["box"]
                rcx, rcy = r_det["center"]
                is_duplicate = False
                for existing in detections:
                    ex1, ey1, ex2, ey2 = existing["box"]
                    ecx, ecy = existing["center"]
                    if math.hypot(rcx - ecx, rcy - ecy) < 45:
                        is_duplicate = True
                        break
                    if (ex1 <= rcx <= ex2 and ey1 <= rcy <= ey2) or (rx1 <= ecx <= rx2 and ry1 <= ecy <= ry2):
                        is_duplicate = True
                        break
                    ix1, iy1 = max(rx1, ex1), max(ry1, ey1)
                    ix2, iy2 = min(rx2, ex2), min(ry2, ey2)
                    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
                    inter_area = iw * ih
                    union_area = (rx2 - rx1) * (ry2 - ry1) + (ex2 - ex1) * (ey2 - ey1) - inter_area
                    if union_area > 0 and (inter_area / union_area) > 0.30:
                        is_duplicate = True
                        break
                if not is_duplicate:
                    detections.append(r_det)

            # Spatial sort on frame 1 so initial labels start 1, 2, 3 in natural sequence
            if frame_number <= 1:
                detections.sort(key=lambda d: d["center"][1] * 2.0 + d["center"][0])

            with self.state_lock:
                # ─── 3. Mutual Nearest Neighbor (MNN) Matching ───
                MAX_MATCH_DIST = 125.0
                det_to_hen = {}
                for d_idx, det in enumerate(detections):
                    cx, cy = det["center"]
                    best_num, best_dist = None, float("inf")
                    for num, data in self.hens.items():
                        if data["lost_frames"] > 45: continue
                        hx, hy = data["center"]
                        d = math.hypot(cx - hx, cy - hy)
                        if d <= MAX_MATCH_DIST and d < best_dist:
                            best_dist = d
                            best_num = num
                    if best_num is not None:
                        det_to_hen[d_idx] = (best_num, best_dist)

                hen_to_det = {}
                for num, data in self.hens.items():
                    if data["lost_frames"] > 45: continue
                    hx, hy = data["center"]
                    best_d_idx, best_dist = None, float("inf")
                    for d_idx, det in enumerate(detections):
                        d = math.hypot(det["center"][0] - hx, det["center"][1] - hy)
                        if d <= MAX_MATCH_DIST and d < best_dist:
                            best_dist = d
                            best_d_idx = d_idx
                    if best_d_idx is not None:
                        hen_to_det[num] = (best_d_idx, best_dist)

                matched_dets = set()
                used_hens = set()
                out_detections = []
                EMA_ALPHA = 0.90

                # Accept ONLY mutual matches
                for d_idx, (num, dist) in det_to_hen.items():
                    if num in hen_to_det and hen_to_det[num][0] == d_idx:
                        matched_dets.add(d_idx)
                        used_hens.add(num)
                        det = detections[d_idx]
                        center = det["center"]
                        raw_box = det["box"]
                        data = self.hens[num]

                        old_cx, old_cy = data["center"]
                        data["velocity"] = (center[0] - old_cx, center[1] - old_cy)
                        data["center"] = center
                        data["lost_frames"] = 0
                        data["seen"] = True
                        data["hits"] = data.get("hits", 1) + 1
                        data["size"] = det["size"]

                        sb = data.get("smooth_box", [float(v) for v in raw_box])
                        data["smooth_box"] = [
                            EMA_ALPHA * raw_box[i] + (1 - EMA_ALPHA) * sb[i]
                            for i in range(4)
                        ]
                        det["hen_number"] = num

                        sb = data["smooth_box"]
                        out_detections.append({
                            "hen_number": num,
                            "box": [int(sb[0]), int(sb[1]), int(sb[2]), int(sb[3])],
                            "confidence": det["conf"],
                            "track_id": num,
                            "predicted": False
                        })

                # ─── 4. Unmatched Detections (Re-attach or Brand New Number) ───
                for d_idx, det in enumerate(detections):
                    if d_idx in matched_dets:
                        continue
                    center = det["center"]
                    raw_box = det["box"]

                    reassigned_num = None
                    closest_dist = float("inf")
                    for num, data in self.hens.items():
                        if num in used_hens or data["lost_frames"] > 45: continue
                        d = math.hypot(center[0] - data["center"][0], center[1] - data["center"][1])
                        if d <= 125.0 and d < closest_dist:
                            closest_dist = d
                            reassigned_num = num

                    if reassigned_num is not None:
                        num = reassigned_num
                        data = self.hens[num]
                        data["center"] = center
                        data["lost_frames"] = 0
                        data["seen"] = True
                        data["hits"] = data.get("hits", 1) + 1
                        data["smooth_box"] = [float(v) for v in raw_box]
                    else:
                        num = self.next_hen_number
                        self.next_hen_number += 1
                        self.hens[num] = {
                            "center": center,
                            "velocity": (0.0, 0.0),
                            "lost_frames": 0,
                            "seen": True,
                            "hits": 1,
                            "size": det["size"],
                            "smooth_box": [float(v) for v in raw_box],
                        }

                    used_hens.add(num)
                    det["hen_number"] = num

                    sb = self.hens[num]["smooth_box"]
                    out_detections.append({
                        "hen_number": num,
                        "box": [int(sb[0]), int(sb[1]), int(sb[2]), int(sb[3])],
                        "confidence": det["conf"],
                        "track_id": num,
                        "predicted": False
                    })

                # 4. Predicted ghost boxes for briefly occluded hens (prevents visual flickering)
                for num, data in self.hens.items():
                    if num not in used_hens and 0 < data["lost_frames"] <= 15 and data.get("hits", 0) >= 2:
                        lost = data["lost_frames"]
                        sb = data.get("smooth_box")
                        if sb:
                            vx, vy = data.get("velocity", (0, 0))
                            pred_cx = (sb[0] + sb[2]) / 2 + vx * min(lost, 8)
                            pred_cy = (sb[1] + sb[3]) / 2 + vy * min(lost, 8)
                            bw = sb[2] - sb[0]
                            bh = sb[3] - sb[1]
                            x1 = int(pred_cx - bw / 2)
                            y1 = int(pred_cy - bh / 2)
                            x2 = int(pred_cx + bw / 2)
                            y2 = int(pred_cy + bh / 2)
                            out_detections.append({
                                "hen_number": num,
                                "box": [x1, y1, x2, y2],
                                "confidence": 0.0,
                                "track_id": data.get("track_id"),
                                "predicted": True
                            })

                elapsed = time.time() - started
                if elapsed > 0:
                    self.ai_fps = 1.0 / elapsed
                
                # Count verified established hens
                verified_total = len([h for h in self.hens.values() if h.get("hits", 0) >= (1 if frame_number <= 3 else 2)])

                self.latest_detections = out_detections
                self.latest_frame_number = frame_number
                self.latest_video_time = video_time
                self.total_inference_count += 1
                self.ai_error = None
                    
            return {
                "success": True, 
                "busy": False, 
                "video_time": video_time,
                "detections": self.latest_detections, 
                "total_hens": verified_total,
                "visible_hens": len(used_hens), 
                "ai_frames": self.total_inference_count,
                "ai_fps": round(self.ai_fps, 2)
            }
        except Exception as e:
            traceback.print_exc()
            self.ai_error = str(e)
            return {"success": False, "error": str(e)}
        finally:
            self.inference_lock.release()
