import cv2
import math
import time
import threading
import traceback
import numpy as np
import torch
import yaml
from ultralytics import YOLO

class OpticalHenTracker:
    def __init__(self, model_path):
        self.MODEL_PATH = model_path
        self.DEVICE = 0 if torch.cuda.is_available() else "cpu"
        self.IMG_SIZE = 640
        self.USE_HALF = True if self.DEVICE != "cpu" else False
        
        print(f"Loading YOLO model from {model_path} on {self.DEVICE}...")
        self.model = YOLO(model_path)
        
        self.HEN_CLASS_ID = 0
        self.TRACKER_YAML = "bytetrack_hen.yaml"
        with open(self.TRACKER_YAML, "w") as f:
            f.write("""tracker_type: bytetrack
track_high_thresh: 0.08
track_low_thresh: 0.03
new_track_thresh: 0.08
track_buffer: 120
match_thresh: 0.82
fuse_score: True
""")
            
        self.YOLO_CONF = 0.05
        self.YOLO_IOU = 0.45
        self.MAX_DETECTIONS = 1500
        self.NEW_HEN_CONF = 0.12
        self.NEW_HEN_CONFIRM_FRAMES = 2
        
        self.MIN_BOX_WIDTH = 3
        self.MIN_BOX_HEIGHT = 3
        self.MAX_BOX_WIDTH_RATIO = 0.25
        self.MAX_BOX_HEIGHT_RATIO = 0.25
        self.MAX_BOX_AREA_RATIO = 0.06
        
        self.COLOR_BOOST = 0.08
        self.COLOR_MIN_PIXELS = 4
        self.COLOR_MIN_RATIO = 0.002
        
        self.BASE_MATCH_DISTANCE = 220
        self.MAX_MATCH_DISTANCE = 500
        self.MAX_LOST_SECONDS = 3.0
        self.MAX_TRACK_SPEED = 2500.0
        
        self.state_lock = threading.RLock()
        self.inference_lock = threading.Lock()
        
        self.video_fps = 30.0
        self.video_width = 0
        self.video_height = 0
        
        self.reset_state()
        
    def reset_state(self):
        with self.state_lock:
            self.hens = {}
            self.track_to_hen = {}
            self.next_hen_number = 1
            self.candidate_tracks = {}
            
            self.latest_detections = []
            self.latest_frame_number = 0
            self.latest_video_time = 0.0
            self.total_inference_count = 0
            self.ai_fps = 0.0
            self.ai_error = None
            
            self.last_ai_frame = None
            self.last_ai_boxes = {}
            self.last_ai_time = 0.0
            
            try:
                if getattr(self.model, "predictor", None) is not None:
                    self.model.predictor = None
            except:
                pass

    def center_of(self, box):
        x1, y1, x2, y2 = box
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    def size_of(self, box):
        x1, y1, x2, y2 = box
        return (max(1.0, x2 - x1), max(1.0, y2 - y1))

    def distance(self, p1, p2):
        return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

    def clamp_box(self, box):
        x1, y1, x2, y2 = box
        if self.video_width > 0:
            x1 = max(0, min(int(x1), self.video_width - 1))
            x2 = max(0, min(int(x2), self.video_width - 1))
        if self.video_height > 0:
            y1 = max(0, min(int(y1), self.video_height - 1))
            y2 = max(0, min(int(y2), self.video_height - 1))
        return (x1, y1, x2, y2)

    def valid_box(self, box):
        x1, y1, x2, y2 = box
        bw, bh = x2 - x1, y2 - y1
        if bw < self.MIN_BOX_WIDTH or bh < self.MIN_BOX_HEIGHT: return False
        if self.video_width <= 0 or self.video_height <= 0: return False
        if bw / self.video_width > self.MAX_BOX_WIDTH_RATIO: return False
        if bh / self.video_height > self.MAX_BOX_HEIGHT_RATIO: return False
        area_ratio = (bw * bh) / (self.video_width * self.video_height)
        if area_ratio > self.MAX_BOX_AREA_RATIO: return False
        return True

    def color_evidence(self, frame, box):
        try:
            x1, y1, x2, y2 = self.clamp_box(box)
            if x2 <= x1 or y2 <= y1: return 0.0
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0: return 0.0
            hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
            
            red1_low = np.array([0, 25, 40], dtype=np.uint8)
            red1_high = np.array([20, 255, 255], dtype=np.uint8)
            red2_low = np.array([155, 25, 40], dtype=np.uint8)
            red2_high = np.array([179, 255, 255], dtype=np.uint8)
            mask1 = cv2.inRange(hsv, red1_low, red1_high)
            mask2 = cv2.inRange(hsv, red2_low, red2_high)
            red_mask = cv2.bitwise_or(mask1, mask2)
            
            pink_low = np.array([155, 12, 70], dtype=np.uint8)
            pink_high = np.array([179, 190, 255], dtype=np.uint8)
            pink_mask = cv2.inRange(hsv, pink_low, pink_high)
            
            light_red_low = np.array([0, 12, 70], dtype=np.uint8)
            light_red_high = np.array([20, 190, 255], dtype=np.uint8)
            light_red_mask = cv2.inRange(hsv, light_red_low, light_red_high)
            
            combined = cv2.bitwise_or(red_mask, pink_mask)
            combined = cv2.bitwise_or(combined, light_red_mask)
            
            kernel = np.ones((3, 3), np.uint8)
            combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, kernel, iterations=1)
            combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel, iterations=1)
            
            pixels = int(cv2.countNonZero(combined))
            total = crop.shape[0] * crop.shape[1]
            if total <= 0: return 0.0
            ratio = pixels / total
            if pixels >= self.COLOR_MIN_PIXELS and ratio >= self.COLOR_MIN_RATIO:
                return min(1.0, ratio * 10.0)
            return 0.0
        except:
            return 0.0

    def create_hen(self, box, track_id, confidence, frame_number, video_time):
        if confidence < self.NEW_HEN_CONF: return None
        if track_id is not None and confidence < 0.25:
            count = self.candidate_tracks.get(track_id, 0) + 1
            self.candidate_tracks[track_id] = count
            if count < self.NEW_HEN_CONFIRM_FRAMES: return None
            
        number = self.next_hen_number
        self.next_hen_number += 1
        cx, cy = self.center_of(box)
        bw, bh = self.size_of(box)
        
        self.hens[number] = {
            "number": number, "track_id": track_id, "box": box,
            "center": (cx, cy), "velocity": (0.0, 0.0), "size": (bw, bh),
            "confidence": float(confidence), "last_frame": frame_number,
            "last_time": video_time, "visible": True
        }
        if track_id is not None:
            self.track_to_hen[track_id] = number
            self.candidate_tracks.pop(track_id, None)
        return number

    def update_hen(self, number, box, track_id, confidence, frame_number, video_time):
        data = self.hens[number]
        old_cx, old_cy = data["center"]
        new_cx, new_cy = self.center_of(box)
        dt = video_time - data["last_time"]
        if dt <= 0: dt = 1.0 / max(self.video_fps, 1.0)
        
        raw_vx = (new_cx - old_cx) / dt
        raw_vy = (new_cy - old_cy) / dt
        old_vx, old_vy = data["velocity"]
        
        vx = 0.65 * old_vx + 0.35 * raw_vx
        vy = 0.65 * old_vy + 0.35 * raw_vy
        vx = max(-self.MAX_TRACK_SPEED, min(self.MAX_TRACK_SPEED, vx))
        vy = max(-self.MAX_TRACK_SPEED, min(self.MAX_TRACK_SPEED, vy))
        
        data["box"] = box
        data["center"] = (new_cx, new_cy)
        data["velocity"] = (vx, vy)
        data["size"] = self.size_of(box)
        data["confidence"] = float(confidence)
        data["last_frame"] = frame_number
        data["last_time"] = video_time
        data["visible"] = True
        
        if track_id is not None:
            data["track_id"] = track_id
            self.track_to_hen[track_id] = number

    def predict_hen(self, data, current_time):
        dt = max(0, current_time - data["last_time"])
        if dt > self.MAX_LOST_SECONDS: return None
        cx, cy = data["center"]
        vx, vy = data["velocity"]
        bw, bh = data["size"]
        px = cx + vx * dt
        py = cy + vy * dt
        return self.clamp_box((px - bw / 2, py - bh / 2, px + bw / 2, py + bh / 2))

    def make_result(self, number, box, confidence, track_id, predicted):
        return {
            "hen_number": int(number),
            "box": [int(box[0]), int(box[1]), int(box[2]), int(box[3])],
            "confidence": round(float(confidence), 4),
            "track_id": int(track_id) if track_id is not None else None,
            "predicted": bool(predicted)
        }

    def associate(self, detections, frame_number, video_time):
        used = set()
        output = []
        for data in self.hens.values():
            data["visible"] = False
        detections = sorted(detections, key=lambda x: x["confidence"], reverse=True)
        remaining = []
        
        for det in detections:
            track_id = det["track_id"]
            number = self.track_to_hen.get(track_id) if track_id is not None else None
            if number in self.hens and number not in used:
                self.update_hen(number, det["box"], track_id, det["confidence"], frame_number, video_time)
                used.add(number)
                output.append(self.make_result(number, det["box"], det["confidence"], track_id, False))
            else:
                remaining.append(det)
                
        for det in remaining:
            current_center = self.center_of(det["box"])
            best_number = None
            best_distance = float("inf")
            for number, data in self.hens.items():
                if number in used: continue
                predicted = self.predict_hen(data, video_time)
                if predicted is None: continue
                predicted_center = self.center_of(predicted)
                d = self.distance(current_center, predicted_center)
                lost_time = video_time - data["last_time"]
                tolerance = min(self.MAX_MATCH_DISTANCE, self.BASE_MATCH_DISTANCE + lost_time * 180)
                if d <= tolerance and d < best_distance:
                    best_distance = d
                    best_number = number
            if best_number is not None:
                self.update_hen(best_number, det["box"], det["track_id"], det["confidence"], frame_number, video_time)
                used.add(best_number)
                output.append(self.make_result(best_number, det["box"], det["confidence"], det["track_id"], False))
            else:
                number = self.create_hen(det["box"], det["track_id"], det["confidence"], frame_number, video_time)
                if number is not None:
                    used.add(number)
                    output.append(self.make_result(number, det["box"], det["confidence"], det["track_id"], False))
                    
        for number, data in self.hens.items():
            if number in used: continue
            predicted = self.predict_hen(data, video_time)
            if predicted is None: continue
            output.append(self.make_result(number, predicted, data["confidence"], data["track_id"], True))
            
        output.sort(key=lambda x: x["hen_number"])
        return output

    def detect_frame(self, frame, frame_number, video_time):
        results = self.model.track(
            source=frame,
            imgsz=self.IMG_SIZE,
            conf=self.YOLO_CONF,
            iou=self.YOLO_IOU,
            classes=[self.HEN_CLASS_ID],
            max_det=self.MAX_DETECTIONS,
            tracker=self.TRACKER_YAML,
            persist=True,
            device=self.DEVICE,
            half=self.USE_HALF,
            augment=False,
            verbose=False
        )
        raw = []
        if not results or results[0].boxes is None:
            return self.associate([], frame_number, video_time)
        boxes = results[0].boxes
        for i in range(len(boxes)):
            try:
                class_id = int(boxes.cls[i].item())
                confidence = float(boxes.conf[i].item())
                coords = boxes.xyxy[i].cpu().numpy().tolist()
            except: continue
            if class_id != self.HEN_CLASS_ID or len(coords) != 4: continue
            box = self.clamp_box(coords)
            if not self.valid_box(box): continue
            
            color_score = self.color_evidence(frame, box)
            effective_confidence = min(0.99, confidence + self.COLOR_BOOST * color_score)
            
            track_id = None
            try:
                if boxes.id is not None: track_id = int(boxes.id[i].item())
            except: pass
            
            raw.append({
                "box": box, "confidence": effective_confidence,
                "model_confidence": confidence, "color_score": color_score, "track_id": track_id
            })
        return self.associate(raw, frame_number, video_time)

    def optical_flow_recover(self, frame, frame_number, video_time):
        if self.last_ai_frame is None or not self.last_ai_boxes: return []
        old_gray = cv2.cvtColor(self.last_ai_frame, cv2.COLOR_BGR2GRAY)
        new_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        recovered = []
        for number, box in list(self.last_ai_boxes.items()):
            x1, y1, x2, y2 = box
            x1, y1 = max(0, int(x1)), max(0, int(y1))
            x2, y2 = min(frame.shape[1]-1, int(x2)), min(frame.shape[0]-1, int(y2))
            if x2 <= x1 or y2 <= y1: continue
            
            mask = np.zeros_like(old_gray)
            cv2.rectangle(mask, (x1, y1), (x2, y2), 255, -1)
            points = cv2.goodFeaturesToTrack(old_gray, maxCorners=25, qualityLevel=0.01, minDistance=3, blockSize=5, mask=mask)
            if points is None or len(points) < 3: continue
            
            next_points, status, error = cv2.calcOpticalFlowPyrLK(
                old_gray, new_gray, points, None, winSize=(21, 21), maxLevel=3,
                criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01)
            )
            if next_points is None or status is None: continue
            good_old = points[status.ravel() == 1]
            good_new = next_points[status.ravel() == 1]
            if len(good_new) < 3: continue
            
            dx = float(np.median(good_new[:, 0] - good_old[:, 0]))
            dy = float(np.median(good_new[:, 1] - good_old[:, 1]))
            new_box = self.clamp_box((x1 + dx, y1 + dy, x2 + dx, y2 + dy))
            if not self.valid_box(new_box): continue
            if number not in self.hens: continue
            data = self.hens[number]
            recovered.append(self.make_result(number, new_box, data["confidence"], data["track_id"], True))
        recovered.sort(key=lambda x: x["hen_number"])
        return recovered

    def process_live_frame(self, frame, frame_number, video_time):
        self.video_width = frame.shape[1]
        self.video_height = frame.shape[0]
        
        # Non-blocking lock for fast UI
        if not self.inference_lock.acquire(blocking=False):
            flow = self.optical_flow_recover(frame, frame_number, video_time)
            with self.state_lock:
                return {
                    "success": True, "busy": True, "video_time": video_time,
                    "detections": flow if flow else self.latest_detections,
                    "total_hens": len(self.hens),
                    "visible_hens": len(flow) if flow else len(self.latest_detections),
                    "ai_frames": self.total_inference_count,
                    "ai_fps": round(self.ai_fps, 2)
                }
        
        started = time.time()
        try:
            detections = self.detect_frame(frame, frame_number, video_time)
            elapsed = time.time() - started
            if elapsed > 0: self.ai_fps = 1.0 / elapsed
            
            with self.state_lock:
                self.latest_detections = detections
                self.latest_frame_number = frame_number
                self.latest_video_time = video_time
                self.total_inference_count += 1
                self.ai_error = None
                
                self.last_ai_frame = frame.copy()
                self.last_ai_boxes = {
                    int(d["hen_number"]): tuple(d["box"])
                    for d in detections if not d["predicted"]
                }
                self.last_ai_time = video_time
                
            return {
                "success": True, "busy": False, "video_time": video_time,
                "detections": detections, "total_hens": len(self.hens),
                "visible_hens": len(detections), "ai_frames": self.total_inference_count,
                "ai_fps": round(self.ai_fps, 2)
            }
        except Exception as e:
            traceback.print_exc()
            self.ai_error = str(e)
            return {"success": False, "error": str(e)}
        finally:
            self.inference_lock.release()
