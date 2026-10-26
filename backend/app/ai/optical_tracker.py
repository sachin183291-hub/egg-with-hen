import time
import math
import threading
import traceback
import cv2
import numpy as np
import os
import torch
from ultralytics import YOLO

def extract_snug_heads(disp_img, x1, y1, x2, y2, fw, fh, full_mask=None):
    """
    Extracts snug, individual-sized bounding boxes strictly covering each hen's head and comb.
    Decomposes multi-hen boxes into individual heads so zero hens are missed.
    """
    x1, y1 = max(0, int(x1)), max(0, int(y1))
    x2, y2 = min(fw - 1, int(x2)), min(fh - 1, int(y2))
    bw, bh = x2 - x1, y2 - y1
    if bw < 6 or bh < 6:
        return []

    if full_mask is None:
        crop = disp_img[y1:y2, x1:x2]
        if crop.size == 0:
            return []
        b, g, r = cv2.split(crop.astype(np.float32))
        red_diff = r - np.maximum(g, b)
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        crop_mask = ((red_diff > 16) & (s > 32) & (v > 42) & ((h < 22) | (h > 158))).astype(np.uint8)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        crop_mask = cv2.morphologyEx(crop_mask, cv2.MORPH_OPEN, kernel)
    else:
        crop_mask = full_mask[y1:y2, x1:x2]
        if crop_mask.size == 0:
            return []

    max_head_w = max(38, int(fw * 0.08))
    max_head_h = max(42, int(fh * 0.09))

    heads = []
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(crop_mask)
    found_comp = False

    for idx in range(1, num_labels):
        area = stats[idx, cv2.CC_STAT_AREA]
        cw = stats[idx, cv2.CC_STAT_WIDTH]
        ch = stats[idx, cv2.CC_STAT_HEIGHT]
        if area >= 20 and cw >= 6 and ch >= 6:
            comp_cx, comp_cy = centroids[idx]
            head_w = max(24, min(max_head_w, int(cw * 1.30 + 8)))
            head_h = max(26, min(max_head_h, int(ch * 1.30 + 10)))
            cx = x1 + comp_cx
            cy = y1 + comp_cy
            heads.append([
                max(0, int(cx - head_w / 2.0)),
                max(0, int(cy - head_h / 2.0)),
                min(fw - 1, int(cx + head_w / 2.0)),
                min(fh - 1, int(cy + head_h / 2.0))
            ])
            found_comp = True

    if not found_comp and bw <= max_head_w * 1.1 and bh <= max_head_h * 1.1 and bw >= 12 and bh >= 12:
        if np.sum(crop_mask) >= 8:
            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            head_w = max(24, min(max_head_w, bw))
            head_h = max(26, min(max_head_h, bh))
            heads.append([
                max(0, int(cx - head_w / 2.0)),
                max(0, int(cy - head_h / 2.0)),
                min(fw - 1, int(cx + head_w / 2.0)),
                min(fh - 1, int(cy + head_h / 2.0))
            ])

    return heads


