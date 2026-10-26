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
    os.path.join(_THIS_DIR, "backend", "best.onnx"),
    os.path.join(_THIS_DIR, "best.onnx"),
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
        conf_thresh=0.03,
        iou_thresh=0.40,
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
        self.model = YOLO(self.model_path, task="detect") if self.model_path.endswith(".onnx") else YOLO(self.model_path)
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

    def extract_snug_heads(self, frame, boxes_xyxy, confs):
        """Extract clean, snug hen comb boxes directly from YOLO detections.
        Preserves all detected combs and eliminates duplicate boxes on the same comb."""
        fh, fw = frame.shape[:2]
        if len(boxes_xyxy) == 0:
            return []

        # Red comb color mask: authentic crimson/magenta/pink comb crest across all lighting
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        h_ch, s_ch, v_ch = cv2.split(hsv)
        b_ch, g_ch, r_ch = cv2.split(frame.astype(np.float32))
        comb_mask = (
            (((h_ch >= 150) | (h_ch <= 15)) & (s_ch > 32) & (v_ch > 40) & ((r_ch - g_ch) > 12)) |
            (((r_ch - np.maximum(g_ch, b_ch)) > 15) & (s_ch > 30) & (v_ch > 45))
        )

        # Realistic comb/head dimensions relative to frame size
        min_comb_sz = max(16, int(min(fw, fh) * 0.02))
        max_comb_w = max(60, int(fw * (0.35 if fw < fh else 0.18)))
        max_comb_h = max(60, int(fh * (0.22 if fw < fh else 0.22)))
        max_area = int(max_comb_w * max_comb_h * 0.90)

        raw_combs = []
        for box, conf in zip(boxes_xyxy, confs):
            if conf < self.conf_thresh:
                continue
            bx1, by1, bx2, by2 = map(int, box)
            bx1, by1 = max(0, bx1), max(0, by1)
            bx2, by2 = min(fw - 1, bx2), min(fh - 1, by2)
            bw, bh = bx2 - bx1, by2 - by1
            if bw < min_comb_sz or bh < min_comb_sz:
                continue

            # Strict Comb-only filter: Discard any whole hen body or cluster
            if bw > max_comb_w or bh > max_comb_h or (bw * bh) > max_area:
                continue

            # Redness verification: authentic comb pixels required
            crop = comb_mask[by1:by2, bx1:bx2]
            comb_pixels = np.count_nonzero(crop)
            if comb_pixels < 14 or (crop.size > 0 and (comb_pixels / float(crop.size)) < 0.025):
                continue

            # Snug-fit comb contour refinement: shrink box tight to comb crest
            ys, xs = np.where(crop)
            if len(xs) >= 10:
                pad = 3
                rx1 = max(0, bx1 + int(np.percentile(xs, 3)) - pad)
                rx2 = min(fw - 1, bx1 + int(np.percentile(xs, 97)) + pad)
                ry1 = max(0, by1 + int(np.percentile(ys, 3)) - pad)
                ry2 = min(fh - 1, by1 + int(np.percentile(ys, 97)) + pad)
                if (rx2 - rx1) >= min_comb_sz and (ry2 - ry1) >= min_comb_sz:
                    final_box = (rx1, ry1, rx2, ry2)
                    comb_cx = int((rx1 + rx2) / 2.0)
                    comb_cy = int((ry1 + ry2) / 2.0)
                else:
                    final_box = (bx1, by1, bx2, by2)
                    comb_cx = int((bx1 + bx2) / 2.0)
                    comb_cy = int((by1 + by2) / 2.0)
            else:
                final_box = (bx1, by1, bx2, by2)
                comb_cx = int((bx1 + bx2) / 2.0)
                comb_cy = int((by1 + by2) / 2.0)

            # Ceiling boundary check
            if final_box[1] <= 6:
                continue

            raw_combs.append({
                "box": final_box,
                "center": (comb_cx, comb_cy),
                "size": (final_box[2] - final_box[0], final_box[3] - final_box[1]),
                "conf": float(conf),
                "is_comb": True,
            })

        if not raw_combs:
            return []

        # Deduplicate overlapping boxes on the same comb without rejecting neighboring hens
        raw_combs.sort(key=lambda d: d["conf"], reverse=True)
        head_radius = max(18.0, 0.018 * fw)

        kept = []
        for d in raw_combs:
            b1 = d["box"]
            cx1, cy1 = d["center"]
            is_dup = False
            for ex in kept:
                b2 = ex["box"]
                cx2, cy2 = ex["center"]

                ix1, iy1 = max(b1[0], b2[0]), max(b1[1], b2[1])
                ix2, iy2 = min(b1[2], b2[2]), min(b1[3], b2[3])
                iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
                inter = iw * ih
                a1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
                a2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
                iou = inter / float(a1 + a2 - inter) if (a1 + a2 - inter) > 0 else 0.0
                dist = math.hypot(cx1 - cx2, cy1 - cy2)

                if iou > 0.40 or dist < head_radius:
                    is_dup = True
                    break

            if not is_dup:
                kept.append(d)

        return kept

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

        # Dynamic search radius based on resolution (tight follow on hen head, zero jumping)
        MAX_SEARCH = max(35.0, 0.04 * frame_w)
        MIN_NEW_DIST = max(38.0, 0.04 * frame_w)

        # ─── Detection Zone: gates NEW hen registration only ───
        if frame_w < frame_h:
            ZONE_X1 = int(frame_w * 0.02)
            ZONE_Y1 = int(frame_h * 0.08)
            ZONE_X2 = int(frame_w * 0.85)
            ZONE_Y2 = int(frame_h * 0.95)
        else:
            ZONE_X1 = int(frame_w * 0.04)
            ZONE_Y1 = int(frame_h * 0.08)
            ZONE_X2 = int(frame_w * 0.96)
            ZONE_Y2 = int(frame_h * 0.92)

        def is_in_zone(cx, cy):
            return ZONE_X1 <= cx <= ZONE_X2 and ZONE_Y1 <= cy <= ZONE_Y2

        def box_iou(b1, b2):
            ix1, iy1 = max(b1[0], b2[0]), max(b1[1], b2[1])
            ix2, iy2 = min(b1[2], b2[2]), min(b1[3], b2[3])
            iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
            inter = iw * ih
            if inter <= 0:
                return 0.0
            a1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
            a2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
            u = a1 + a2 - inter
            return inter / u if u > 0 else 0.0

        while self.is_running and self.cap.isOpened():
            if self.paused:
                key = cv2.waitKey(30) & 0xFF
                if key == ord(" "):
                    self.paused = False
                    self.show_toast("RESUMED", 1.5)
                elif key in (ord("q"), 27):
                    break
                elif key == ord("s"):
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

            # Age tracks: increment lost_frames, keep boxes anchored firmly to hen heads
            for num, data in self.hens.items():
                data["lost_frames"] += 1
                data["seen"] = False

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

            # ─── 2. Clean Deduplicated Detections (1 Comb = 1 Box) ───
            detections = []
            if results and len(results) > 0 and results[0].boxes is not None:
                boxes_xyxy = results[0].boxes.xyxy.cpu().numpy()
                confs = results[0].boxes.conf.cpu().numpy()
                detections = self.extract_snug_heads(frame, boxes_xyxy, confs)
                for det in detections:
                    self.conf_history.append(det["conf"])

            # Frame 1: Register initial hens from BOTTOM TO TOP ("killa irunthu mela")
            if frame_no == 1:
                detections.sort(key=lambda d: -d["center"][1] * 2.0 + d["center"][0])
                for det in detections:
                    num = self.next_hen_number
                    self.next_hen_number += 1
                    raw_box = det["box"]
                    center = det["center"]
                    trail = deque(maxlen=25)
                    trail.append(center)
                    self.hens[num] = {
                        "center": center,
                        "box": list(raw_box),
                        "vel": (0.0, 0.0),
                        "lost_frames": 0,
                        "seen": True,
                        "hits": 3,
                        "size": det["size"],
                        "trail": trail,
                        "last_y": center[1],
                        "is_comb": True,
                    }
                    det["hen_number"] = num

            # ─── 3. Velocity-Guided Bipartite Matching (Stage 1: Active Tracks) ───
            matched_dets = set()
            used_hens = set()

            if frame_no > 1:
                candidate_matches = []
                for d_idx, det in enumerate(detections):
                    cx, cy = det["center"]
                    raw_box = det["box"]
                    for num, data in self.hens.items():
                        if data["lost_frames"] > 4:
                            continue
                        if not is_in_zone(data["center"][0], data["center"][1]):
                            continue
                        dist = math.hypot(cx - data["center"][0], cy - data["center"][1])
                        iou = box_iou(raw_box, data["box"])

                        if dist <= MAX_SEARCH or iou > 0.20:
                            cost = (1.0 - iou) * 0.3 + (dist / MAX_SEARCH) * 0.7
                            candidate_matches.append((cost, d_idx, num))

                candidate_matches.sort(key=lambda x: x[0])
                for cost, d_idx, num in candidate_matches:
                    if d_idx in matched_dets or num in used_hens:
                        continue
                    matched_dets.add(d_idx)
                    used_hens.add(num)
                    det = detections[d_idx]
                    center = det["center"]
                    raw_box = det["box"]
                    data = self.hens[num]

                    # Smooth position & box update: STABILIZED to prevent box jumping (55/45 blend)
                    old_cx, old_cy = data["center"]
                    old_b = data["box"]
                    SMOOTH = 0.55
                    SMOOTH_INV = 0.45
                    data["center"] = (SMOOTH * center[0] + SMOOTH_INV * old_cx, SMOOTH * center[1] + SMOOTH_INV * old_cy)
                    data["box"] = [
                        int(SMOOTH * raw_box[0] + SMOOTH_INV * old_b[0]),
                        int(SMOOTH * raw_box[1] + SMOOTH_INV * old_b[1]),
                        int(SMOOTH * raw_box[2] + SMOOTH_INV * old_b[2]),
                        int(SMOOTH * raw_box[3] + SMOOTH_INV * old_b[3]),
                    ]
                    data["lost_frames"] = 0
                    data["seen"] = True
                    data["hits"] = data.get("hits", 0) + 1
                    data["size"] = det["size"]
                    data["trail"].append((int(data["center"][0]), int(data["center"][1])))

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

            # ─── 4. Stage 2: New Hen Gating (Strict sequential IDs, no repeats, bottom-to-top) ───
            if frame_no > 1:
                unmatched_dets = [det for d_idx, det in enumerate(detections) if d_idx not in matched_dets]
                unmatched_dets.sort(key=lambda d: -d["center"][1])
                for det in unmatched_dets:
                    center = det["center"]
                    raw_box = det["box"]

                    # Only block if too close to an actively tracked hen (prevents duplicate boxes on same hen)
                    is_near_any = any(
                        math.hypot(center[0] - data["center"][0], center[1] - data["center"][1]) < MIN_NEW_DIST
                        for data in self.hens.values() if data["lost_frames"] <= 4
                    )
                    if is_near_any:
                        continue

                    # Zone gate: only register NEW hens inside the detection zone
                    if not is_in_zone(center[0], center[1]):
                        continue

                    num = self.next_hen_number
                    self.next_hen_number += 1
                    trail = deque(maxlen=25)
                    trail.append(center)
                    self.hens[num] = {
                        "center": center,
                        "box": list(raw_box),
                        "vel": (0.0, 0.0),
                        "lost_frames": 0,
                        "seen": True,
                        "hits": 1,
                        "size": det["size"],
                        "trail": trail,
                        "last_y": center[1],
                        "is_comb": True,
                    }
                    used_hens.add(num)
                    det["hen_number"] = num

            # ─── IMMEDIATE RETIREMENT: When hen leaves zone, delete immediately! ───
            # Box disappears instantly, and ID is NEVER repeated!
            for num in list(self.hens.keys()):
                cx, cy = self.hens[num]["center"]
                b = self.hens[num]["box"]
                left_zone = not is_in_zone(cx, cy)
                lost_too_long = self.hens[num]["lost_frames"] > 4
                outside = (b[2] < 0 or b[0] > frame_w or b[3] < 0 or b[1] > frame_h)
                if left_zone or lost_too_long or outside:
                    del self.hens[num]

            # ─── DRAW DETECTION ZONE OVERLAY ───
            display_frame = frame.copy()
            zone_overlay = display_frame.copy()
            cv2.rectangle(zone_overlay, (0, 0), (frame_w, ZONE_Y1), (0, 0, 0), -1)
            cv2.rectangle(zone_overlay, (0, ZONE_Y2), (frame_w, frame_h), (0, 0, 0), -1)
            cv2.rectangle(zone_overlay, (0, ZONE_Y1), (ZONE_X1, ZONE_Y2), (0, 0, 0), -1)
            cv2.rectangle(zone_overlay, (ZONE_X2, ZONE_Y1), (frame_w, ZONE_Y2), (0, 0, 0), -1)
            cv2.addWeighted(zone_overlay, 0.25, display_frame, 0.75, 0, display_frame)
            cv2.rectangle(display_frame, (ZONE_X1, ZONE_Y1), (ZONE_X2, ZONE_Y2), (0, 240, 255), 2, cv2.LINE_AA)
            zc_len = 16
            for zx, zy, dx, dy in [(ZONE_X1, ZONE_Y1, 1, 1), (ZONE_X2, ZONE_Y1, -1, 1),
                                    (ZONE_X1, ZONE_Y2, 1, -1), (ZONE_X2, ZONE_Y2, -1, -1)]:
                cv2.line(display_frame, (zx, zy), (zx + dx * zc_len, zy), (0, 255, 255), 3, cv2.LINE_AA)
                cv2.line(display_frame, (zx, zy), (zx, zy + dy * zc_len), (0, 255, 255), 3, cv2.LINE_AA)
            zone_label = "DETECTION ZONE"
            (ztw, zth), _ = cv2.getTextSize(zone_label, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
            cv2.rectangle(display_frame, (ZONE_X1 + 4, ZONE_Y1 + 4), (ZONE_X1 + ztw + 14, ZONE_Y1 + zth + 12), (0, 0, 0), -1)
            cv2.rectangle(display_frame, (ZONE_X1 + 4, ZONE_Y1 + 4), (ZONE_X1 + ztw + 14, ZONE_Y1 + zth + 12), (0, 240, 255), 1)
            cv2.putText(display_frame, zone_label, (ZONE_X1 + 9, ZONE_Y1 + zth + 8), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 240, 255), 1, cv2.LINE_AA)

            # ZONE FILTER: When a hen leaves the zone, its detection box disappears ("poiruranum")
            candidate_hens = [
                (num, data) for num, data in self.hens.items()
                if data["lost_frames"] == 0 and data.get("hits", 0) >= 1 and is_in_zone(data["center"][0], data["center"][1]) and data["box"][1] > 6
            ]
            candidate_hens.sort(key=lambda item: (item[1].get("hits", 0), -item[1].get("lost_frames", 0)), reverse=True)

            # Display Deduplication: suppress overlapping boxes for RENDERING ONLY
            active_render_hens = []
            min_hen_dist = max(18.0, 0.015 * frame_w)

            for num, data in candidate_hens:
                cx, cy = data["center"]
                box = data["box"]
                is_dup = False
                for v_num, v_data in active_render_hens:
                    v_cx, v_cy = v_data["center"]
                    v_box = v_data["box"]
                    dist = math.hypot(cx - v_cx, cy - v_cy)
                    iou = box_iou(box, v_box)
                    if dist < min_hen_dist or iou > 0.30:
                        is_dup = True
                        break
                if not is_dup:
                    active_render_hens.append((num, data))

            visible_count = len(active_render_hens)
            self.total_counted = max(self.total_counted, self.next_hen_number - 1)
            total_unique = self.total_counted

            # 1. Draw Motion Trajectory Trails
            if self.show_trails:
                for num, data in self.hens.items():
                    trail = data.get("trail", [])
                    if len(trail) > 1 and data["lost_frames"] <= 1:
                        pts = list(trail)
                        for idx in range(1, len(pts)):
                            thickness = max(1, int(idx / len(pts) * 3.5))
                            fade = idx / len(pts)
                            color = (int(255 * (1 - fade)), int(230 * fade), int(255 * fade))
                            pt_a = (int(pts[idx - 1][0]), int(pts[idx - 1][1]))
                            pt_b = (int(pts[idx][0]), int(pts[idx][1]))
                            cv2.line(display_frame, pt_a, pt_b, color, thickness, cv2.LINE_AA)

            # 2. Draw Active Hen Head Bounding Boxes (EXACTLY ONE BOX PER HEN)
            for num, data in active_render_hens:
                sb = data["box"]
                x1, y1, x2, y2 = int(sb[0]), int(sb[1]), int(sb[2]), int(sb[3])

                # Solid bright green head box
                box_color = (0, 255, 0)
                self.draw_rounded_rect(display_frame, (x1, y1), (x2, y2), box_color, 2, r=6)

                # High-precision viewfinder corner brackets
                bw = x2 - x1
                bh = y2 - y1
                c_len = max(5, min(10, int(min(bw, bh) * 0.35)))
                cv2.line(display_frame, (x1, y1), (x1 + c_len, y1), (255, 255, 255), 2)
                cv2.line(display_frame, (x1, y1), (x1, y1 + c_len), (255, 255, 255), 2)
                cv2.line(display_frame, (x2, y1), (x2 - c_len, y1), (255, 255, 255), 2)
                cv2.line(display_frame, (x2, y1), (x2, y1 + c_len), (255, 255, 255), 2)
                cv2.line(display_frame, (x1, y2), (x1 + c_len, y2), (255, 255, 255), 2)
                cv2.line(display_frame, (x1, y2), (x1, y2 - c_len), (255, 255, 255), 2)
                cv2.line(display_frame, (x2, y2), (x2 - c_len, y2), (255, 255, 255), 2)
                cv2.line(display_frame, (x2, y2), (x2, y2 - c_len), (255, 255, 255), 2)

                # Clean Badge: Hen 1, Hen 2, Hen 3...
                badge_text = f"Hen {num}"
                (tw, th), _ = cv2.getTextSize(badge_text, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 2)
                ty1 = max(y1 - 22, 0)
                ty2 = max(y1, 22)
                cv2.rectangle(display_frame, (x1, ty1), (x1 + tw + 8, ty2), box_color, -1)
                cv2.putText(
                    display_frame,
                    badge_text,
                    (x1 + 4, max(y1 - 5, 16)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.48,
                    (0, 0, 0),
                    2,
                    cv2.LINE_AA,
                )

                # Center tracking crosshair dot on comb
                cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
                cv2.circle(display_frame, (cx, cy), 3, (0, 255, 0), -1)

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
        self.conf_scale = tk.Scale(conf_row, from_=0.05, to=0.80, resolution=0.01, orient="horizontal", bg="#F9FAFB", highlightthickness=0)
        self.conf_scale.set(0.10)
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
    parser.add_argument("--conf", type=float, default=0.22, help="Confidence threshold")
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
