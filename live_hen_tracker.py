"""
GioTag - Real-Time Hen & Hen Comb Tracking System
==================================================
Inspired by Real-Time Object Detection, Tracking & Traffic Analytics:
- Multi-target Detection (Hen Comb & Hen Body using YOLOv8)
- Real-time Object Tracking & Permanent Counting (ByteTrack + Motion Prediction)
- Live Analytics Dashboard (Broadcast-Grade On-Screen HUD Overlay)
- Motion Trajectory Trails & Ghost Recovery for Occlusions
- Fast Inference (Configurable resolution: 320px Nano / 640px Standard)
- FFmpeg Integration for Web-Ready Video Export (H.264 / MP4)
- Multi-Source Support: Live Webcam, Video Files, RTSP Streams
- Interactive Controls: Hotkeys [Q], [SPACE], [S], [T], [H], [L], [R]

Tech Stack: Python | YOLOv8 | OpenCV | FFmpeg | Tkinter
"""

import os
import sys
import time
import math
import shutil
import argparse
import subprocess
from collections import deque
from threading import Thread

import cv2
import numpy as np
from ultralytics import YOLO

# GUI imports
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ─── FFmpeg Resolver ─────────────────────────────────────────────────────────
def get_ffmpeg_executable():
    """Locate FFmpeg executable via imageio_ffmpeg or system PATH."""
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except ImportError:
        pass
    which_ffmpeg = shutil.which("ffmpeg")
    if which_ffmpeg:
        return which_ffmpeg
    return None


