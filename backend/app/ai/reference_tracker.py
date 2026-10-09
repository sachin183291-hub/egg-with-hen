import time, math, threading, traceback, os
import numpy as np
import cv2
import torch
from ultralytics import YOLO


class ReferenceAwareHenTracker:
    def __init__(self, model_path: str):
        self.MODEL_PATH = model_path
        self.DEVICE = 0 if torch.cuda.is_available() else 'cpu'
        print(f'[RefTracker] Loading YOLO from {model_path} on {self.DEVICE}...')
        self.model = YOLO(model_path)
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        self.model(dummy, verbose=False, imgsz=640)
        print('[RefTracker] Model ready.')
        self.TRACKER_YAML = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../bytetrack_hen.yaml'))
        if not os.path.exists(self.TRACKER_YAML):
            self.TRACKER_YAML = 'bytetrack.yaml'
        self.state_lock = threading.RLock()
        self.infer_lock = threading.Lock()
        self.reference_templates = []
        self.reference_avg_size = (80, 80)
        self.reference_conf_boost = 0.0
        self.reference_ready = False
        self.reference_frames_used = 0
        self.reset_state()

    def process_reference_video(self, video_path: str, max_frames: int = 300) -> dict:
        print(f'[RefTracker] Processing reference video: {video_path}')
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return {'success': False, 'error': 'Cannot open reference video'}
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        duration_s = total_frames / fps
        step = max(1, total_frames // max_frames)
        sample_indices = list(range(0, total_frames, step))[:max_frames]
        templates = []
        sizes = []
        frames_ok = 0
        for idx in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue
            try:
                results = self.model(source=frame, verbose=False, conf=0.25, iou=0.45, imgsz=480, device=self.DEVICE)
            except Exception:
                continue
            if not results or results[0].boxes is None:
                continue
            boxes = results[0].boxes.xyxy.cpu().numpy()
            confs = results[0].boxes.conf.cpu().numpy()
            for box, conf in zip(boxes, confs):
                if conf < 0.30:
                    continue
                x1, y1, x2, y2 = map(int, box)
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
                if x2 - x1 < 10 or y2 - y1 < 10:
                    continue
                crop = frame[y1:y2, x1:x2]
                thumb = cv2.resize(crop, (64, 64))
                templates.append(thumb)
                sizes.append((x2 - x1, y2 - y1))
                frames_ok += 1
        cap.release()
        if not templates:
            return {'success': False, 'error': 'No hens detected in reference video.', 'frames_sampled': len(sample_indices)}
        MAX_TEMPLATES = 200
        if len(templates) > MAX_TEMPLATES:
            s2 = len(templates) // MAX_TEMPLATES
            templates = templates[::s2][:MAX_TEMPLATES]
            sizes = sizes[::s2][:MAX_TEMPLATES]
        avg_w = int(np.mean([s[0] for s in sizes]))
        avg_h = int(np.mean([s[1] for s in sizes]))
        with self.state_lock:
            self.reference_templates = templates
            self.reference_avg_size = (avg_w, avg_h)
            self.reference_conf_boost = 0.10
            self.reference_ready = True
            self.reference_frames_used = frames_ok
        print(f'[RefTracker] Reference ready: {len(templates)} templates, avg size {avg_w}x{avg_h}px')
        return {'success': True, 'templates_extracted': len(templates), 'frames_sampled': len(sample_indices), 'detections_used': frames_ok, 'avg_hen_size': {'width': avg_w, 'height': avg_h}, 'duration_seconds': round(duration_s, 1)}

    def _template_similarity(self, crop: np.ndarray) -> float:
        if not self.reference_templates or crop is None or crop.size == 0:
            return 0.0
        try:
            thumb = cv2.resize(crop, (64, 64))
            hist_q = cv2.calcHist([thumb], [0, 1, 2], None, [8, 8, 8], [0,256,0,256,0,256])
            cv2.normalize(hist_q, hist_q)
        except Exception:
            return 0.0
        scores = []
        sample = self.reference_templates[::max(1, len(self.reference_templates)//30)]
        for tmpl in sample:
            try:
                hist_t = cv2.calcHist([tmpl], [0, 1, 2], None, [8, 8, 8], [0,256,0,256,0,256])
                cv2.normalize(hist_t, hist_t)
                score = cv2.compareHist(hist_q, hist_t, cv2.HISTCMP_CORREL)
                scores.append(score)
            except Exception:
                pass
        return float(np.mean(scores)) if scores else 0.0

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
                if getattr(self.model, 'predictor', None) is not None:
                    self.model.predictor = None
            except Exception:
                pass

    def process_live_frame(self, frame: np.ndarray, frame_number: int, video_time: float) -> dict:
        if not self.infer_lock.acquire(blocking=False):
            with self.state_lock:
                return {'success': True, 'busy': True, 'video_time': video_time, 'detections': self.latest_detections, 'total_hens': max(0, self.next_hen_number - 1), 'visible_hens': len(self.latest_detections), 'ai_frames': self.total_inference_count, 'ai_fps': round(self.ai_fps, 2), 'reference_active': self.reference_ready}
        started = time.time()
        try:
            results = self.model.track(source=frame, persist=True, verbose=False, conf=0.20, iou=0.45, imgsz=480, tracker=self.TRACKER_YAML, device=self.DEVICE)
            raw_detections = []
            if results and len(results) > 0 and results[0].boxes is not None:
                boxes = results[0].boxes.xyxy.cpu().numpy()
                confs = results[0].boxes.conf.cpu().numpy()
                tracker_ids = (results[0].boxes.id.int().cpu().tolist() if results[0].boxes.id is not None else [None] * len(boxes))
                for box, conf, tid in zip(boxes, confs, tracker_ids):
                    if conf < 0.20:
                        continue
                    x1, y1, x2, y2 = map(int, box)
                    if x2 <= x1 or y2 <= y1:
                        continue
                    adjusted_conf = float(conf)
                    similarity = 0.0
                    if self.reference_ready:
                        crop = frame[max(0,y1):min(frame.shape[0],y2), max(0,x1):min(frame.shape[1],x2)]
                        similarity = self._template_similarity(crop)
                        if similarity > 0.3:
                            adjusted_conf = min(1.0, adjusted_conf + self.reference_conf_boost * similarity)
                        elif similarity < 0.05 and adjusted_conf < 0.35:
                            continue
                    raw_detections.append({'box': (x1, y1, x2, y2), 'center': ((x1+x2)/2.0, (y1+y2)/2.0), 'size': (x2-x1, y2-y1), 'track_id': tid, 'conf': adjusted_conf, 'similarity': round(similarity, 3)})
            with self.state_lock:
                for number in self.hens:
                    self.hens[number]['lost_frames'] += 1
                    self.hens[number]['seen'] = False
                used_hens = set()
                raw_detections.sort(key=lambda x: x['conf'], reverse=True)
                out_detections = []
                for det in raw_detections:
                    center = det['center']
                    tracker_id = det['track_id']
                    assigned = None
                    if tracker_id is not None:
                        for number, data in self.hens.items():
                            if number in used_hens: continue
                            if data['track_id'] == tracker_id and data['lost_frames'] <= 180:
                                assigned = number; break
                    if assigned is None:
                        best_number, best_score = None, float('inf')
                        for number, data in self.hens.items():
                            if number in used_hens or data['lost_frames'] > 180: continue
                            cx, cy = data['center']; vx, vy = data['velocity']; lost = data['lost_frames']
                            px = cx + vx * min(lost, 10); py = cy + vy * min(lost, 10)
                            d = math.hypot(center[0]-px, center[1]-py)
                            allowed = min(400, 180 + lost * 8)
                            if d <= allowed and d < best_score:
                                best_score = d; best_number = number
                        if best_number is not None: assigned = best_number
                    raw_box = det['box']
                    if assigned is None:
                        assigned = self.next_hen_number; self.next_hen_number += 1
                        self.hens[assigned] = {'center': center, 'velocity': (0, 0), 'track_id': tracker_id, 'lost_frames': 0, 'seen': True, 'size': det.get('size', (60, 60)), 'smooth_box': [float(raw_box[0]), float(raw_box[1]), float(raw_box[2]), float(raw_box[3])]}
                    else:
                        data = self.hens[assigned]; old_cx, old_cy = data['center']
                        new_vx = center[0] - old_cx; new_vy = center[1] - old_cy
                        old_vx, old_vy = data['velocity']
                        data['center'] = center; data['velocity'] = (0.7*old_vx + 0.3*new_vx, 0.7*old_vy + 0.3*new_vy)
                        data['track_id'] = tracker_id; data['lost_frames'] = 0; data['seen'] = True; data['size'] = det.get('size', data.get('size', (60, 60)))
                        alpha = 0.95; sb = data['smooth_box']
                        data['smooth_box'] = [alpha*raw_box[0]+(1-alpha)*sb[0], alpha*raw_box[1]+(1-alpha)*sb[1], alpha*raw_box[2]+(1-alpha)*sb[2], alpha*raw_box[3]+(1-alpha)*sb[3]]
                    used_hens.add(assigned)
                    sb = self.hens[assigned]['smooth_box']
                    out_detections.append({'hen_number': assigned, 'box': [int(sb[0]), int(sb[1]), int(sb[2]), int(sb[3])], 'confidence': det['conf'], 'track_id': tracker_id, 'predicted': False, 'similarity': det.get('similarity', 0.0)})
                for num, data in self.hens.items():
                    if num not in used_hens and 0 < data['lost_frames'] <= 1:
                        lost = data['lost_frames']; vx, vy = data['velocity']; sb = data.get('smooth_box')
                        if sb:
                            pred_cx = (sb[0]+sb[2])/2 + vx*min(lost,15); pred_cy = (sb[1]+sb[3])/2 + vy*min(lost,15)
                            bw = sb[2]-sb[0]; bh = sb[3]-sb[1]
                        else:
                            cx, cy = data['center']; pred_cx = cx + vx*min(lost,15); pred_cy = cy + vy*min(lost,15); bw, bh = data.get('size', (60, 60))
                        x1 = int(pred_cx - bw/2); y1 = int(pred_cy - bh/2); x2 = int(pred_cx + bw/2); y2 = int(pred_cy + bh/2)
                        out_detections.append({'hen_number': num, 'box': [x1, y1, x2, y2], 'confidence': 0.0, 'track_id': data.get('track_id'), 'predicted': True, 'similarity': 0.0})
                elapsed = time.time() - started
                if elapsed > 0: self.ai_fps = 1.0 / elapsed
                self.latest_detections = out_detections; self.latest_frame_number = frame_number; self.latest_video_time = video_time; self.total_inference_count += 1; self.ai_error = None
            return {'success': True, 'busy': False, 'video_time': video_time, 'detections': out_detections, 'total_hens': max(0, self.next_hen_number - 1), 'visible_hens': len(out_detections), 'ai_frames': self.total_inference_count, 'ai_fps': round(self.ai_fps, 2), 'reference_active': self.reference_ready, 'reference_templates': len(self.reference_templates) if self.reference_ready else 0}
        except Exception as e:
            traceback.print_exc(); self.ai_error = str(e)
            return {'success': False, 'error': str(e), 'reference_active': self.reference_ready}
        finally:
            self.infer_lock.release()
