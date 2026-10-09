import cv2
import time
from ultralytics import YOLO
import tkinter as tk
from threading import Thread
import numpy as np

class LiveHenTracker:
    def __init__(self, model_path='yolov8n.pt', video_source=0):
        self.model_path = model_path
        self.video_source = video_source
        self.cap = None
        
        print(f"Loading model from {model_path}...")
        self.model = YOLO(model_path)
        
        print("Warming up AI model...")
        dummy_img = np.zeros((320, 320, 3), dtype=np.uint8)
        self.model(dummy_img, verbose=False, imgsz=320)
        
        self.unique_hen_ids = set()
        self.is_running = False
        self.window_open = True
        
        # Setup GUI
        self.root = tk.Tk()
        self.root.title("GioTag - Live Hen Tracker")
        self.root.geometry("300x150")
        
        self.status_lbl = tk.Label(self.root, text="Status: Stopped", font=("Arial", 12))
        self.status_lbl.pack(pady=10)
        
        self.start_btn = tk.Button(self.root, text="Start Live Video", command=self.start_tracking, bg="green", fg="white", font=("Arial", 12))
        self.start_btn.pack(pady=5)
        
        self.stop_btn = tk.Button(self.root, text="Stop Live Video", command=self.stop_tracking, bg="red", fg="white", font=("Arial", 12))
        self.stop_btn.pack(pady=5)
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def start_tracking(self):
        if not self.is_running:
            self.is_running = True
            self.status_lbl.config(text="Status: Running Live Video")
            self.cap = cv2.VideoCapture(self.video_source)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1) # Reduce buffer size to minimize lag
            Thread(target=self.tracking_loop, daemon=True).start()
            
    def stop_tracking(self):
        if self.is_running:
            self.is_running = False
            self.status_lbl.config(text="Status: Stopped")
            if self.cap:
                self.cap.release()
            cv2.destroyAllWindows()

    def tracking_loop(self):
        import math
        import time
        # Track persistent hens exactly like StableHenTracker does
        self.hens = {}
        self.next_hen_number = 1
        
        frame_no = 0
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0 or fps > 100: fps = 30.0
        
        is_live = (str(self.video_source) == '0' or str(self.video_source) == 'camera')
        start_time = time.time()
        
        while self.is_running and self.cap.isOpened():
            if not is_live:
                elapsed = time.time() - start_time
                target_frame = int(elapsed * fps)
                if target_frame < frame_no:
                    time.sleep((frame_no - target_frame) / fps)
                elif target_frame > frame_no + 1:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                    frame_no = target_frame

            ret, frame = self.cap.read()
            if not ret:
                break
                
            frame_no += 1
                
            import os
            # Ensure we use the custom bytetrack config
            tracker_cfg = os.path.join(os.path.dirname(__file__), "backend", "bytetrack_hen.yaml")
            if not os.path.exists(tracker_cfg):
                tracker_cfg = "bytetrack.yaml"
            
            # Run YOLO tracking synchronously
            # Matching the behavior of the video analyzer script
            results = self.model.track(frame, persist=True, verbose=False, conf=0.05, iou=0.3, imgsz=640)
            
            detections = []
            if results and len(results) > 0 and results[0].boxes is not None:
                boxes       = results[0].boxes.xyxy.cpu().numpy()
                confs       = results[0].boxes.conf.cpu().numpy()
                classes     = results[0].boxes.cls.int().cpu().tolist()
                tracker_ids = (
                    results[0].boxes.id.int().cpu().tolist()
                    if results[0].boxes.id is not None
                    else [None] * len(boxes)
                )

                for box, conf, cls, tid in zip(boxes, confs, classes, tracker_ids):
                    if conf < 0.05: continue
                    x1, y1, x2, y2 = map(int, box)
                    if x2 <= x1 or y2 <= y1: continue
                    cb = (x1, y1, x2, y2)
                    detections.append({
                        "box": cb,
                        "center": ((x1+x2)/2.0, (y1+y2)/2.0),
                        "size": (x2 - x1, y2 - y1),  # store real bbox size
                        "track_id": tid,
                        "conf": float(conf)
                    })

            # Age hens
            for number in self.hens:
                self.hens[number]["lost_frames"] += 1
                self.hens[number]["seen"] = False

            used_hens = set()
            detections.sort(key=lambda x: x["conf"], reverse=True)

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
                raw_box = det["box"]  # (x1, y1, x2, y2) raw from YOLO
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
                        # EMA-smoothed box — starts at raw detection
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

                    # EMA smooth: 40% toward new raw box, 60% keep old smooth
                    # This gives the exact tracking feel as seen in the video
                    alpha = 0.4
                    sb = data["smooth_box"]
                    data["smooth_box"] = [
                        alpha * raw_box[0] + (1 - alpha) * sb[0],
                        alpha * raw_box[1] + (1 - alpha) * sb[1],
                        alpha * raw_box[2] + (1 - alpha) * sb[2],
                        alpha * raw_box[3] + (1 - alpha) * sb[3],
                    ]

                used_hens.add(assigned)
                det["hen_number"] = assigned
                    
            # Draw results
            display_frame = frame.copy()
            visible_count = 0
            
            # First, draw EMA-smoothed boxes for all active detections
            # Using smooth_box so the rectangle FOLLOWS the comb's movement
            drawn_hens = set()
            for det in detections:
                num = det["hen_number"]
                visible_count += 1
                drawn_hens.add(num)

                # Use smoothed box from hen data (follows comb movement)
                hen_data = self.hens[num]
                sb = hen_data.get("smooth_box", list(det["box"]))
                x1, y1, x2, y2 = int(sb[0]), int(sb[1]), int(sb[2]), int(sb[3])

                # Draw tracking box — bright green, follows comb
                cv2.rectangle(display_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                
                label = f"HEN {num}"
                (w_txt, h_txt), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
                # Draw filled green rectangle for the text background
                cv2.rectangle(display_frame, (x1, max(y1 - 22, 0)), (x1 + w_txt, max(y1, 22)), (0, 255, 0), -1)
                # Draw text in black over the green rectangle
                cv2.putText(display_frame, label, (x1, max(y1 - 6, 16)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2, cv2.LINE_AA)
                            
                # Draw a small center dot so you can see the tracking point
                cx_s, cy_s = int((sb[0]+sb[2])/2), int((sb[1]+sb[3])/2)
                cv2.circle(display_frame, (cx_s, cy_s), 4, (0, 255, 0), -1)
            
            # Second, draw predicted (ghost) boxes for temporarily missing hens
            # This makes tracking robust to brief occlusions, exactly like the video
            for num, data in self.hens.items():
                if num not in drawn_hens and 0 < data["lost_frames"] <= 60:
                    lost = data["lost_frames"]
                    vx, vy = data["velocity"]

                    sb = data.get("smooth_box", None)
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

                    # Do not draw if predicted center is out of screen (meaning it actually left)
                    height, width = display_frame.shape[:2]
                    if pred_cx < 10 or pred_cx > width - 10 or pred_cy < 10 or pred_cy > height - 10:
                        continue

                    x1 = int(pred_cx - bw / 2)
                    y1 = int(pred_cy - bh / 2)
                    x2 = int(pred_cx + bw / 2)
                    y2 = int(pred_cy + bh / 2)

                    fade = max(0.2, 1.0 - lost / 60.0)
                    color_val = int(255 * fade)

                    visible_count += 1
                    cv2.rectangle(display_frame, (x1, y1), (x2, y2), (0, color_val, 255), 1)
                    label = f"HEN {num}"
                    
                    cv2.putText(display_frame, label, (x1, max(y1 - 6, 16)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, color_val, 255), 1, cv2.LINE_AA)

            # Calculate FPS and Time
            fps = self.cap.get(cv2.CAP_PROP_FPS)
            if fps <= 0: fps = 30.0
            time_s = frame_no / fps

            # Draw top-left status box
            cv2.rectangle(display_frame, (10, 10), (280, 110), (0, 0, 0), -1)
            cv2.putText(display_frame, f"TIME: {time_s:.1f}s", (20, 40), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(display_frame, f"VISIBLE HENS: {visible_count}", (20, 70), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2, cv2.LINE_AA)
            cv2.putText(display_frame, f"TOTAL HENS: {self.next_hen_number - 1}", (20, 100), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
                        
            cv2.imshow("Live Hen Tracker", display_frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                self.stop_tracking()
                break
                
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()

    def on_close(self):
        self.stop_tracking()
        self.window_open = False
        self.root.destroy()

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    # --- IMPORTANT ---
    # 1. model_path = 'backend/best.pt' (Your custom trained model)
    # 2. video_source = 0 (for webcam) OR 'test.mp4' (for a saved video)
    tracker = LiveHenTracker(model_path='backend/best.pt', video_source=0)
    tracker.run()