def convert_to_web_ready_video(input_path, output_path):
    """Convert an MP4 video into web-ready H.264 format using FFmpeg."""
    ffmpeg_exe = get_ffmpeg_executable()
    if not ffmpeg_exe:
        print("[WARNING] FFmpeg not found. Video saved in OpenCV default format.")
        if input_path != output_path:
            shutil.copy2(input_path, output_path)
        return output_path

    cmd = [
        ffmpeg_exe, "-y",
        "-i", input_path,
        "-vcodec", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "fast",
        "-crf", "22",
        output_path
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        if os.path.exists(input_path) and input_path != output_path:
            try:
                os.remove(input_path)
            except OSError:
                pass
        return output_path
    except Exception as e:
        print(f"[ERROR] FFmpeg conversion failed: {e}")
        if input_path != output_path and os.path.exists(input_path):
            shutil.copy2(input_path, output_path)
        return output_path


# ─── Default Paths & Model Candidates ────────────────────────────────────────
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_MODEL_CANDIDATES = [
    os.path.join(_THIS_DIR, "backend", "best.pt"),
    os.path.join(_THIS_DIR, "best.pt"),
    os.path.join(_THIS_DIR, "weights", "best.pt"),
    os.path.join(_THIS_DIR, "yolov8n.pt"),
]


def resolve_model_path(preferred_path=None):
    if preferred_path and os.path.exists(preferred_path):
        return preferred_path
    for cand in _MODEL_CANDIDATES:
        if os.path.exists(cand):
            return cand
    return "yolov8n.pt"


def find_default_video():
    """Look for sample or raw drone/poultry videos in the repository."""
    candidates = [
        os.path.join(_THIS_DIR, "uploads", "DJI_20260911145052_0001_S.MP4"),
        os.path.join(_THIS_DIR, "uploads", "DJI_20260911145654_0003_S.MP4"),
        os.path.join(_THIS_DIR, "sample_video.mp4"),
        os.path.join(_THIS_DIR, "reference_video.mp4"),
        os.path.join(_THIS_DIR, "backend", "tiny_test.mp4"),
    ]
    for c in candidates:
        if os.path.exists(c) and os.path.getsize(c) > 10000:
            return c
    return ""


# ─── Live Hen & Comb Tracker Core Engine ─────────────────────────────────────
class LiveHenTracker:
    def __init__(
        self,
        model_path="backend/best.pt",
        video_source=0,
        imgsz=640,
        conf_thresh=0.12,
        iou_thresh=0.35,
        show_trails=True,
        show_hud=True,
        show_counting_line=True,
        record_output=False,
    ):
        self.model_path = resolve_model_path(model_path)
        self.video_source = video_source
        self.imgsz = imgsz
        self.conf_thresh = conf_thresh
        self.iou_thresh = iou_thresh
        self.show_trails = show_trails
        self.show_hud = show_hud
        self.show_counting_line = show_counting_line
        self.record_output = record_output

        self.cap = None
        self.is_running = False
        self.paused = False
        self.window_name = "GioTag - Real-Time Hen & Comb Tracking"

        # Output paths
        self.output_dir = os.path.join(_THIS_DIR, "outputs")
        os.makedirs(self.output_dir, exist_ok=True)
        self.video_writer = None
        self.raw_record_path = None
        self.final_record_path = None

        # Tracking state
        self.hens = {}
        self.next_hen_number = 1
        self.total_counted = 0
        self.line_in_count = 0
        self.line_out_count = 0

        # UI & Telemetry
        self.toast_message = ""
        self.toast_expiry = 0
        self.fps_history = deque(maxlen=25)
        self.conf_history = deque(maxlen=25)

        # Load & Warm up AI Model
        print(f"Loading YOLO model from: {self.model_path}...")
        self.model = YOLO(self.model_path)
        print("Warming up AI inference engine...")
        dummy_img = np.zeros((320, 320, 3), dtype=np.uint8)
        for _ in range(2):
            self.model(dummy_img, verbose=False, imgsz=320)
        print("AI Model ready!\n")

    def show_toast(self, text, duration=2.5):
        """Display an on-screen toast notification."""
        self.toast_message = text
        self.toast_expiry = time.time() + duration

    def save_snapshot(self, frame):
        """Save high-resolution annotated screenshot to outputs directory."""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"snapshot_{timestamp}.jpg"
        save_path = os.path.join(self.output_dir, filename)
        cv2.imwrite(save_path, frame)
        print(f"[SNAPSHOT] Saved: {save_path}")
        self.show_toast(f"SNAPSHOT SAVED: {filename}", 3.0)
        return save_path

    def draw_rounded_rect(self, img, pt1, pt2, color, thickness=1, r=8):
        """Draw a rectangle with rounded corners."""
        x1, y1 = pt1
        x2, y2 = pt2
        r = min(r, abs(x2 - x1) // 2, abs(y2 - y1) // 2)
        if r <= 0:
            cv2.rectangle(img, pt1, pt2, color, thickness)
            return

        # Straight lines
        cv2.line(img, (x1 + r, y1), (x2 - r, y1), color, thickness, cv2.LINE_AA)
        cv2.line(img, (x1 + r, y2), (x2 - r, y2), color, thickness, cv2.LINE_AA)
        cv2.line(img, (x1, y1 + r), (x1, y2 - r), color, thickness, cv2.LINE_AA)
        cv2.line(img, (x2, y1 + r), (x2, y2 - r), color, thickness, cv2.LINE_AA)
        # Corners
        cv2.ellipse(img, (x1 + r, y1 + r), (r, r), 180, 0, 90, color, thickness, cv2.LINE_AA)
        cv2.ellipse(img, (x2 - r, y1 + r), (r, r), 270, 0, 90, color, thickness, cv2.LINE_AA)
        cv2.ellipse(img, (x1 + r, y2 - r), (r, r), 90, 0, 90, color, thickness, cv2.LINE_AA)
        cv2.ellipse(img, (x2 - r, y2 - r), (r, r), 0, 0, 90, color, thickness, cv2.LINE_AA)

    def draw_hud(
        self,
        display_frame,
        visible_count,
        total_unique,
        fps_val,
        session_time,
        frame_no,
        total_frames,
        avg_conf,
        counting_line_y,
    ):
        """Render a broadcast-grade on-screen HUD analytics dashboard."""
        fh, fw = display_frame.shape[:2]

        # ─── 1. Top Header Glass Bar ───
        overlay = display_frame.copy()
        cv2.rectangle(overlay, (0, 0), (fw, 46), (15, 20, 26), -1)

        # ─── 2. Analytics Telemetry Card (Top-Left) ───
        card_w, card_h = 330, 185
        cv2.rectangle(overlay, (15, 60), (15 + card_w, 60 + card_h), (12, 16, 22), -1)

        # ─── 3. Bottom Hotkey Legend Bar ───
        bar_w = min(780, fw - 30)
        bx1 = (fw - bar_w) // 2
        bx2 = bx1 + bar_w
        cv2.rectangle(overlay, (bx1, fh - 40), (bx2, fh - 10), (15, 20, 26), -1)

        # Alpha blend HUD overlay onto frame
        cv2.addWeighted(overlay, 0.75, display_frame, 0.25, 0, display_frame)

        # Header accent bottom border
        cv2.line(display_frame, (0, 46), (fw, 46), (0, 230, 115), 2)
        # Header title
        cv2.putText(
            display_frame,
            "GIOTAG AI  *  REAL-TIME HEN & COMB TRACKER",
            (22, 31),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.72,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        # Status badge (Live / Rec)
        status_text = "[* REC]" if self.record_output else "[* LIVE]"
        badge_color = (0, 0, 220) if self.record_output else (0, 190, 0)
        (tw, th), _ = cv2.getTextSize(status_text, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
        rx = fw - tw - 25
        cv2.rectangle(display_frame, (rx - 8, 10), (rx + tw + 8, 38), badge_color, -1)
        cv2.putText(
            display_frame,
            status_text,
            (rx, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        # Telemetry Card Outline & Title
        cv2.rectangle(display_frame, (15, 60), (15 + card_w, 60 + card_h), (50, 180, 110), 1)
        cv2.putText(
            display_frame,
            "LIVE TELEMETRY & ANALYTICS",
            (25, 82),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            (0, 230, 255),
            1,
            cv2.LINE_AA,
        )
        cv2.line(display_frame, (25, 90), (15 + card_w - 10, 90), (60, 80, 100), 1)

        # Telemetry Metrics
        speed_color = (0, 255, 128) if fps_val >= 18 else ((0, 220, 255) if fps_val >= 10 else (0, 140, 255))
        frame_str = f"Frame {frame_no}/{total_frames}" if total_frames > 0 else f"Frame {frame_no}"

        metrics = [
            ("VISIBLE HENS:", f"{visible_count}", (0, 255, 0)),
            ("TOTAL UNIQUE:", f"{total_unique}", (0, 230, 255)),
            ("AI FPS:", f"{fps_val:.1f} FPS", speed_color),
            ("SESSION TIME:", f"{session_time:.1f}s ({frame_str})", (220, 220, 220)),
            ("AVG CONFIDENCE:", f"{avg_conf:.1%}", (180, 255, 180)),
            ("LINE CROSSINGS:", f"IN: {self.line_in_count} | OUT: {self.line_out_count}", (255, 190, 80)),
        ]

        y = 114
        for label, val, col in metrics:
            cv2.putText(display_frame, label, (25, y), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (170, 180, 190), 1, cv2.LINE_AA)
            cv2.putText(display_frame, val, (175, y), cv2.FONT_HERSHEY_SIMPLEX, 0.50, col, 2, cv2.LINE_AA)
            y += 22

        # Bottom hotkeys bar
        cv2.rectangle(display_frame, (bx1, fh - 40), (bx2, fh - 10), (70, 90, 110), 1)
        hotkeys_msg = "[Q] Quit | [SPACE] Pause | [S] Snapshot | [T] Trails | [H] HUD | [L] Line | [R] Reset"
        cv2.putText(
            display_frame,
            hotkeys_msg,
            (bx1 + 18, fh - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.46,
            (220, 230, 240),
            1,
            cv2.LINE_AA,
        )

        # Counting Line
        if self.show_counting_line and counting_line_y is not None:
            ly = int(counting_line_y)
            cv2.line(display_frame, (0, ly), (fw, ly), (0, 220, 255), 2, cv2.LINE_AA)
            cv2.putText(
                display_frame,
                "<-- VIRTUAL COUNTING LINE -->",
                (fw // 2 - 135, ly - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.52,
                (0, 220, 255),
                2,
                cv2.LINE_AA,
            )

        # On-screen Toast Notification
        if time.time() < self.toast_expiry and self.toast_message:
            (msg_w, msg_h), _ = cv2.getTextSize(self.toast_message, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
            tx = (fw - msg_w) // 2
            ty = fh - 65
            cv2.rectangle(display_frame, (tx - 15, ty - 26), (tx + msg_w + 15, ty + 10), (0, 40, 20), -1)
            cv2.rectangle(display_frame, (tx - 15, ty - 26), (tx + msg_w + 15, ty + 10), (0, 255, 128), 2)
            cv2.putText(
                display_frame,
                self.toast_message,
                (tx, ty),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 255, 128),
                2,
                cv2.LINE_AA,
            )

    def is_pure_comb(self, box, frame):
        x1, y1, x2, y2 = map(int, box)
        w = x2 - x1
        h = y2 - y1
        if w <= 8 or h <= 8:
            return False
        if w > 350 or h > 350:
            return False
        return True

    def tracking_loop(self):
        """Main real-time tracking, inference, and analytics loop."""
        self.hens.clear()
        self.next_hen_number = 1
        self.line_in_count = 0
        self.line_out_count = 0
        self.fps_history.clear()
        self.conf_history.clear()

        # Open video source
        src = self.video_source
        if isinstance(src, str) and src.isdigit():
            src = int(src)

        print(f"Opening video feed: {src} ...")
        self.cap = cv2.VideoCapture(src)
        if not self.cap.isOpened():
            print(f"[ERROR] Failed to open video source: {src}")
            self.is_running = False
            return

        fps_src = self.cap.get(cv2.CAP_PROP_FPS)
        if fps_src <= 0 or fps_src > 120 or math.isnan(fps_src):
            fps_src = 30.0
        frame_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames < 0:
            total_frames = 0

        counting_line_y = frame_h * 0.55 if frame_h > 0 else 300

        # Video Recorder Setup
        if self.record_output:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            self.raw_record_path = os.path.join(self.output_dir, f"temp_rec_{timestamp}.mp4")
            self.final_record_path = os.path.join(self.output_dir, f"hen_tracking_{timestamp}.mp4")
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            self.video_writer = cv2.VideoWriter(
                self.raw_record_path, fourcc, fps_src, (frame_w, frame_h)
            )
            print(f"[RECORDING] Live session recording to: {self.final_record_path}")

        frame_no = 0
        is_live_stream = isinstance(src, int) or str(src).lower().startswith("rtsp")
        start_wall_time = time.time()
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, min(1280, frame_w), min(720, frame_h))

        EMA_ALPHA = 0.88  # Smooth box EMA weight
        prev_small_gray = None

        while self.is_running and self.cap.isOpened():
            if self.paused:
                key = cv2.waitKey(30) & 0xFF
                if key == ord(" "):
                    self.paused = False
                    self.show_toast("RESUMED", 1.5)
                elif key in (ord("q"), 27):
                    break
                elif key == ord("s"):
                    # Save current paused frame
                    if "display_frame" in locals():
                        self.save_snapshot(display_frame)
                continue

            # Playback synchronization for video files
            if not is_live_stream and total_frames > 0:
                elapsed_real = time.time() - start_wall_time
                target_frame = int(elapsed_real * fps_src)
                if target_frame < frame_no:
                    time.sleep(max(0.001, (frame_no - target_frame) / fps_src))

            ret, frame = self.cap.read()
            if not ret:
                print("End of video stream.")
                break

            frame_no += 1
            t_start = time.perf_counter()

            # ─── 0. Fast Camera Motion Compensation ───
            small_gray = cv2.cvtColor(cv2.resize(frame, (320, 180)), cv2.COLOR_BGR2GRAY).astype(np.float32)
            cam_dx, cam_dy = 0.0, 0.0
            if prev_small_gray is not None:
                shift, response = cv2.phaseCorrelate(prev_small_gray, small_gray)
                if response > 0.04 and abs(shift[0]) < 25 and abs(shift[1]) < 25:
                    cam_dx = shift[0] * (frame_w / 320.0)
                    cam_dy = shift[1] * (frame_h / 180.0)
            prev_small_gray = small_gray

            # Update all existing tracks with camera translation
            for num, data in self.hens.items():
                data["lost_frames"] += 1
                data["seen"] = False
                cx, cy = data["center"]
                data["center"] = (cx + cam_dx, cy + cam_dy)
                if "smooth_box" in data:
                    sb = data["smooth_box"]
                    data["smooth_box"] = [sb[0] + cam_dx, sb[1] + cam_dy, sb[2] + cam_dx, sb[3] + cam_dy]
                if "anchor" in data:
                    ax, ay = data["anchor"]
                    data["anchor"] = (ax + cam_dx, ay + cam_dy)

            # ─── 1. YOLO Inference ───
            results = self.model.predict(
                frame,
                verbose=False,
                conf=self.conf_thresh,
                iou=self.iou_thresh,
                imgsz=self.imgsz,
            )
            dt = time.perf_counter() - t_start
            current_fps = 1.0 / dt if dt > 0 else 30.0
            self.fps_history.append(current_fps)

            # ─── 2. Filter Detections (Strict 1-Box-Per-Hen) ───
            raw_detections = []
            if results and len(results) > 0 and results[0].boxes is not None:
                boxes_xyxy = results[0].boxes.xyxy.cpu().numpy()
                confs = results[0].boxes.conf.cpu().numpy()

                for box, conf in zip(boxes_xyxy, confs):
                    if conf < self.conf_thresh:
                        continue
                    if not self.is_pure_comb(box, frame):
                        continue
                    x1, y1, x2, y2 = map(int, box)
                    w, h = x2 - x1, y2 - y1
                    raw_detections.append({
                        "box": (x1, y1, x2, y2),
                        "center": ((x1 + x2) / 2.0, (y1 + y2) / 2.0),
                        "size": (w, h),
                        "conf": float(conf),
                        "is_comb": True,
                    })

            # Sort by confidence so compact comb boxes are preferred over any stray large boxes
            raw_detections.sort(key=lambda d: d["conf"], reverse=True)

            # Strict 1-Box-Per-Hen Deduplication (Center containment + Centroid 45px + IoU 0.30)
            detections = []
            for r_det in raw_detections:
                rx1, ry1, rx2, ry2 = r_det["box"]
                rcx, rcy = r_det["center"]
                is_duplicate = False
                for existing in detections:
                    ex1, ey1, ex2, ey2 = existing["box"]
                    ecx, ecy = existing["center"]
                    # Centroid distance check (45px radius)
                    if math.hypot(rcx - ecx, rcy - ecy) < 45:
                        is_duplicate = True
                        break
                    # Center containment check (if center of smaller is inside larger)
                    if (ex1 <= rcx <= ex2 and ey1 <= rcy <= ey2) or (rx1 <= ecx <= rx2 and ry1 <= ecy <= ry2):
                        is_duplicate = True
                        break
                    # IoU check
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
                    self.conf_history.append(r_det["conf"])

            # On frame 1, sort detections spatially so numbers start 1, 2, 3 in natural reading order
            if frame_no == 1:
                detections.sort(key=lambda d: d["center"][1] * 2.0 + d["center"][0])

            # ─── 3. Mutual Nearest Neighbor (MNN) Matching ───
            MAX_MATCH_DIST = 125.0  # Robust matching radius preventing ID drift when hens turn or peck
            det_to_hen = {}
            for d_idx, det in enumerate(detections):
                cx, cy = det["center"]
                best_num, best_dist = None, float("inf")
                for num, data in self.hens.items():
                    if data["lost_frames"] > 45:
                        continue
                    hx, hy = data["center"]
                    d = math.hypot(cx - hx, cy - hy)
                    if d <= MAX_MATCH_DIST and d < best_dist:
                        best_dist = d
                        best_num = num
                if best_num is not None:
                    det_to_hen[d_idx] = (best_num, best_dist)

            # Hen-to-Detection closest mapping
            hen_to_det = {}
            for num, data in self.hens.items():
                if data["lost_frames"] > 45:
                    continue
                hx, hy = data["center"]
                best_d_idx, best_dist = None, float("inf")
                for d_idx, det in enumerate(detections):
                    d = math.hypot(det["center"][0] - hx, det["center"][1] - hy)
                    if d <= MAX_MATCH_DIST and d < best_dist:
                        best_dist = d
                        best_d_idx = d_idx
                if best_d_idx is not None:
                    hen_to_det[num] = (best_d_idx, best_dist)

            # Accept ONLY MUTUAL matches: det prefers hen AND hen prefers det!
            matched_dets = set()
            used_hens = set()
            for d_idx, (num, dist) in det_to_hen.items():
                if num in hen_to_det and hen_to_det[num][0] == d_idx:
                    matched_dets.add(d_idx)
                    used_hens.add(num)
                    det = detections[d_idx]
                    center = det["center"]
                    raw_box = det["box"]
                    data = self.hens[num]

                    old_cx, old_cy = data["center"]
                    data["center"] = center
                    data["vel"] = (center[0] - old_cx, center[1] - old_cy)
                    data["lost_frames"] = 0
                    data["seen"] = True
                    data["hits"] = data.get("hits", 1) + 1
                    data["size"] = det["size"]
                    data["is_comb"] = det["is_comb"]

                    # Smooth bounding box EMA interpolation
                    sb = data["smooth_box"]
                    data["smooth_box"] = [
                        EMA_ALPHA * raw_box[i] + (1 - EMA_ALPHA) * sb[i]
                        for i in range(4)
                    ]
                    data["trail"].append(center)

                    # Virtual line crossing check
                    if self.show_counting_line and counting_line_y is not None:
                        ly = counting_line_y
                        if data.get("last_y", center[1]) < ly and center[1] >= ly:
                            self.line_in_count += 1
                            self.show_toast(f"HEN #{num} CROSSED [IN]", 1.5)
                        elif data.get("last_y", center[1]) > ly and center[1] <= ly:
                            self.line_out_count += 1
                            self.show_toast(f"HEN #{num} CROSSED [OUT]", 1.5)
                    data["last_y"] = center[1]

                    det["hen_number"] = num

            # ─── 4. Register Genuinely New Hens ───
            for d_idx, det in enumerate(detections):
                if d_idx in matched_dets:
                    continue

                center = det["center"]
                raw_box = det["box"]

                # Check if this detection belongs to an occluded hen within 100px
                reassigned_num = None
                closest_dist = float("inf")
                for num, data in self.hens.items():
                    if num in used_hens or data["lost_frames"] > 45:
                        continue
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
                    data["size"] = det["size"]
                    data["is_comb"] = det["is_comb"]
                    data["smooth_box"] = [float(v) for v in raw_box]
                    data["trail"].append(center)
                else:
                    # Brand new sequence number
                    num = self.next_hen_number
                    self.next_hen_number += 1
                    trail = deque(maxlen=25)
                    trail.append(center)
                    self.hens[num] = {
                        "center": center,
                        "anchor": center,
                        "vel": (0.0, 0.0),
                        "lost_frames": 0,
                        "seen": True,
                        "hits": 1,
                        "size": det["size"],
                        "smooth_box": [float(v) for v in raw_box],
                        "trail": trail,
                        "last_y": center[1],
                        "is_comb": det["is_comb"],
                    }

                used_hens.add(num)
                det["hen_number"] = num

            # ─── Frame Rendering ───
            display_frame = frame.copy()
            visible_count = len(used_hens)
            # Count only verified established hens (prevents 1-frame noise from inflating count)
            total_unique = len([h for h in self.hens.values() if h.get("hits", 0) >= (1 if frame_no <= 3 else 2)])

            # 1. Draw Motion Trajectory Trails
            if self.show_trails:
                for num, data in self.hens.items():
                    trail = data.get("trail", [])
                    if len(trail) > 1 and data["lost_frames"] <= 30:
                        pts = list(trail)
                        for idx in range(1, len(pts)):
                            thickness = max(1, int(idx / len(pts) * 3.5))
                            fade = idx / len(pts)
                            # Cyan-to-green gradient trail
                            color = (int(255 * (1 - fade)), int(230 * fade), int(255 * fade))
                            pt_a = (int(pts[idx - 1][0]), int(pts[idx - 1][1]))
                            pt_b = (int(pts[idx][0]), int(pts[idx][1]))
                            cv2.line(display_frame, pt_a, pt_b, color, thickness, cv2.LINE_AA)

            # 2. Draw Active Hen Comb Tracking Bounding Boxes
            for det in detections:
                num = det["hen_number"]
                data = self.hens[num]
                sb = data["smooth_box"]
                x1, y1, x2, y2 = int(sb[0]), int(sb[1]), int(sb[2]), int(sb[3])
                conf = det["conf"]
                is_comb = det["is_comb"]

                # Neon Green for Hen Comb, Cyan for Hen Body
                box_color = (0, 255, 0) if is_comb else (0, 220, 255)
                self.draw_rounded_rect(display_frame, (x1, y1), (x2, y2), box_color, 2, r=6)

                # Text Badge above bounding box
                badge_text = f"HEN #{num} | {conf:.0%}"
                (tw, th), _ = cv2.getTextSize(badge_text, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 2)
                ty1 = max(y1 - 24, 0)
                ty2 = max(y1, 24)
                cv2.rectangle(display_frame, (x1, ty1), (x1 + tw + 8, ty2), box_color, -1)
                cv2.putText(
                    display_frame,
                    badge_text,
                    (x1 + 4, max(y1 - 6, 17)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.52,
                    (0, 0, 0),
                    2,
                    cv2.LINE_AA,
                )

                # Center tracking crosshair dot
                cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
                cv2.circle(display_frame, (cx, cy), 3, (0, 255, 0), -1)

            # 3. Draw Predicted Ghost Boxes for Briefly Occluded Hens
            for num, data in self.hens.items():
                if num not in used_hens and data.get("hits", 0) >= 3 and 0 < data["lost_frames"] <= 35:
                    lost = data["lost_frames"]
                    sb = data["smooth_box"]
                    vx, vy = data["vel"]
                    pred_x = (sb[0] + sb[2]) / 2 + vx * min(lost, 10)
                    pred_y = (sb[1] + sb[3]) / 2 + vy * min(lost, 10)
                    bw = sb[2] - sb[0]
                    bh = sb[3] - sb[1]

                    if pred_x < 10 or pred_x > frame_w - 10 or pred_y < 10 or pred_y > frame_h - 10:
                        continue

                    gx1, gy1 = int(pred_x - bw / 2), int(pred_y - bh / 2)
                    gx2, gy2 = int(pred_x + bw / 2), int(pred_y + bh / 2)

                    fade = max(0.2, 1.0 - lost / 60.0)
                    ghost_color = (0, int(160 * fade), int(255 * fade))
                    cv2.rectangle(display_frame, (gx1, gy1), (gx2, gy2), ghost_color, 1, cv2.LINE_AA)
                    cv2.putText(
                        display_frame,
                        f"HEN #{num} [PREDICTED]",
                        (gx1, max(gy1 - 6, 14)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.46,
                        ghost_color,
                        1,
                        cv2.LINE_AA,
                    )

            # 4. Draw Broadcast HUD Overlay
            avg_fps = np.mean(self.fps_history) if self.fps_history else current_fps
            avg_conf = np.mean(self.conf_history) if self.conf_history else 0.0
            session_time = frame_no / fps_src

            if self.show_hud:
                self.draw_hud(
                    display_frame,
                    visible_count,
                    total_unique,
                    avg_fps,
                    session_time,
                    frame_no,
                    total_frames,
                    avg_conf,
                    counting_line_y,
                )

            # Record frame if enabled
            if self.video_writer is not None:
                self.video_writer.write(display_frame)

            # Display in OpenCV window
            try:
                cv2.imshow(self.window_name, display_frame)
            except Exception:
                pass

            # Interactive Hotkey Controls
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):  # Quit
                break
            elif key == ord(" "):  # Pause / Resume
                self.paused = True
                self.show_toast("PAUSED [PRESS SPACE TO RESUME]", 999)
            elif key == ord("s"):  # Snapshot
                self.save_snapshot(display_frame)
            elif key == ord("t"):  # Toggle Trails
                self.show_trails = not self.show_trails
                self.show_toast(f"TRAILS: {'ON' if self.show_trails else 'OFF'}")
            elif key == ord("h"):  # Toggle HUD
                self.show_hud = not self.show_hud
                self.show_toast(f"HUD: {'ON' if self.show_hud else 'OFF'}")
            elif key == ord("l"):  # Toggle Line
                self.show_counting_line = not self.show_counting_line
                self.show_toast(f"COUNTING LINE: {'ON' if self.show_counting_line else 'OFF'}")
            elif key == ord("r"):  # Reset
                self.hens.clear()
                self.next_hen_number = 1
                self.line_in_count = 0
                self.line_out_count = 0
                self.show_toast("TRACKING COUNTERS RESET")

        # Cleanup video capture and writer
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()

        if self.video_writer is not None:
            self.video_writer.release()
            self.video_writer = None
            print(f"Finished recording raw video. Converting to web-ready H.264...")
            final_mp4 = convert_to_web_ready_video(self.raw_record_path, self.final_record_path)
            print(f"[SUCCESS] Web-Ready Video Saved: {final_mp4}")

        self.is_running = False
        print(f"Live Hen Tracking completed. Total Unique Hens: {self.next_hen_number - 1}")

    def start_tracking(self):
        """Start the tracking thread."""
        if not self.is_running:
            self.is_running = True
            Thread(target=self.tracking_loop, daemon=True).start()

    def stop_tracking(self):
        """Stop tracking and close windows."""
        self.is_running = False
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()


# ─── Modern Tkinter Launcher GUI ──────────────────────────────────────────────
class HenTrackerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("GioTag - Real-Time Hen & Comb AI Tracker")
        self.root.geometry("540x590")
        self.root.resizable(False, False)

        self.tracker = None
        self.default_video = find_default_video()

        # Styles
        style = ttk.Style()
        style.theme_use("clam")

        # Top Header Frame
        header = tk.Frame(root, bg="#111827", height=65)
        header.pack(fill="x")
        title_lbl = tk.Label(
            header,
            text="GioTag Poultry Vision AI",
            font=("Segoe UI", 16, "bold"),
            fg="#10B981",
            bg="#111827",
        )
        title_lbl.pack(pady=(10, 2))
        sub_lbl = tk.Label(
            header,
            text="Real-Time Hen & Comb Tracking • YOLOv8 • Live Analytics HUD",
            font=("Segoe UI", 9),
            fg="#9CA3AF",
            bg="#111827",
        )
        sub_lbl.pack(pady=(0, 10))

        # Main Controls Frame
        main_frame = tk.Frame(root, padx=20, pady=15, bg="#F9FAFB")
        main_frame.pack(fill="both", expand=True)

        # 1. Source Selection
        src_group = tk.LabelFrame(main_frame, text=" Video Source ", font=("Segoe UI", 10, "bold"), bg="#F9FAFB", fg="#1F2937")
        src_group.pack(fill="x", pady=6, padx=5)

        self.source_mode = tk.StringVar(value="file" if self.default_video else "webcam")
        r_webcam = tk.Radiobutton(src_group, text="Live Camera / Webcam (Index 0)", variable=self.source_mode, value="webcam", bg="#F9FAFB", font=("Segoe UI", 9))
        r_webcam.pack(anchor="w", padx=10, pady=2)

        r_file = tk.Radiobutton(src_group, text="Video File:", variable=self.source_mode, value="file", bg="#F9FAFB", font=("Segoe UI", 9))
        r_file.pack(anchor="w", padx=10, pady=2)

        file_row = tk.Frame(src_group, bg="#F9FAFB")
        file_row.pack(fill="x", padx=25, pady=(0, 8))
        self.file_path_var = tk.StringVar(value=self.default_video)
        self.file_entry = tk.Entry(file_row, textvariable=self.file_path_var, font=("Segoe UI", 8), bg="#FFFFFF")
        self.file_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        btn_browse = tk.Button(file_row, text="Browse...", command=self.browse_video, font=("Segoe UI", 8), bg="#E5E7EB")
        btn_browse.pack(side="right")

        # 2. AI Model & Inference Options
        model_group = tk.LabelFrame(main_frame, text=" AI Model & Speed ", font=("Segoe UI", 10, "bold"), bg="#F9FAFB", fg="#1F2937")
        model_group.pack(fill="x", pady=6, padx=5)

        m_row = tk.Frame(model_group, bg="#F9FAFB")
        m_row.pack(fill="x", padx=10, pady=4)
        tk.Label(m_row, text="Model:", bg="#F9FAFB", font=("Segoe UI", 9)).pack(side="left")
        self.model_var = tk.StringVar(value=resolve_model_path())
        self.model_combo = ttk.Combobox(
            m_row,
            textvariable=self.model_var,
            values=[
                "backend/best.pt (Trained Hen Comb - Recommended)",
                "yolov8n.pt (YOLOv8 Nano)",
            ],
            width=36,
            font=("Segoe UI", 8),
        )
        self.model_combo.pack(side="left", padx=8)

        # Resolution toggle
        res_row = tk.Frame(model_group, bg="#F9FAFB")
        res_row.pack(fill="x", padx=10, pady=4)
        tk.Label(res_row, text="Inference Resolution:", bg="#F9FAFB", font=("Segoe UI", 9)).pack(side="left")
        self.imgsz_var = tk.IntVar(value=640)
        r_640 = tk.Radiobutton(res_row, text="640px (High Accuracy)", variable=self.imgsz_var, value=640, bg="#F9FAFB", font=("Segoe UI", 8))
        r_640.pack(side="left", padx=8)
        r_320 = tk.Radiobutton(res_row, text="320px (Ultra-Fast)", variable=self.imgsz_var, value=320, bg="#F9FAFB", font=("Segoe UI", 8))
        r_320.pack(side="left", padx=4)

        # Confidence Threshold Slider
        conf_row = tk.Frame(model_group, bg="#F9FAFB")
        conf_row.pack(fill="x", padx=10, pady=(2, 6))
        tk.Label(conf_row, text="Confidence:", bg="#F9FAFB", font=("Segoe UI", 9)).pack(side="left")
        self.conf_scale = tk.Scale(conf_row, from_=0.05, to=0.80, resolution=0.05, orient="horizontal", bg="#F9FAFB", highlightthickness=0)
        self.conf_scale.set(0.15)
        self.conf_scale.pack(side="left", fill="x", expand=True, padx=8)

        # 3. Features & Toggles
        feat_group = tk.LabelFrame(main_frame, text=" Live Analytics Features ", font=("Segoe UI", 10, "bold"), bg="#F9FAFB", fg="#1F2937")
        feat_group.pack(fill="x", pady=6, padx=5)

        self.trails_var = tk.BooleanVar(value=True)
        self.hud_var = tk.BooleanVar(value=True)
        self.line_var = tk.BooleanVar(value=True)
        self.record_var = tk.BooleanVar(value=False)

        chk_col1 = tk.Frame(feat_group, bg="#F9FAFB")
        chk_col1.pack(side="left", fill="x", expand=True, padx=10, pady=4)
        tk.Checkbutton(chk_col1, text="Motion Trajectory Trails", variable=self.trails_var, bg="#F9FAFB", font=("Segoe UI", 9)).pack(anchor="w")
        tk.Checkbutton(chk_col1, text="On-Screen Analytics HUD", variable=self.hud_var, bg="#F9FAFB", font=("Segoe UI", 9)).pack(anchor="w")

        chk_col2 = tk.Frame(feat_group, bg="#F9FAFB")
        chk_col2.pack(side="right", fill="x", expand=True, padx=10, pady=4)
        tk.Checkbutton(chk_col2, text="Virtual Counting Line", variable=self.line_var, bg="#F9FAFB", font=("Segoe UI", 9)).pack(anchor="w")
        tk.Checkbutton(chk_col2, text="Record Web-Ready MP4", variable=self.record_var, bg="#F9FAFB", font=("Segoe UI", 9)).pack(anchor="w")

        # 4. Status Label
        self.status_lbl = tk.Label(
            main_frame,
            text="Status: Ready to Track",
            font=("Segoe UI", 10, "bold"),
            fg="#047857",
            bg="#F9FAFB",
        )
        self.status_lbl.pack(pady=6)

        # 5. Buttons
        btn_frame = tk.Frame(main_frame, bg="#F9FAFB")
        btn_frame.pack(fill="x", pady=6)

        self.btn_start = tk.Button(
            btn_frame,
            text="▶  START LIVE TRACKING",
            command=self.on_start,
            font=("Segoe UI", 11, "bold"),
            bg="#10B981",
            fg="#FFFFFF",
            relief="flat",
            padx=12,
            pady=8,
            cursor="hand2",
        )
        self.btn_start.pack(side="left", fill="x", expand=True, padx=4)

        self.btn_stop = tk.Button(
            btn_frame,
            text="⏹  STOP TRACKING",
            command=self.on_stop,
            font=("Segoe UI", 11, "bold"),
            bg="#EF4444",
            fg="#FFFFFF",
            relief="flat",
            padx=12,
            pady=8,
            state="disabled",
            cursor="hand2",
        )
        self.btn_stop.pack(side="right", fill="x", expand=True, padx=4)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def browse_video(self):
        f = filedialog.askopenfilename(
            title="Select Video for Tracking",
            filetypes=[("Video Files", "*.mp4 *.avi *.mov *.mkv *.webm"), ("All Files", "*.*")],
        )
        if f:
            self.file_path_var.set(f)
            self.source_mode.set("file")

    def on_start(self):
        mode = self.source_mode.get()
        if mode == "webcam":
            src = 0
        else:
            src = self.file_path_var.get().strip()
            if not src or not os.path.exists(src):
                messagebox.showerror("Invalid Video File", "Please select a valid video file.")
                return

        model_p = self.model_var.get().split(" ")[0].strip()
        imgsz = self.imgsz_var.get()
        conf = float(self.conf_scale.get())

        self.tracker = LiveHenTracker(
            model_path=model_p,
            video_source=src,
            imgsz=imgsz,
            conf_thresh=conf,
            show_trails=self.trails_var.get(),
            show_hud=self.hud_var.get(),
            show_counting_line=self.line_var.get(),
            record_output=self.record_var.get(),
        )

        self.status_lbl.config(text="Status: RUNNING LIVE TRACKING", fg="#2563EB")
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.tracker.start_tracking()

        # Monitor loop
        self.check_tracker_status()

    def check_tracker_status(self):
        if self.tracker and self.tracker.is_running:
            self.root.after(300, self.check_tracker_status)
        else:
            self.status_lbl.config(text="Status: Stopped / Ready", fg="#047857")
            self.btn_start.config(state="normal")
            self.btn_stop.config(state="disabled")

    def on_stop(self):
        if self.tracker:
            self.tracker.stop_tracking()
        self.status_lbl.config(text="Status: Stopped", fg="#6B7280")
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")

    def on_close(self):
        self.on_stop()
        self.root.destroy()


# ─── Command Line & Main Runner ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="GioTag Real-Time Hen & Comb Tracking")
    parser.add_argument("--source", type=str, default=None, help="Video source (0 for webcam, path to video file)")
    parser.add_argument("--model", type=str, default="backend/best.pt", help="Path to YOLO weights (.pt)")
    parser.add_argument("--imgsz", type=int, default=640, help="Inference image resolution (320 or 640)")
    parser.add_argument("--conf", type=float, default=0.15, help="Confidence threshold")
    parser.add_argument("--no-trails", action="store_true", help="Disable motion trajectory trails")
    parser.add_argument("--no-hud", action="store_true", help="Disable on-screen HUD")
    parser.add_argument("--record", action="store_true", help="Record session to Web-Ready MP4 via FFmpeg")
    parser.add_argument("--cli", action="store_true", help="Run directly in CLI mode without Tkinter GUI")

    args = parser.parse_args()

    # If CLI flag or source specified from terminal, run directly
    if args.cli or args.source is not None:
        src = args.source
        if src is None:
            src = find_default_video() or 0
        elif src.isdigit():
            src = int(src)

        tracker = LiveHenTracker(
            model_path=args.model,
            video_source=src,
            imgsz=args.imgsz,
            conf_thresh=args.conf,
            show_trails=not args.no_trails,
            show_hud=not args.no_hud,
            record_output=args.record,
        )
        print("Starting Real-Time Hen & Comb Tracker in CLI mode...")
        tracker.tracking_loop()
    else:
        # Launch modern GUI launcher
        root = tk.Tk()
        app = HenTrackerGUI(root)
        root.mainloop()


if __name__ == "__main__":
    main()
