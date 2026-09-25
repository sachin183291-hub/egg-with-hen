import math
import cv2
import torch
from ultralytics import YOLO


# ============================================================
# STABLE HEN TRACKING SETTINGS
# Same settings as the original working code
# ============================================================

CONF_THRESHOLD = 0.30
IOU_THRESHOLD = 0.50
IMG_SIZE = 1280  # Reverted back to 1280 so tracking works correctly

MAX_LOST_FRAMES = 180

BASE_MATCH_DISTANCE = 180
MAX_FAST_MATCH_DISTANCE = 400


class StableHenTracker:

    def __init__(self, model_path, device=None):

        # Load YOLO model
        self.model = YOLO(model_path)
        if hasattr(self.model, "set_classes") or "world" in str(model_path).lower():
            try:
                self.model.set_classes(["hen", "chicken", "bird", "poultry", "hen head", "chicken head"])
            except Exception:
                pass

        # Automatically use GPU if available
        if device is not None:
            self.device = device
        else:
            self.device = (
                0
                if torch.cuda.is_available()
                else "cpu"
            )

        # Permanent hen registry
        self.hens = {}

        # Next permanent hen number
        self.next_hen_number = 1

        # Use 640 on CPU for fast streaming without timeouts, 1280 on GPU
        self.img_size = 640 if self.device == "cpu" else 1280

    def _is_hen_detection(self, cls: int, conf: float) -> bool:
        if conf < CONF_THRESHOLD:
            return False
        names = getattr(self.model, "names", {})
        if not names or len(names) <= 1:
            return True
        raw_name = str(names.get(cls, "")).lower()
        if any(k in raw_name for k in ("hen", "comb", "bird", "chicken", "poultry", "animal")):
            return True
        if cls == 0:
            return True
        return False


    # ========================================================
    # CENTER
    # ========================================================

    @staticmethod
    def center_of(box):

        x1, y1, x2, y2 = box

        return (
            (x1 + x2) / 2.0,
            (y1 + y2) / 2.0
        )


    # ========================================================
    # BOX SIZE
    # ========================================================

    @staticmethod
    def box_size(box):

        x1, y1, x2, y2 = box

        return (
            max(1, x2 - x1),
            max(1, y2 - y1)
        )


    # ========================================================
    # DISTANCE
    # ========================================================

    @staticmethod
    def distance(p1, p2):

        return math.sqrt(
            (p1[0] - p2[0]) ** 2 +
            (p1[1] - p2[1]) ** 2
        )


    # ========================================================
    # PREDICT POSITION
    # ========================================================

    @staticmethod
    def predict_position(data):

        cx, cy = data["center"]

        vx, vy = data["velocity"]

        lost = data["lost_frames"]

        return (
            cx + vx * min(lost, 10),
            cy + vy * min(lost, 10)
        )

    # ========================================================
    # PROCESS AND SAVE H.264  (Process-First, Play-Later)
    #
    # Runs YOLO on EVERY frame (no skipping) – user's exact logic.
    # Saves annotated frames as a browser-compatible H.264 MP4
    # using imageio+ffmpeg so the browser can play at normal speed.
    # ========================================================

    def process_and_save_h264(self, video_path, output_path, progress_callback=None):
        """
        Process every frame → annotate → save as H.264 MP4 via imageio.
        The output video is browser-compatible and plays at normal speed.
        progress_callback(percent, visible_hens, total_hens) is called every 10 frames.
        """
        try:
            import imageio
        except ImportError:
            raise RuntimeError(
                "imageio not installed. Run: pip install 'imageio[ffmpeg]'"
            )

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError("Cannot open uploaded video")

        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = 25.0

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # imageio writer – H.264, browser-compatible
        writer = imageio.get_writer(
            output_path,
            fps=fps,
            codec="libx264",
            quality=None,
            output_params=["-crf", "23", "-preset", "fast", "-movflags", "+faststart"],
        )

        frame_no = 0

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                frame_no += 1

                # ── YOLO tracking (every frame, no skipping) ────────────
                results = self.model.track(
                    source=frame,
                    imgsz=self.img_size,
                    conf=CONF_THRESHOLD,
                    iou=IOU_THRESHOLD,
                    tracker="bytetrack.yaml",
                    persist=True,
                    device=self.device,
                    verbose=False,
                )
                result = results[0]

                detections = []
                if result.boxes is not None and len(result.boxes) > 0:
                    boxes       = result.boxes.xyxy.cpu().numpy()
                    confs       = result.boxes.conf.cpu().numpy()
                    classes     = result.boxes.cls.int().cpu().tolist()
                    tracker_ids = (
                        result.boxes.id.int().cpu().tolist()
                        if result.boxes.id is not None
                        else [None] * len(boxes)
                    )
                    for box, conf, cls, tid in zip(boxes, confs, classes, tracker_ids):
                        if not self._is_hen_detection(cls, conf):
                            continue
                        x1, y1, x2, y2 = map(int, box)
                        if x2 <= x1 or y2 <= y1:
                            continue
                        cb = (x1, y1, x2, y2)
                        detections.append({
                            "box":      cb,
                            "center":   self.center_of(cb),
                            "size":     self.box_size(cb),
                            "track_id": tid,
                            "conf":     float(conf),
                        })

                # Age hens
                for number in self.hens:
                    self.hens[number]["lost_frames"] += 1
                    self.hens[number]["seen"] = False

                used_hens = set()
                detections.sort(key=lambda x: x["conf"], reverse=True)

                for det in detections:
                    center     = det["center"]
                    tracker_id = det["track_id"]
                    assigned   = None

                    if tracker_id is not None:
                        for number, data in self.hens.items():
                            if number in used_hens:
                                continue
                            if data["track_id"] == tracker_id and data["lost_frames"] <= MAX_LOST_FRAMES:
                                assigned = number
                                break

                    if assigned is None:
                        best_number, best_score = None, float("inf")
                        for number, data in self.hens.items():
                            if number in used_hens or data["lost_frames"] > MAX_LOST_FRAMES:
                                continue
                            predicted = self.predict_position(data)
                            d = self.distance(center, predicted)
                            allowed = min(MAX_FAST_MATCH_DISTANCE, BASE_MATCH_DISTANCE + data["lost_frames"] * 8)
                            if d <= allowed and d < best_score:
                                best_score = d
                                best_number = number
                        if best_number is not None:
                            assigned = best_number

                    if assigned is None:
                        assigned = self.next_hen_number
                        self.next_hen_number += 1
                        self.hens[assigned] = {
                            "center": center, "previous_center": center,
                            "velocity": (0, 0), "track_id": tracker_id,
                            "lost_frames": 0, "seen": True,
                        }
                    else:
                        data = self.hens[assigned]
                        old_cx, old_cy = data["center"]
                        new_vx, new_vy = center[0] - old_cx, center[1] - old_cy
                        old_vx, old_vy = data["velocity"]
                        data["previous_center"] = data["center"]
                        data["center"] = center
                        data["velocity"] = (0.7*old_vx + 0.3*new_vx, 0.7*old_vy + 0.3*new_vy)
                        data["track_id"] = tracker_id
                        data["lost_frames"] = 0
                        data["seen"] = True

                    used_hens.add(assigned)
                    det["hen_number"] = assigned

                # ── Draw boxes ──────────────────────────────────────────
                annotated     = frame.copy()
                visible_count = 0

                for det in detections:
                    x1, y1, x2, y2 = det["box"]
                    hen_number      = det["hen_number"]
                    visible_count  += 1
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 3)
                    label = f"HEN {hen_number}"
                    font, scale, thick = cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2
                    (tw, th), _ = cv2.getTextSize(label, font, scale, thick)
                    ly = max(0, y1 - th - 10)
                    cv2.rectangle(annotated, (x1, ly), (x1 + tw + 10, y1), (0, 255, 0), -1)
                    cv2.putText(annotated, label, (x1 + 5, y1 - 5), font, scale, (0, 0, 0), thick, cv2.LINE_AA)

                # Info panel
                current_time = frame_no / fps
                cv2.rectangle(annotated, (20, 20), (700, 180), (0, 0, 0), -1)
                cv2.putText(annotated, f"TIME: {current_time:.1f}s",
                            (35, 55), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                cv2.putText(annotated, f"VISIBLE HENS: {visible_count}",
                            (35, 105), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                cv2.putText(annotated, f"TOTAL HENS: {self.next_hen_number - 1}",
                            (35, 155), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 255), 3)

                # Write frame (imageio expects RGB)
                writer.append_data(cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB))

                # Report progress every 10 frames
                if progress_callback and frame_no % 10 == 0 and total_frames > 0:
                    pct = int(frame_no / total_frames * 100)
                    progress_callback(pct, visible_count, self.next_hen_number - 1)

        finally:
            cap.release()
            writer.close()

        if progress_callback:
            progress_callback(100, 0, self.next_hen_number - 1)

    # ========================================================
    # PROCESS TO QUEUE  (Buffered WebSocket Streaming)
    # 
    # Runs YOLO on EVERY frame (no skipping) in a background thread.
    # Encoded frames are pushed to a queue.
    # The WebSocket endpoint reads from the queue at video FPS
    # so the browser sees normal-speed playback with accurate boxes.
    # ========================================================

    def process_to_queue(self, video_path, frame_queue, job_dict):

        """
        Process every frame with the user's exact tracking logic.
        Push each annotated JPEG (base64) into frame_queue.
        Push None as sentinel when done.
        Update job_dict with fps, progress, visible_hens, total_hens.
        """
        import base64
        import time

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            frame_queue.put(None)
            return

        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = 25.0

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        job_dict["fps"] = fps

        frame_no = 0

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                frame_no += 1

                # ================================================
                # YOLO TRACKING – every frame, no skipping
                # ================================================
                results = self.model.track(
                    source=frame,
                    imgsz=self.img_size,
                    conf=CONF_THRESHOLD,
                    iou=IOU_THRESHOLD,
                    tracker="bytetrack.yaml",
                    persist=True,
                    device=self.device,
                    verbose=False,
                )
                result = results[0]

                detections = []
                if result.boxes is not None and len(result.boxes) > 0:
                    boxes       = result.boxes.xyxy.cpu().numpy()
                    confs       = result.boxes.conf.cpu().numpy()
                    classes     = result.boxes.cls.int().cpu().tolist()
                    tracker_ids = (
                        result.boxes.id.int().cpu().tolist()
                        if result.boxes.id is not None
                        else [None] * len(boxes)
                    )

                    for box, conf, cls, tid in zip(boxes, confs, classes, tracker_ids):
                        if not self._is_hen_detection(cls, conf):
                            continue
                        x1, y1, x2, y2 = map(int, box)
                        if x2 <= x1 or y2 <= y1:
                            continue
                        current_box = (x1, y1, x2, y2)
                        detections.append({
                            "box":      current_box,
                            "center":   self.center_of(current_box),
                            "size":     self.box_size(current_box),
                            "track_id": tid,
                            "conf":     float(conf),
                        })

                # Age existing hens
                for number in self.hens:
                    self.hens[number]["lost_frames"] += 1
                    self.hens[number]["seen"] = False

                used_hens = set()
                detections.sort(key=lambda x: x["conf"], reverse=True)

                for det in detections:
                    center     = det["center"]
                    tracker_id = det["track_id"]
                    assigned   = None

                    # Step 1 – same YOLO track ID
                    if tracker_id is not None:
                        for number, data in self.hens.items():
                            if number in used_hens:
                                continue
                            if (
                                data["track_id"] == tracker_id
                                and data["lost_frames"] <= MAX_LOST_FRAMES
                            ):
                                assigned = number
                                break

                    # Step 2 – position + motion match
                    if assigned is None:
                        best_number, best_score = None, float("inf")
                        for number, data in self.hens.items():
                            if number in used_hens or data["lost_frames"] > MAX_LOST_FRAMES:
                                continue
                            predicted = self.predict_position(data)
                            d         = self.distance(center, predicted)
                            allowed   = min(
                                MAX_FAST_MATCH_DISTANCE,
                                BASE_MATCH_DISTANCE + data["lost_frames"] * 8,
                            )
                            if d <= allowed and d < best_score:
                                best_score  = d
                                best_number = number
                        if best_number is not None:
                            assigned = best_number

                    # Step 3 – create new hen
                    if assigned is None:
                        assigned = self.next_hen_number
                        self.next_hen_number += 1
                        self.hens[assigned] = {
                            "center":          center,
                            "previous_center": center,
                            "velocity":        (0, 0),
                            "track_id":        tracker_id,
                            "lost_frames":     0,
                            "seen":            True,
                        }
                    else:
                        data    = self.hens[assigned]
                        old_cx, old_cy = data["center"]
                        new_vx  = center[0] - old_cx
                        new_vy  = center[1] - old_cy
                        old_vx, old_vy = data["velocity"]
                        data["previous_center"] = data["center"]
                        data["center"]          = center
                        data["velocity"]        = (
                            0.7 * old_vx + 0.3 * new_vx,
                            0.7 * old_vy + 0.3 * new_vy,
                        )
                        data["track_id"]    = tracker_id
                        data["lost_frames"] = 0
                        data["seen"]        = True

                    used_hens.add(assigned)
                    det["hen_number"] = assigned

                # ================================================
                # DRAW – same as user's Colab script
                # ================================================
                annotated     = frame.copy()
                visible_count = 0

                for det in detections:
                    x1, y1, x2, y2 = det["box"]
                    hen_number      = det["hen_number"]
                    visible_count  += 1

                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 3)

                    label     = f"HEN {hen_number}"
                    font      = cv2.FONT_HERSHEY_SIMPLEX
                    scale     = 0.8
                    thickness = 2
                    (tw, th), _ = cv2.getTextSize(label, font, scale, thickness)
                    label_y   = max(0, y1 - th - 10)

                    cv2.rectangle(
                        annotated, (x1, label_y), (x1 + tw + 10, y1), (0, 255, 0), -1
                    )
                    cv2.putText(
                        annotated, label, (x1 + 5, y1 - 5),
                        font, scale, (0, 0, 0), thickness, cv2.LINE_AA,
                    )

                # Info panel
                current_time = frame_no / fps
                cv2.rectangle(annotated, (20, 20), (700, 180), (0, 0, 0), -1)
                cv2.putText(
                    annotated, f"TIME: {current_time:.1f}s",
                    (35, 55), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2,
                )
                cv2.putText(
                    annotated, f"VISIBLE HENS: {visible_count}",
                    (35, 105), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2,
                )
                cv2.putText(
                    annotated, f"TOTAL HENS: {self.next_hen_number - 1}",
                    (35, 155), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 255), 3,
                )

                # Encode to JPEG → base64
                _, buffer = cv2.imencode(
                    ".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 75]
                )
                b64 = base64.b64encode(buffer.tobytes()).decode("utf-8")

                # Update job progress
                pct = int(frame_no / total_frames * 100) if total_frames > 0 else 0
                job_dict["progress"]     = pct
                job_dict["visible_hens"] = visible_count
                job_dict["total_hens"]   = self.next_hen_number - 1

                # Push to queue (blocks if queue full → natural backpressure)
                frame_queue.put({
                    "frame":        b64,
                    "visible_hens": visible_count,
                    "total_hens":   self.next_hen_number - 1,
                    "progress":     pct,
                })

        finally:
            cap.release()
            frame_queue.put(None)  # Sentinel – always signal done

    # ========================================================
    # PROCESS SINGLE FRAME (For Live WebSocket Streaming)
    # ========================================================
    def process_frame(self, frame, frame_no=1, fps=30.0):
        import base64
        import time

        results = self.model.track(
            source=frame,
            imgsz=self.img_size,
            conf=CONF_THRESHOLD,
            iou=IOU_THRESHOLD,
            tracker="bytetrack.yaml",
            persist=True,
            device=self.device,
            verbose=False,
        )
        result = results[0]

        detections = []
        if result.boxes is not None and len(result.boxes) > 0:
            boxes       = result.boxes.xyxy.cpu().numpy()
            confs       = result.boxes.conf.cpu().numpy()
            classes     = result.boxes.cls.int().cpu().tolist()
            tracker_ids = (
                result.boxes.id.int().cpu().tolist()
                if result.boxes.id is not None
                else [None] * len(boxes)
            )

            for box, conf, cls, tid in zip(boxes, confs, classes, tracker_ids):
                if not self._is_hen_detection(cls, conf):
                    continue
                x1, y1, x2, y2 = map(int, box)
                if x2 <= x1 or y2 <= y1:
                    continue
                current_box = (x1, y1, x2, y2)
                detections.append({
                    "box":      current_box,
                    "center":   self.center_of(current_box),
                    "size":     self.box_size(current_box),
                    "track_id": tid,
                    "conf":     float(conf),
                })

        for number in self.hens:
            self.hens[number]["lost_frames"] += 1
            self.hens[number]["seen"] = False

        used_hens = set()
        detections.sort(key=lambda x: x["conf"], reverse=True)

        for det in detections:
            center     = det["center"]
            tracker_id = det["track_id"]
            assigned   = None

            if tracker_id is not None:
                for number, data in self.hens.items():
                    if number in used_hens:
                        continue
                    if data["track_id"] == tracker_id and data["lost_frames"] <= MAX_LOST_FRAMES:
                        assigned = number
                        break

            if assigned is None:
                best_number, best_score = None, float("inf")
                for number, data in self.hens.items():
                    if number in used_hens or data["lost_frames"] > MAX_LOST_FRAMES:
                        continue
                    predicted = self.predict_position(data)
                    d         = self.distance(center, predicted)
                    allowed   = min(MAX_FAST_MATCH_DISTANCE, BASE_MATCH_DISTANCE + data["lost_frames"] * 8)
                    if d <= allowed and d < best_score:
                        best_score  = d
                        best_number = number
                if best_number is not None:
                    assigned = best_number

            if assigned is None:
                assigned = self.next_hen_number
                self.next_hen_number += 1
                self.hens[assigned] = {
                    "center":          center,
                    "previous_center": center,
                    "velocity":        (0, 0),
                    "track_id":        tracker_id,
                    "lost_frames":     0,
                    "seen":            True,
                }
            else:
                data    = self.hens[assigned]
                old_cx, old_cy = data["center"]
                new_vx  = center[0] - old_cx
                new_vy  = center[1] - old_cy
                old_vx, old_vy = data["velocity"]
                data["previous_center"] = data["center"]
                data["center"]          = center
                data["velocity"]        = (0.7 * old_vx + 0.3 * new_vx, 0.7 * old_vy + 0.3 * new_vy)
                data["track_id"]    = tracker_id
                data["lost_frames"] = 0
                data["seen"]        = True

            used_hens.add(assigned)
            det["hen_number"] = assigned

        annotated     = frame.copy()
        visible_count = 0

        for det in detections:
            x1, y1, x2, y2 = det["box"]
            hen_number      = det["hen_number"]
            visible_count  += 1

            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 3)

            label     = f"HEN {hen_number}"
            font      = cv2.FONT_HERSHEY_SIMPLEX
            scale     = 0.8
            thickness = 2
            (tw, th), _ = cv2.getTextSize(label, font, scale, thickness)
            label_y   = max(0, y1 - th - 10)

            cv2.rectangle(annotated, (x1, label_y), (x1 + tw + 10, y1), (0, 255, 0), -1)
            cv2.putText(annotated, label, (x1 + 5, y1 - 5), font, scale, (0, 0, 0), thickness, cv2.LINE_AA)

        current_time = frame_no / fps
        cv2.rectangle(annotated, (20, 20), (700, 180), (0, 0, 0), -1)
        cv2.putText(annotated, f"TIME: {current_time:.1f}s", (35, 55), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(annotated, f"VISIBLE HENS: {visible_count}", (35, 105), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(annotated, f"TOTAL HENS: {self.next_hen_number - 1}", (35, 155), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 255), 3)

        _, buffer = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
        b64 = base64.b64encode(buffer.tobytes()).decode("utf-8")

        return b64, visible_count, self.next_hen_number - 1

    # ========================================================
    # PROCESS AND SAVE  (Solution 1 – Process First, Play Later)
    # Exact same logic as the user's Colab script.
    # Every frame is processed by YOLO – no skipping.
    # Saves a fully-annotated MP4 that can be played at normal speed.
    # ========================================================

    def process_and_save(self, video_path, output_path, progress_callback=None):
        """
        Process every frame with YOLO tracking (identical to the Colab script),
        write annotated frames to output_path as an MP4, and call
        progress_callback(percent, visible_hens, total_hens) periodically.
        """

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError("Cannot open uploaded video")

        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = 30

        width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # Use mp4v codec (universally available with OpenCV on Windows)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

        if not out.isOpened():
            cap.release()
            raise RuntimeError("Cannot create output video writer")

        frame_no = 0

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                frame_no += 1

                # ================================================
                # YOLO TRACKING – every frame, no skipping
                # ================================================
                results = self.model.track(
                    source=frame,
                    imgsz=self.img_size,
                    conf=CONF_THRESHOLD,
                    iou=IOU_THRESHOLD,
                    tracker="bytetrack.yaml",
                    persist=True,
                    device=self.device,
                    verbose=False,
                )
                result = results[0]

                detections = []
                if result.boxes is not None and len(result.boxes) > 0:
                    boxes       = result.boxes.xyxy.cpu().numpy()
                    confs       = result.boxes.conf.cpu().numpy()
                    classes     = result.boxes.cls.int().cpu().tolist()
                    tracker_ids = (
                        result.boxes.id.int().cpu().tolist()
                        if result.boxes.id is not None
                        else [None] * len(boxes)
                    )

                    for box, conf, cls, tid in zip(boxes, confs, classes, tracker_ids):
                        if not self._is_hen_detection(cls, conf):
                            continue
                        x1, y1, x2, y2 = map(int, box)
                        if x2 <= x1 or y2 <= y1:
                            continue
                        current_box = (x1, y1, x2, y2)
                        detections.append({
                            "box":      current_box,
                            "center":   self.center_of(current_box),
                            "size":     self.box_size(current_box),
                            "track_id": tid,
                            "conf":     float(conf),
                        })

                # Age all existing hens
                for number in self.hens:
                    self.hens[number]["lost_frames"] += 1
                    self.hens[number]["seen"] = False

                used_hens = set()
                detections.sort(key=lambda x: x["conf"], reverse=True)

                for det in detections:
                    center     = det["center"]
                    tracker_id = det["track_id"]
                    assigned   = None

                    # Step 1 – same YOLO track ID
                    if tracker_id is not None:
                        for number, data in self.hens.items():
                            if number in used_hens:
                                continue
                            if (
                                data["track_id"] == tracker_id
                                and data["lost_frames"] <= MAX_LOST_FRAMES
                            ):
                                assigned = number
                                break

                    # Step 2 – position + motion match
                    if assigned is None:
                        best_number, best_score = None, float("inf")
                        for number, data in self.hens.items():
                            if number in used_hens or data["lost_frames"] > MAX_LOST_FRAMES:
                                continue
                            predicted = self.predict_position(data)
                            d         = self.distance(center, predicted)
                            allowed   = min(
                                MAX_FAST_MATCH_DISTANCE,
                                BASE_MATCH_DISTANCE + data["lost_frames"] * 8,
                            )
                            if d <= allowed and d < best_score:
                                best_score  = d
                                best_number = number
                        if best_number is not None:
                            assigned = best_number

                    # Step 3 – create new hen
                    if assigned is None:
                        assigned = self.next_hen_number
                        self.next_hen_number += 1
                        self.hens[assigned] = {
                            "center":          center,
                            "previous_center": center,
                            "velocity":        (0, 0),
                            "track_id":        tracker_id,
                            "lost_frames":     0,
                            "seen":            True,
                        }
                    else:
                        data    = self.hens[assigned]
                        old_cx, old_cy = data["center"]
                        new_vx  = center[0] - old_cx
                        new_vy  = center[1] - old_cy
                        old_vx, old_vy = data["velocity"]
                        data["previous_center"] = data["center"]
                        data["center"]          = center
                        data["velocity"]        = (
                            0.7 * old_vx + 0.3 * new_vx,
                            0.7 * old_vy + 0.3 * new_vy,
                        )
                        data["track_id"]    = tracker_id
                        data["lost_frames"] = 0
                        data["seen"]        = True

                    used_hens.add(assigned)
                    det["hen_number"] = assigned

                # ================================================
                # DRAW – same as Colab script
                # ================================================
                annotated     = frame.copy()
                visible_count = 0

                for det in detections:
                    x1, y1, x2, y2 = det["box"]
                    hen_number      = det["hen_number"]
                    visible_count  += 1

                    # Green bounding box
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 3)

                    # Label
                    label     = f"HEN {hen_number}"
                    font      = cv2.FONT_HERSHEY_SIMPLEX
                    scale     = 0.8
                    thickness = 2
                    (tw, th), _ = cv2.getTextSize(label, font, scale, thickness)
                    label_y   = max(0, y1 - th - 10)

                    cv2.rectangle(
                        annotated,
                        (x1, label_y),
                        (x1 + tw + 10, y1),
                        (0, 255, 0),
                        -1,
                    )
                    cv2.putText(
                        annotated,
                        label,
                        (x1 + 5, y1 - 5),
                        font,
                        scale,
                        (0, 0, 0),
                        thickness,
                        cv2.LINE_AA,
                    )

                # Info panel (top-left) – same as Colab script
                current_time = frame_no / fps
                cv2.rectangle(annotated, (20, 20), (700, 180), (0, 0, 0), -1)
                cv2.putText(
                    annotated,
                    f"TIME: {current_time:.1f}s",
                    (35, 55),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2,
                )
                cv2.putText(
                    annotated,
                    f"VISIBLE HENS: {visible_count}",
                    (35, 105),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2,
                )
                cv2.putText(
                    annotated,
                    f"TOTAL HENS: {self.next_hen_number - 1}",
                    (35, 155),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 255), 3,
                )

                out.write(annotated)

                # Report progress every 10 frames
                if progress_callback and frame_no % 10 == 0 and total_frames > 0:
                    pct = int(frame_no / total_frames * 100)
                    progress_callback(pct, visible_count, self.next_hen_number - 1)

        finally:
            cap.release()
            out.release()

        # Final progress report
        if progress_callback:
            progress_callback(100, 0, self.next_hen_number - 1)

    # ========================================================
    # GENERATE WS STREAM (legacy – kept for reference)
    # ========================================================

    def generate_ws_stream(self, video_path, counts_dict, job_id):
        import base64
        import time

        cap = cv2.VideoCapture(video_path)

        if not cap.isOpened():
            return
            
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = 30
            
        frame_no = 0
        
        # We skip YOLO processing on 3 out of 4 frames to keep the video
        # running at "normal speed" on CPU, relying on velocity prediction!
        PROCESS_EVERY_N_FRAMES = 4 

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                    
                frame_no += 1
                start_time = time.time()

                # ==================================
                # YOLO TRACKING (EVERY FRAME)
                # ==================================
                results = self.model.track(
                    source=frame,
                    imgsz=IMG_SIZE,
                    conf=CONF_THRESHOLD,
                    iou=IOU_THRESHOLD,
                    tracker="bytetrack.yaml",
                    persist=True,
                    device=self.device,
                    verbose=False
                )
                result = results[0]

                detections = []
                if result.boxes is not None and len(result.boxes) > 0:
                    boxes = result.boxes.xyxy.cpu().numpy()
                    confs = result.boxes.conf.cpu().numpy()
                    classes = result.boxes.cls.int().cpu().tolist()
                    tracker_ids = result.boxes.id.int().cpu().tolist() if result.boxes.id is not None else [None] * len(boxes)

                    for box, conf, cls, tid in zip(boxes, confs, classes, tracker_ids):
                        if cls != 0 or conf < CONF_THRESHOLD:
                            continue
                        x1, y1, x2, y2 = map(int, box)
                        if x2 <= x1 or y2 <= y1:
                            continue
                        current_box = (x1, y1, x2, y2)
                        detections.append({
                            "box": current_box,
                            "center": self.center_of(current_box),
                            "size": self.box_size(current_box),
                            "track_id": tid,
                            "conf": float(conf)
                        })

                # Age existing hens
                for number in self.hens:
                    self.hens[number]["lost_frames"] += 1
                    self.hens[number]["seen"] = False

                used_hens = set()
                detections.sort(key=lambda x: x["conf"], reverse=True)

                # Match
                for det in detections:
                    center = det["center"]
                    tracker_id = det["track_id"]
                    assigned = None

                    if tracker_id is not None:
                        for number, data in self.hens.items():
                            if number in used_hens: continue
                            if data["track_id"] == tracker_id and data["lost_frames"] <= MAX_LOST_FRAMES:
                                assigned = number
                                break

                    if assigned is None:
                        best_number, best_score = None, float("inf")
                        for number, data in self.hens.items():
                            if number in used_hens or data["lost_frames"] > MAX_LOST_FRAMES:
                                continue
                            predicted = self.predict_position(data)
                            d = self.distance(center, predicted)
                            allowed = min(MAX_FAST_MATCH_DISTANCE, BASE_MATCH_DISTANCE + (data["lost_frames"] * 8))
                            if d <= allowed and d < best_score:
                                best_score = d
                                best_number = number
                        if best_number is not None:
                            assigned = best_number

                    if assigned is None:
                        assigned = self.next_hen_number
                        self.next_hen_number += 1
                        self.hens[assigned] = {
                            "center": center, "previous_center": center, "velocity": (0, 0),
                            "track_id": tracker_id, "lost_frames": 0, "seen": True, "box": det["box"]
                        }
                    else:
                        data = self.hens[assigned]
                        new_vx, new_vy = center[0] - data["center"][0], center[1] - data["center"][1]
                        old_vx, old_vy = data["velocity"]
                        data["previous_center"] = data["center"]
                        data["center"] = center
                        data["velocity"] = (0.7 * old_vx + 0.3 * new_vx, 0.7 * old_vy + 0.3 * new_vy)
                        data["track_id"] = tracker_id
                        data["lost_frames"] = 0
                        data["seen"] = True
                        data["box"] = det["box"]

                    used_hens.add(assigned)
                    det["hen_number"] = assigned
                
                # Update external counts state
                if job_id in counts_dict:
                    visible_count = len([h for h in self.hens.values() if h["seen"]])
                    counts_dict[job_id]["visible_hens"] = visible_count
                    counts_dict[job_id]["total_hens"] = self.next_hen_number - 1

                # Draw
                for number, data in self.hens.items():
                    if data["seen"] and "box" in data:
                        x1, y1, x2, y2 = data["box"]
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        cv2.putText(frame, f"ID: {number}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                
                # Draw total count on the right side of the video
                text = f"Total Hens: {self.next_hen_number - 1}"
                h, w = frame.shape[:2]
                (text_width, text_height), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)
                cv2.rectangle(frame, (w - text_width - 30, 20), (w - 10, 70), (0, 0, 0), -1)
                cv2.putText(frame, text, (w - text_width - 20, 55), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

                # Encode to Base64
                ret_img, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
                if ret_img:
                    frame_bytes = buffer.tobytes()
                    b64_str = base64.b64encode(frame_bytes).decode('utf-8')
                    
                    # Yield data for the WebSocket!
                    yield b64_str, counts_dict[job_id]["visible_hens"], counts_dict[job_id]["total_hens"]
                    
                # To maintain normal speed feeling, sleep slightly if processing was too fast
                processing_time = time.time() - start_time
                target_time = 1.0 / fps
                if processing_time < target_time:
                    time.sleep(target_time - processing_time)

        finally:
            cap.release()

    def process_video(
        self,
        video_path,
        progress_callback=None
    ):

        cap = cv2.VideoCapture(video_path)

        if not cap.isOpened():

            raise RuntimeError(
                "Cannot open uploaded video"
            )


        fps = cap.get(
            cv2.CAP_PROP_FPS
        )

        if fps <= 0:

            fps = 30


        total_frames = int(
            cap.get(
                cv2.CAP_PROP_FRAME_COUNT
            )
        )


        frame_no = 0
        
        # Set up output video writer
        output_path = video_path.replace(".mp4", "_output.mp4").replace(".MP4", "_output.mp4")
        if "_output" not in output_path:
            output_path += "_output.mp4"
            
        out = None

        try:

            # =================================================
            # FRAME LOOP
            # =================================================

            while True:

                ret, frame = cap.read()

                if not ret:
                    break


                if out is None:
                    h, w = frame.shape[:2]
                    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                    out = cv2.VideoWriter(output_path, fourcc, fps, (w, h))

                frame_no += 1


                # =================================================
                # YOLO + BYTE TRACK
                # Same tracking call as original code
                # =================================================

                results = self.model.track(

                    source=frame,

                    imgsz=IMG_SIZE,

                    conf=CONF_THRESHOLD,

                    iou=IOU_THRESHOLD,

                    tracker="bytetrack.yaml",

                    persist=True,

                    device=self.device,

                    verbose=False
                )


                result = results[0]


                # =================================================
                # DETECTIONS
                # =================================================

                detections = []


                if (
                    result.boxes is not None
                    and len(result.boxes) > 0
                ):


                    boxes = (
                        result.boxes.xyxy
                        .cpu()
                        .numpy()
                    )


                    confs = (
                        result.boxes.conf
                        .cpu()
                        .numpy()
                    )


                    classes = (
                        result.boxes.cls
                        .int()
                        .cpu()
                        .tolist()
                    )


                    # Tracker IDs

                    if result.boxes.id is not None:

                        tracker_ids = (
                            result.boxes.id
                            .int()
                            .cpu()
                            .tolist()
                        )

                    else:

                        tracker_ids = (
                            [None]
                            * len(boxes)
                        )


                    # =================================================
                    # PROCESS DETECTIONS
                    # =================================================

                    for (
                        box,
                        conf,
                        cls,
                        tid
                    ) in zip(
                        boxes,
                        confs,
                        classes,
                        tracker_ids
                    ):


                        # ONLY HEN_COMB
                        if cls != 0:
                            continue


                        # CONFIDENCE FILTER
                        if conf < CONF_THRESHOLD:
                            continue


                        x1, y1, x2, y2 = map(
                            int,
                            box
                        )


                        if x2 <= x1:
                            continue


                        if y2 <= y1:
                            continue


                        current_box = (
                            x1,
                            y1,
                            x2,
                            y2
                        )


                        detections.append({

                            "box":
                                current_box,

                            "center":
                                self.center_of(
                                    current_box
                                ),

                            "size":
                                self.box_size(
                                    current_box
                                ),

                            "track_id":
                                tid,

                            "conf":
                                float(conf)
                        })


                # =================================================
                # AGE EXISTING HENS
                # =================================================

                for number in self.hens:

                    self.hens[number][
                        "lost_frames"
                    ] += 1

                    self.hens[number][
                        "seen"
                    ] = False


                # =================================================
                # USED HENS
                # =================================================

                used_hens = set()


                # =================================================
                # HIGH CONFIDENCE FIRST
                # =================================================

                detections.sort(

                    key=lambda x:
                        x["conf"],

                    reverse=True
                )


                # =================================================
                # MATCH EACH DETECTION
                # =================================================

                for det in detections:


                    center = det[
                        "center"
                    ]


                    tracker_id = det[
                        "track_id"
                    ]


                    assigned = None


                    # =================================================
                    # STEP 1
                    # SAME YOLO TRACKER ID
                    # =================================================

                    if tracker_id is not None:


                        for (
                            number,
                            data
                        ) in self.hens.items():


                            if number in used_hens:
                                continue


                            if (
                                data["track_id"]
                                == tracker_id
                            ):


                                if (
                                    data[
                                        "lost_frames"
                                    ]
                                    <= MAX_LOST_FRAMES
                                ):

                                    assigned = number


                                break


                    # =================================================
                    # STEP 2
                    # POSITION + MOTION MATCH
                    # =================================================

                    if assigned is None:


                        best_number = None

                        best_score = (
                            float("inf")
                        )


                        for (
                            number,
                            data
                        ) in self.hens.items():


                            if number in used_hens:
                                continue


                            if (
                                data[
                                    "lost_frames"
                                ]
                                > MAX_LOST_FRAMES
                            ):
                                continue


                            # Predict position

                            predicted = (
                                self.predict_position(
                                    data
                                )
                            )


                            # Distance

                            d = self.distance(

                                center,

                                predicted
                            )


                            # Dynamic movement tolerance

                            allowed = min(

                                MAX_FAST_MATCH_DISTANCE,

                                BASE_MATCH_DISTANCE
                                +
                                (
                                    data[
                                        "lost_frames"
                                    ]
                                    * 8
                                )
                            )


                            if d <= allowed:


                                score = d


                                if (
                                    score
                                    < best_score
                                ):

                                    best_score = (
                                        score
                                    )

                                    best_number = (
                                        number
                                    )


                        if (
                            best_number
                            is not None
                        ):

                            assigned = (
                                best_number
                            )


                    # =================================================
                    # STEP 3
                    # CREATE NEW HEN
                    # =================================================

                    if assigned is None:


                        assigned = (
                            self.next_hen_number
                        )


                        self.next_hen_number += 1


                        self.hens[
                            assigned
                        ] = {

                            "center":
                                center,

                            "previous_center":
                                center,

                            "velocity":
                                (0, 0),

                            "track_id":
                                tracker_id,

                            "lost_frames":
                                0,

                            "seen":
                                True,
                                
                            "box": det["box"]
                        }


                    # =================================================
                    # EXISTING HEN
                    # UPDATE
                    # =================================================

                    else:


                        data = self.hens[
                            assigned
                        ]


                        old_center = (
                            data["center"]
                        )


                        # New velocity

                        new_vx = (
                            center[0]
                            -
                            old_center[0]
                        )


                        new_vy = (
                            center[1]
                            -
                            old_center[1]
                        )


                        # Old velocity

                        old_vx, old_vy = (
                            data["velocity"]
                        )


                        # Smooth motion

                        smooth_vx = (

                            0.7 * old_vx

                            +

                            0.3 * new_vx
                        )


                        smooth_vy = (

                            0.7 * old_vy

                            +

                            0.3 * new_vy
                        )


                        data[
                            "previous_center"
                        ] = old_center


                        data[
                            "center"
                        ] = center


                        data[
                            "velocity"
                        ] = (
                            smooth_vx,
                            smooth_vy
                        )


                        data[
                            "track_id"
                        ] = tracker_id


                        data[
                            "lost_frames"
                        ] = 0


                        data[
                            "seen"
                        ] = True
                        
                        data[
                            "box"
                        ] = det["box"]


                    # Mark this hen as used

                    used_hens.add(
                        assigned
                    )


                    # Permanent number

                    det[
                        "hen_number"
                    ] = assigned


                # =================================================
                # DRAW BOXES AND LIVE COUNT ON VIDEO FRAME
                # =================================================
                
                for number, data in self.hens.items():
                    if data["seen"] and "box" in data:
                        x1, y1, x2, y2 = data["box"]
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        cv2.putText(frame, f"ID: {number}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                        
                # Draw total count on the right side
                text = f"Total Hens: {self.next_hen_number - 1}"
                
                h, w = frame.shape[:2]
                # Get text size to right-align
                (text_width, text_height), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)
                cv2.putText(frame, text, (w - text_width - 20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                
                if out is not None:
                    out.write(frame)

                # =================================================
                # LIVE COUNT
                # =================================================

                visible_count = len(
                    detections
                )


                current_time = (
                    frame_no / fps
                )


                if total_frames > 0:

                    progress = (
                        frame_no
                        /
                        total_frames
                        *
                        100
                    )

                else:

                    progress = 0


                # =================================================
                # SEND LIVE UPDATE
                # =================================================

                if (
                    progress_callback
                    is not None
                ):


                    progress_callback({

                        "type":
                            "progress",

                        "frame":
                            frame_no,

                        "total_frames":
                            total_frames,

                        "time":
                            round(
                                current_time,
                                2
                            ),

                        "visible_hens":
                            visible_count,

                        "total_hens":
                            (
                                self.next_hen_number
                                - 1
                            ),

                        "progress":
                            round(
                                progress,
                                2
                            )
                    })


            # =================================================
            # FINAL RESULT
            # =================================================

            final_count = (
                self.next_hen_number
                - 1
            )


            final_result = {

                "type":
                    "completed",

                "total_hens":
                    final_count,

                "frames_processed":
                    frame_no,

                "duration_seconds":
                    round(
                        frame_no / fps,
                        2
                    ),
                    
                "output_video": output_path
            }


            if (
                progress_callback
                is not None
            ):

                progress_callback(
                    final_result
                )


            return final_result


        finally:

            cap.release()
            if out is not None:
                out.release()