class OpticalHenTracker:
    def __init__(self, model_path=None):
        self.MODEL_PATH = model_path
        self.DEVICE = 0 if torch.cuda.is_available() else "cpu"
        
        from app.ai.shared_model import get_shared_model
        self.model = get_shared_model(model_path)
        
        self.state_lock = threading.RLock()
        self.ai_lock = threading.Lock()
        
        self.ai_frame = None
        self.ai_results = None
        self.ai_running = True
        
        self.reset_state()
        
        # Background worker for continuous YOLO inference without blocking frame stream
        self.worker_thread = threading.Thread(target=self._ai_worker, daemon=True)
        self.worker_thread.start()

    def _ai_worker(self):
        """Background thread running YOLO inference continuously."""
        while self.ai_running:
            f = None
            with self.ai_lock:
                if self.ai_frame is not None:
                    f = self.ai_frame
                    self.ai_frame = None
            if f is None:
                time.sleep(0.01)
                continue

            try:
                fh, fw = f.shape[:2]
                infer_imgsz = 352 if (os.environ.get("RENDER") == "true" or not torch.cuda.is_available()) else 640
                results = self.model.predict(
                    source=f,
                    verbose=False,
                    conf=0.035,
                    iou=0.40,
                    imgsz=infer_imgsz,
                    device=self.DEVICE
                )

                raw_dets = []
                if results and len(results) > 0 and results[0].boxes is not None:
                    boxes = results[0].boxes.xyxy.cpu().numpy()
                    confs = results[0].boxes.conf.cpu().numpy()

                    # Dynamic Zone definition (stored for new-hen gating in process_live_frame)
                    if fw < fh:
                        self._zone = (int(fw * 0.01), int(fh * 0.02), int(fw * 0.99), int(fh * 0.98))
                    else:
                        self._zone = (int(fw * 0.01), int(fh * 0.02), int(fw * 0.99), int(fh * 0.98))

                    max_comb_w = max(60, int(fw * (0.35 if fw < fh else 0.18)))
                    max_comb_h = max(60, int(fh * (0.22 if fw < fh else 0.22)))
                    max_area = int(max_comb_w * max_comb_h * 0.90)

                    hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
                    h_ch, s_ch, v_ch = cv2.split(hsv)
                    b_ch, g_ch, r_ch = cv2.split(f.astype(np.float32))
                    comb_red = (
                        (((h_ch >= 150) | (h_ch <= 15)) & (s_ch > 32) & (v_ch > 40) & ((r_ch - g_ch) > 12)) |
                        (((r_ch - np.maximum(g_ch, b_ch)) > 15) & (s_ch > 30) & (v_ch > 45))
                    )

                    for box, conf in zip(boxes, confs):
                        x1, y1, x2, y2 = map(int, box)
                        hw = x2 - x1
                        hh = y2 - y1
                        if hw < 8 or hh < 8:
                            continue
                        if hw > max_comb_w or hh > max_comb_h or (hw * hh) > max_area:
                            continue

                        crop_red = comb_red[y1:y2, x1:x2]
                        ys, xs = np.where(crop_red)
                        scale_factor = max(fw, fh) / 640.0
                        if len(xs) >= 6:
                            cx = x1 + float(np.median(xs))
                            cy = y1 + float(np.median(ys))
                            w_comb = float(np.percentile(xs, 90) - np.percentile(xs, 10))
                            h_comb = float(np.percentile(ys, 90) - np.percentile(ys, 10))
                            base_sz = max(24.0 * scale_factor, min(38.0 * scale_factor, max(w_comb, h_comb) + 6.0))
                        else:
                            cx = (x1 + x2) / 2.0
                            cy = (y1 + y2) / 2.0
                            base_sz = max(24.0 * scale_factor, min(38.0 * scale_factor, max(hw, hh) + 4.0))

                        hw_box = base_sz / 2.0
                        hh_box = base_sz / 2.0
                        box_final = [
                            max(0.0, float(cx - hw_box)),
                            max(0.0, float(cy - hh_box)),
                            min(float(fw - 1), float(cx + hw_box)),
                            min(float(fh - 1), float(cy + hh_box))
                        ]

                        # Reject ceiling fixtures at top
                        if box_final[1] <= 6:
                            continue

                        # Zone check: only detect combs inside the detection zone
                        z = getattr(self, '_zone', None)
                        if z is not None and not (z[0] <= cx <= z[2] and z[1] <= cy <= z[3]):
                            continue

                        raw_dets.append({
                            "box": box_final,
                            "center": (cx, cy),
                            "conf": float(conf),
                            "diag": math.hypot(box_final[2] - box_final[0], box_final[3] - box_final[1])
                        })

                # Deduplicate: strictly ONE box per hen head
                raw_dets.sort(key=lambda d: d["conf"], reverse=True)
                kept_dets = []
                for d in raw_dets:
                    c1 = d["center"]
                    diag1 = d["diag"]
                    overlap = False
                    for ex in kept_dets:
                        c2 = ex["center"]
                        diag2 = ex["diag"]
                        if math.hypot(c1[0] - c2[0], c1[1] - c2[1]) < min(diag1, diag2) * 0.40 or math.hypot(c1[0] - c2[0], c1[1] - c2[1]) < 22:
                            overlap = True
                            break
                    if not overlap:
                        kept_dets.append(d)

                with self.ai_lock:
                    self.ai_results = kept_dets

            except Exception as e:
                pass

    def reset_state(self):
        with self.state_lock:
            self.hens = {}
            self.next_hen_number = 1
            self.max_total_hens = 0
            self.prev_gray = None
            self.prev_small_gray = None
            self.latest_detections = []
            self.latest_frame_number = 0
            self.latest_video_time = 0.0
            self.total_inference_count = 0
            self.ai_fps = 30.0

        with self.ai_lock:
            self.ai_frame = None
            self.ai_results = None

    def process_live_frame(self, frame, frame_number, video_time):
        started = time.time()
        fh, fw = frame.shape[:2]

        with self.state_lock:
            self.latest_frame_number = frame_number
            self.latest_video_time = video_time
            self.total_inference_count += 1

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # Boxes remain anchored to detected hen heads; zero artificial drift
            small_gray = cv2.cvtColor(cv2.resize(frame, (320, 180)), cv2.COLOR_BGR2GRAY).astype(np.float32)
            self.prev_small_gray = small_gray

            # ─── Instant Initial Seed: Spatially ordered 1, 2, 3... ───
            if len(self.hens) == 0:
                try:
                    init_imgsz = 352 if (os.environ.get("RENDER") == "true" or not torch.cuda.is_available()) else 640
                    init_res = self.model.predict(
                        source=frame,
                        verbose=False,
                        conf=0.025,
                        iou=0.45,
                        imgsz=init_imgsz,
                        device=self.DEVICE
                    )
                    if init_res and len(init_res) > 0 and init_res[0].boxes is not None:
                        boxes = init_res[0].boxes.xyxy.cpu().numpy()
                        confs = init_res[0].boxes.conf.cpu().numpy()
                        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                        h_ch, s_ch, v_ch = cv2.split(hsv)
                        b_ch, g_ch, r_ch = cv2.split(frame.astype(np.float32))
                        comb_red = (
                            (((h_ch >= 150) | (h_ch <= 15)) & (s_ch > 32) & (v_ch > 40) & ((r_ch - g_ch) > 12)) |
                            (((r_ch - np.maximum(g_ch, b_ch)) > 15) & (s_ch > 30) & (v_ch > 45))
                        )
                        init_candidates = []
                        scale_factor = max(fw, fh) / 640.0
                        for box, conf in zip(boxes, confs):
                            x1, y1, x2, y2 = map(int, box)
                            x1, y1 = max(0, min(fw - 1, x1)), max(0, min(fh - 1, y1))
                            x2, y2 = max(0, min(fw - 1, x2)), max(0, min(fh - 1, y2))
                            crop_red = comb_red[y1:y2, x1:x2]
                            comb_px = np.count_nonzero(crop_red)
                            if comb_px < 14:
                                continue
                            ys, xs = np.where(crop_red)
                            if len(xs) >= 10:
                                cx = x1 + float(np.median(xs))
                                cy = y1 + float(np.median(ys))
                                w_comb = float(np.percentile(xs, 90) - np.percentile(xs, 10))
                                h_comb = float(np.percentile(ys, 90) - np.percentile(ys, 10))
                                base_sz = max(26.0 * scale_factor, min(38.0 * scale_factor, max(w_comb, h_comb) + 6.0))
                                hw, hh = base_sz / 2.0, base_sz / 2.0
                                box_final = [
                                    max(0.0, float(cx - hw)),
                                    max(0.0, float(cy - hh)),
                                    min(float(fw - 1), float(cx + hw)),
                                    min(float(fh - 1), float(cy + hh))
                                ]
                                init_candidates.append({
                                    "box": box_final,
                                    "center": (cx, cy),
                                    "conf": float(conf)
                                })

                        # Sort bottom-to-top ("killa irunthu mela") so Hen #1 is at the bottom
                        init_candidates.sort(key=lambda d: -d["center"][1] * 2.0 + d["center"][0])
                        for d in init_candidates:
                            # Assign strictly new permanent number (never reuse, never repeat)
                            hid = self.next_hen_number
                            self.next_hen_number += 1

                            self.hens[hid] = {
                                "box": d["box"],
                                "center": d["center"],
                                "velocity": (0.0, 0.0),
                                "lost": 0,
                                "hits": 3,
                                "conf": d["conf"]
                            }
                        self.max_total_hens = max(self.max_total_hens, len(self.hens))
                except Exception:
                    pass

            # ─── 1. Multi-Point Optical Flow PyrLK: Tight points locked inside head/comb ───
            active_ids = [hid for hid, hdata in self.hens.items() if hdata["lost"] <= 12]
            if len(active_ids) > 0 and self.prev_gray is not None:
                pts_in = []
                pt_map = []
                for hid in active_ids:
                    x1, y1, x2, y2 = self.hens[hid]["box"]
                    cx, cy = self.hens[hid]["center"]
                    bw = x2 - x1
                    bh = y2 - y1
                    quad_pts = [
                        (cx, cy),
                        (cx - bw * 0.22, cy - bh * 0.22),
                        (cx + bw * 0.22, cy - bh * 0.22),
                        (cx - bw * 0.22, cy + bh * 0.22),
                        (cx + bw * 0.22, cy + bh * 0.22),
                    ]
                    for p in quad_pts:
                        pts_in.append([[p[0], p[1]]])
                        pt_map.append(hid)

                pts_in_arr = np.array(pts_in, dtype=np.float32)
                # Larger window and higher pyramid level for fast head movement / turning
                pts_out, status, _ = cv2.calcOpticalFlowPyrLK(
                    self.prev_gray, gray, pts_in_arr, None,
                    winSize=(21, 21), maxLevel=3,
                    criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 12, 0.03)
                )

                hen_shifts = {hid: [] for hid in active_ids}
                for i, hid in enumerate(pt_map):
                    if status[i][0] == 1:
                        dx = float(pts_out[i][0][0] - pts_in_arr[i][0][0])
                        dy = float(pts_out[i][0][1] - pts_in_arr[i][0][1])
                        if abs(dx) < 15 and abs(dy) < 15:
                            hen_shifts[hid].append((dx, dy))

                for hid, shifts in hen_shifts.items():
                    if len(shifts) >= 1:
                        mdx = float(np.median([s[0] for s in shifts]))
                        mdy = float(np.median([s[1] for s in shifts]))
                        b = self.hens[hid]["box"]
                        self.hens[hid]["box"] = [b[0] + mdx, b[1] + mdy, b[2] + mdx, b[3] + mdy]
                        cx = (self.hens[hid]["box"][0] + self.hens[hid]["box"][2]) / 2.0
                        cy = (self.hens[hid]["box"][1] + self.hens[hid]["box"][3]) / 2.0
                        self.hens[hid]["center"] = (cx, cy)
                        self.hens[hid]["velocity"] = (mdx, mdy)
                    else:
                        # Keep box firmly anchored to head, zero drift into side
                        self.hens[hid]["velocity"] = (0.0, 0.0)
                        self.hens[hid]["lost"] += 1

            self.prev_gray = gray

            # ─── 2. Integrate fresh YOLO comb detections from background worker ───
            fresh = None
            with self.ai_lock:
                if self.ai_results is not None:
                    fresh = self.ai_results
                    self.ai_results = None

            def _box_iou(b1, b2):
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

            if fresh is not None:
                used_dets = set()
                used_hens = set()

                z = getattr(self, '_zone', None)
                def is_in_zone(x, y):
                    if z is None:
                        return True
                    return z[0] <= x <= z[2] and z[1] <= y <= z[3]

                # Stage 1: Match active and remembered tracks with stable radius
                MAX_LOST_MEMORY = 30
                active_matches = []
                for det_idx, det in enumerate(fresh):
                    cx, cy = det["center"]
                    for hid, hdata in self.hens.items():
                        if hdata["lost"] > MAX_LOST_MEMORY:
                            continue
                        hx, hy = hdata["center"]
                        if not is_in_zone(hx, hy):
                            continue
                        vx, vy = hdata.get("velocity", (0.0, 0.0))
                        pred_hx = hx + vx * min(hdata["lost"], 3)
                        pred_hy = hy + vy * min(hdata["lost"], 3)
                        dist = min(math.hypot(cx - hx, cy - hy), math.hypot(cx - pred_hx, cy - pred_hy))
                        iou = _box_iou(hdata["box"], det["box"])
                        max_match = 50.0  # Stable radius to keep ID locked to hen
                        if iou >= 0.15 or dist <= max_match:
                            cost = (1.0 - iou) * 0.4 + (dist / max_match) * 0.6
                            active_matches.append((cost, det_idx, hid))

                active_matches.sort(key=lambda m: m[0])
                for cost, det_idx, hid in active_matches:
                    if det_idx in used_dets or hid in used_hens:
                        continue
                    used_dets.add(det_idx)
                    used_hens.add(hid)
                    det = fresh[det_idx]
                    nb = det["box"]
                    det_cx, det_cy = det["center"]
                    old_cx, old_cy = self.hens[hid]["center"]
                    old_b = self.hens[hid]["box"]

                    # Smooth position & box update: follows hen head smoothly, ZERO box jumping
                    SMOOTH = 0.40
                    SMOOTH_INV = 0.60
                    self.hens[hid]["box"] = [
                        SMOOTH * nb[0] + SMOOTH_INV * old_b[0],
                        SMOOTH * nb[1] + SMOOTH_INV * old_b[1],
                        SMOOTH * nb[2] + SMOOTH_INV * old_b[2],
                        SMOOTH * nb[3] + SMOOTH_INV * old_b[3]
                    ]
                    self.hens[hid]["center"] = (SMOOTH * det_cx + SMOOTH_INV * old_cx, SMOOTH * det_cy + SMOOTH_INV * old_cy)
                    self.hens[hid]["velocity"] = (det_cx - old_cx, det_cy - old_cy)
                    self.hens[hid]["lost"] = 0
                    self.hens[hid]["hits"] = self.hens[hid].get("hits", 0) + 1
                    self.hens[hid]["conf"] = det["conf"]

                # Increment lost for any track not matched in this AI cycle
                for hid, hdata in self.hens.items():
                    if hid not in used_hens:
                        hdata["lost"] += 1

                # Stage 2: Register New Hen entering the zone (Unique IDs, zero repeats!)
                min_new_dist = 36.0
                unmatched_fresh = [det for det_idx, det in enumerate(fresh) if det_idx not in used_dets and det.get("conf", 0.0) >= 0.03]
                unmatched_fresh.sort(key=lambda d: -d["center"][1])
                for det in unmatched_fresh:
                    cx, cy = det["center"]

                    # Zone gate: only register inside the detection zone
                    if not is_in_zone(cx, cy):
                        continue

                    # Only block if too close to a known tracked hen (prevents duplicate box on same comb)
                    is_near_active = any(
                        math.hypot(cx - h["center"][0], cy - h["center"][1]) < min_new_dist or _box_iou(det["box"], h["box"]) > 0.25
                        for h in self.hens.values() if h["lost"] <= 45
                    )
                    if is_near_active:
                        continue

                    # Truly new hen entered the zone: assign a new unique ID! Never repeat!
                    hid = self.next_hen_number
                    self.next_hen_number += 1
                    self.hens[hid] = {
                        "box": list(det["box"]),
                        "center": (cx, cy),
                        "velocity": (0.0, 0.0),
                        "lost": 0,
                        "hits": 1,
                        "conf": det["conf"]
                    }
                    used_hens.add(hid)

            # IMMEDIATE RETIREMENT: When a hen actually leaves the zone or is lost too long
            # When a hen leaves the zone, its box vanishes immediately and ID is permanently preserved!
            z = getattr(self, '_zone', None)
            for hid in list(self.hens.keys()):
                b = self.hens[hid]["box"]
                cx, cy = self.hens[hid]["center"]
                left_zone = (z is not None and not (z[0] <= cx <= z[2] and z[1] <= cy <= z[3]))
                lost_too_long = self.hens[hid]["lost"] > 45
                is_out_of_bounds = (b[2] < 0 or b[0] > fw or b[3] < 0 or b[1] > fh)
                if left_zone or lost_too_long or is_out_of_bounds:
                    del self.hens[hid]

            # ─── 3. Submit frame to AI worker if idle ───
            with self.ai_lock:
                if self.ai_frame is None and self.ai_results is None:
                    self.ai_frame = frame.copy()

            # ZONE FILTER: Only display boxes while the hen's head/comb is actively detected inside the detection zone
            # When a hen leaves the zone, its detection box disappears immediately ("poiruranum")
            z = getattr(self, '_zone', None)
            candidates = [
                hid for hid, d in self.hens.items()
                if d["lost"] <= 2 and d.get("hits", 0) >= 1 and (z is None or (z[0] <= d["center"][0] <= z[2] and z[1] <= d["center"][1] <= z[3])) and d["box"][1] > 6
            ]
            candidates.sort(key=lambda hid: (-self.hens[hid].get("hits", 0), self.hens[hid]["lost"]))

            visible_hens = []
            for hid in candidates:
                b1 = self.hens[hid]["box"]
                c1 = self.hens[hid]["center"]
                diag1 = math.hypot(b1[2] - b1[0], b1[3] - b1[1])
                is_duplicate = False
                for kept_id in visible_hens:
                    b2 = self.hens[kept_id]["box"]
                    c2 = self.hens[kept_id]["center"]
                    diag2 = math.hypot(b2[2] - b2[0], b2[3] - b2[1])

                    if math.hypot(c1[0] - c2[0], c1[1] - c2[1]) < min(diag1, diag2) * 0.35:
                        is_duplicate = True
                        break

                    ix1, iy1 = max(b1[0], b2[0]), max(b1[1], b2[1])
                    ix2, iy2 = min(b1[2], b2[2]), min(b1[3], b2[3])
                    iw = max(0, ix2 - ix1)
                    ih = max(0, iy2 - iy1)
                    inter = iw * ih
                    union = (b1[2] - b1[0]) * (b1[3] - b1[1]) + (b2[2] - b2[0]) * (b2[3] - b2[1]) - inter
                    if union > 0 and (inter / union) > 0.45:
                        is_duplicate = True
                        break

                if not is_duplicate:
                    visible_hens.append(hid)

            # Total counted = total unique sequential hens registered in zone
            self.max_total_hens = max(self.max_total_hens, self.next_hen_number - 1)

            out_detections = []
            for hid in visible_hens:
                d = self.hens[hid]
                b = d["box"]
                x1 = int(max(0, min(fw - 1, b[0])))
                y1 = int(max(0, min(fh - 1, b[1])))
                x2 = int(max(0, min(fw - 1, b[2])))
                y2 = int(max(0, min(fh - 1, b[3])))
                if x2 - x1 < 2 or y2 - y1 < 2:
                    continue
                vx, vy = d.get("velocity", (0.0, 0.0))
                out_detections.append({
                    "hen_number": hid,
                    "box": [x1, y1, x2, y2],
                    "confidence": float(round(d.get("conf", 0.85), 2)),
                    "velocity": [float(round(vx, 2)), float(round(vy, 2))],
                    "track_id": hid,
                    "predicted": False
                })

            # Strictly sort by sequential hen_number: 1, 2, 3, 4, 5...
            out_detections.sort(key=lambda d: d["hen_number"])

            self.latest_detections = out_detections
            elapsed = time.time() - started
            fps = 1.0 / max(0.001, elapsed)

            return {
                "success": True,
                "busy": False,
                "video_time": video_time,
                "frame_width": fw,
                "frame_height": fh,
                "detections": out_detections,
                "total_hens": self.max_total_hens,
                "visible_hens": len(out_detections),
                "ai_frames": self.total_inference_count,
                "ai_fps": round(fps, 1)
            }
