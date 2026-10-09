import time
import math
import threading
import traceback
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
        self.TRACKER_YAML = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../bytetrack_hen.yaml"))
        if not os.path.exists(self.TRACKER_YAML):
            self.TRACKER_YAML = "bytetrack.yaml"
            
        self.state_lock = threading.RLock()
        self.inference_lock = threading.Lock()
        
        self.reset_state()
        
    def reset_state(self):
        with self.state_lock:
            self.hens = {}
            self.next_hen_number = 1
            
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

    def process_live_frame(self, frame, frame_number, video_time):
        # Non-blocking lock for fast UI
        if not self.inference_lock.acquire(blocking=False):
            with self.state_lock:
                return {
                    "success": True, "busy": True, "video_time": video_time,
                    "detections": self.latest_detections,
                    "total_hens": max(0, self.next_hen_number - 1),
                    "visible_hens": len(self.latest_detections),
                    "ai_frames": self.total_inference_count,
                    "ai_fps": round(self.ai_fps, 2)
                }
        
        started = time.time()
        try:
            # 1. Run YOLO tracking synchronously
            results = self.model.track(
                source=frame,
                persist=True, 
                verbose=False, 
                conf=0.20,      # Slightly lower for faster/quicker detection
                iou=0.45,
                imgsz=480,      # Reduced from 640 for much faster processing!
                tracker=self.TRACKER_YAML,
                device=self.DEVICE
            )

            detections = []
            if results and len(results) > 0 and results[0].boxes is not None:
                boxes       = results[0].boxes.xyxy.cpu().numpy()
                confs       = results[0].boxes.conf.cpu().numpy()
                tracker_ids = (
                    results[0].boxes.id.int().cpu().tolist()
                    if results[0].boxes.id is not None
                    else [None] * len(boxes)
                )

                for box, conf, tid in zip(boxes, confs, tracker_ids):
                    if conf < 0.25: continue
                    x1, y1, x2, y2 = map(int, box)
                    if x2 <= x1 or y2 <= y1: continue
                    cb = (x1, y1, x2, y2)
                    detections.append({
                        "box": cb,
                        "center": ((x1+x2)/2.0, (y1+y2)/2.0),
                        "size": (x2 - x1, y2 - y1),
                        "track_id": tid,
                        "conf": float(conf)
                    })

            # Age hens
            with self.state_lock:
                for number in self.hens:
                    self.hens[number]["lost_frames"] += 1
                    self.hens[number]["seen"] = False

                used_hens = set()
                detections.sort(key=lambda x: x["conf"], reverse=True)

                out_detections = []

                for det in detections:
                    center = det["center"]
                    tracker_id = det["track_id"]
                    assigned = None

                    # 1. Match by ByteTrack ID
                    if tracker_id is not None:
                        for number, data in self.hens.items():
                            if number in used_hens: continue
                            if data["track_id"] == tracker_id and data["lost_frames"] <= 180:
                                assigned = number
                                break

                    # 2. Match by Position and Velocity (Optical Flow/Prediction fallback)
                    if assigned is None:
                        best_number, best_score = None, float("inf")
                        for number, data in self.hens.items():
                            if number in used_hens or data["lost_frames"] > 180:
                                continue
                            cx, cy = data["center"]
                            vx, vy = data["velocity"]
                            lost = data["lost_frames"]
                            px, py = cx + vx * min(lost, 10), cy + vy * min(lost, 10)
                            
                            d = math.hypot(center[0]-px, center[1]-py)
                            allowed = min(400, 180 + lost * 8)
                            if d <= allowed and d < best_score:
                                best_score = d
                                best_number = number
                        if best_number is not None:
                            assigned = best_number

                    # 3. Register New Hen
                    raw_box = det["box"]
                    if assigned is None:
                        assigned = self.next_hen_number
                        self.next_hen_number += 1
                        self.hens[assigned] = {
                            "center": center,
                            "velocity": (0, 0),
                            "track_id": tracker_id,
                            "lost_frames": 0,
                            "seen": True,
                            "size": det.get("size", (60, 60)),
                            "smooth_box": [float(raw_box[0]), float(raw_box[1]),
                                           float(raw_box[2]), float(raw_box[3])]
                        }
                    else:
                        data = self.hens[assigned]
                        old_cx, old_cy = data["center"]
                        new_vx, new_vy = center[0] - old_cx, center[1] - old_cy
                        old_vx, old_vy = data["velocity"]
                        data["center"] = center
                        data["velocity"] = (0.7*old_vx + 0.3*new_vx, 0.7*old_vy + 0.3*new_vy)
                        data["track_id"] = tracker_id
                        data["lost_frames"] = 0
                        data["seen"] = True
                        data["size"] = det.get("size", data.get("size", (60, 60)))

                        # Increase EMA alpha to 0.95 for instant tracking response (removes stuck/lagging boxes)
                        alpha = 0.95
                        sb = data["smooth_box"]
                        data["smooth_box"] = [
                            alpha * raw_box[0] + (1 - alpha) * sb[0],
                            alpha * raw_box[1] + (1 - alpha) * sb[1],
                            alpha * raw_box[2] + (1 - alpha) * sb[2],
                            alpha * raw_box[3] + (1 - alpha) * sb[3],
                        ]

                    used_hens.add(assigned)
                    
                    # Prepare output format for frontend
                    sb = self.hens[assigned]["smooth_box"]
                    out_detections.append({
                        "hen_number": assigned,
                        "box": [int(sb[0]), int(sb[1]), int(sb[2]), int(sb[3])],
                        "confidence": det["conf"],
                        "track_id": tracker_id,
                        "predicted": False
                    })
                        
                # Add ghost / predicted boxes (Disabled to make boxes disappear instantly when hen moves out of frame)
                for num, data in self.hens.items():
                    if num not in used_hens and 0 < data["lost_frames"] <= 1:
                        lost = data["lost_frames"]
                        vx, vy = data["velocity"]
                        sb = data.get("smooth_box")
                        if sb:
                            pred_cx = (sb[0] + sb[2]) / 2 + vx * min(lost, 15)
                            pred_cy = (sb[1] + sb[3]) / 2 + vy * min(lost, 15)
                            bw = sb[2] - sb[0]
                            bh = sb[3] - sb[1]
                        else:
                            cx, cy = data["center"]
                            pred_cx = cx + vx * min(lost, 15)
                            pred_cy = cy + vy * min(lost, 15)
                            bw, bh = data.get("size", (60, 60))

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
                if elapsed > 0: self.ai_fps = 1.0 / elapsed
                
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
                "total_hens": max(0, self.next_hen_number - 1),
                "visible_hens": len(out_detections), 
                "ai_frames": self.total_inference_count,
                "ai_fps": round(self.ai_fps, 2)
            }
        except Exception as e:
            traceback.print_exc()
            self.ai_error = str(e)
            return {"success": False, "error": str(e)}
        finally:
            self.inference_lock.release()
