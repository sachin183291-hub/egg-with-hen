import cv2
import math
import numpy as np
import torch
import os
import base64
from ultralytics import YOLO

class HighRecallHenTracker:
    def __init__(self, model_path, device=None):
        self.model = YOLO(model_path)
        if device is not None:
            self.device = device
        else:
            self.device = 0 if torch.cuda.is_available() else "cpu"
        
        self.img_size = 1280 if self.device != "cpu" else 640
        self.use_half = True if self.device != "cpu" else False
        
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
        
        self.HEN_CLASS_ID = 0
        
        self.reset_tracking()
        
        self.tracker_yaml = os.path.abspath(os.path.join(os.path.dirname(__file__), "bytetrack_hen_comb.yaml"))
        with open(self.tracker_yaml, "w") as f:
            f.write("""tracker_type: bytetrack\ntrack_high_thresh: 0.08\ntrack_low_thresh: 0.03\nnew_track_thresh: 0.08\ntrack_buffer: 120\nmatch_thresh: 0.82\nfuse_score: True\n""")

    def reset_tracking(self):
        self.hens = {}
        self.track_to_hen = {}
        self.next_hen_number = 1
        self.candidate_tracks = {}
        self.last_ai_frame = None
        self.last_ai_boxes = {}
        self.last_ai_time = 0.0
        self.video_fps = 30.0
        self.video_width = 1280
        self.video_height = 720
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
        bw = x2 - x1
        bh = y2 - y1
        if bw < self.MIN_BOX_WIDTH or bh < self.MIN_BOX_HEIGHT:
            return False
        if self.video_width <= 0 or self.video_height <= 0:
            return False
        if bw / self.video_width > self.MAX_BOX_WIDTH_RATIO:
            return False
        if bh / self.video_height > self.MAX_BOX_HEIGHT_RATIO:
            return False
        area_ratio = (bw * bh) / (self.video_width * self.video_height)
        if area_ratio > self.MAX_BOX_AREA_RATIO:
            return False
        return True

    def color_evidence(self, frame, box):
        try:
            x1, y1, x2, y2 = self.clamp_box(box)
            if x2 <= x1 or y2 <= y1: return 0.0
            crop = frame[int(y1):int(y2), int(x1):int(x2)]
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
            "number": number, "track_id": track_id, "box": box, "center": (cx, cy),
            "velocity": (0.0, 0.0), "size": (bw, bh), "confidence": float(confidence),
            "last_frame": frame_number, "last_time": video_time, "visible": True
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
        dt = current_time - data["last_time"]
        if dt < 0: dt = 0
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
            "track_id": None if track_id is None else int(track_id),
            "predicted": bool(predicted)
        }

    def associate(self, detections, frame_number, video_time):
        used = set()
        output = []
        for data in self.hens.values():
            data["visible"] = False
        detections = sorted(detections, key=lambda x: x["confidence"], reverse=True)
        remaining = []
        # Pass 1 - Byte Track ID
        for det in detections:
            track_id = det["track_id"]
            number = None
            if track_id is not None:
                number = self.track_to_hen.get(track_id)
            if number in self.hens and number not in used:
                self.update_hen(number, det["box"], track_id, det["confidence"], frame_number, video_time)
                used.add(number)
                output.append(self.make_result(number, det["box"], det["confidence"], track_id, False))
            else:
                remaining.append(det)
        # Pass 2 - Position + Motion
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
        # Pass 3 - Temporary Prediction
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
            imgsz=self.img_size,
            conf=self.YOLO_CONF,
            iou=self.YOLO_IOU,
            classes=[self.HEN_CLASS_ID],
            max_det=self.MAX_DETECTIONS,
            tracker=self.tracker_yaml,
            persist=True,
            device=self.device,
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

    def draw_results(self, frame, detections, frame_no, video_time):
        annotated = frame.copy()
        visible_count = 0
        for det in detections:
            x1, y1, x2, y2 = det["box"]
            hen_number = det["hen_number"]
            predicted = det["predicted"]
            if not predicted: visible_count += 1
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2 if predicted else 3)
            label = f"HEN {hen_number}"
            font, scale, thick = cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2
            (tw, th), _ = cv2.getTextSize(label, font, scale, thick)
            ly = max(0, y1 - th - 10)
            cv2.rectangle(annotated, (x1, ly), (x1 + tw + 10, y1), (0, 255, 0), -1)
            cv2.putText(annotated, label, (x1 + 5, y1 - 5), font, scale, (0, 0, 0), thick, cv2.LINE_AA)
            
        cv2.rectangle(annotated, (20, 20), (700, 180), (0, 0, 0), -1)
        cv2.putText(annotated, f"TIME: {video_time:.1f}s", (35, 55), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(annotated, f"VISIBLE HENS: {visible_count}", (35, 105), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(annotated, f"TOTAL HENS: {len(self.hens)}", (35, 155), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 255), 3)
        return annotated, visible_count

    def process_to_queue(self, video_path, frame_queue, job_dict):
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            frame_queue.put(None)
            return
        self.video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.video_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.video_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        job_dict["fps"] = self.video_fps
        frame_no = 0
        try:
            while True:
                ret, frame = cap.read()
                if not ret: break
                frame_no += 1
                video_time = frame_no / self.video_fps
                detections = self.detect_frame(frame, frame_no, video_time)
                annotated, visible_count = self.draw_results(frame, detections, frame_no, video_time)
                _, buffer = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
                b64 = base64.b64encode(buffer.tobytes()).decode("utf-8")
                pct = int(frame_no / total_frames * 100) if total_frames > 0 else 0
                job_dict["progress"] = pct
                job_dict["visible_hens"] = visible_count
                job_dict["total_hens"] = len(self.hens)
                frame_queue.put({
                    "frame": b64, "visible_hens": visible_count,
                    "total_hens": len(self.hens), "progress": pct,
                })
        finally:
            cap.release()
            frame_queue.put(None)

    def process_frame(self, frame, frame_no=1, fps=30.0, video_time=None):
        self.video_fps = fps
        self.video_width = frame.shape[1]
        self.video_height = frame.shape[0]
        if video_time is None:
            video_time = frame_no / self.video_fps
        detections = self.detect_frame(frame, frame_no, video_time)
        annotated, visible_count = self.draw_results(frame, detections, frame_no, video_time)
        _, buffer = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
        b64 = base64.b64encode(buffer.tobytes()).decode("utf-8")
        formatted_detections = [{"box": d["box"], "hen_number": d["hen_number"], "predicted": d["predicted"]} for d in detections]
        return b64, visible_count, len(self.hens), formatted_detections
