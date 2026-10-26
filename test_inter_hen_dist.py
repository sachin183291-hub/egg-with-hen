import cv2
import numpy as np
import math
from collections import deque
from ultralytics import YOLO

# Test script to verify persistent hen tracking without ID switching
video_path = "uploads/DJI_20260911155924_0026_V.MP4"
cap = cv2.VideoCapture(video_path)
model = YOLO("yolov8n.pt")

fw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
print(f"Video resolution: {fw}x{fh}")

def extract_snug_heads(frame, raw_boxes, raw_confs):
    h_img, w_img = frame.shape[:2]
    b_ch, g_ch, r_ch = cv2.split(frame.astype(np.float32))
    red_diff = r_ch - np.maximum(g_ch, b_ch)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    h_ch, s_ch, v_ch = cv2.split(hsv)
    comb_mask = ((red_diff >= 34) & (s_ch >= 60) & (v_ch >= 50) & ((h_ch < 14) | (h_ch > 166))).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    comb_mask = cv2.morphologyEx(comb_mask, cv2.MORPH_OPEN, kernel)
    min_comb_area = max(35, int(0.000035 * w_img * h_img))
    
    heads = []
    for box, conf in zip(raw_boxes, raw_confs):
        if float(conf) < 0.05:
            continue
        bx1, by1 = max(0, int(box[0])), max(0, int(box[1]))
        bx2, by2 = min(w_img - 1, int(box[2])), min(h_img - 1, int(box[3]))
        if bx2 <= bx1 or by2 <= by1:
            continue
        crop_mask = comb_mask[by1:by2, bx1:bx2]
        if crop_mask.size == 0 or cv2.countNonZero(crop_mask) < min_comb_area:
            continue
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(crop_mask)
        for idx in range(1, num_labels):
            area = stats[idx, cv2.CC_STAT_AREA]
            cw = stats[idx, cv2.CC_STAT_WIDTH]
            ch = stats[idx, cv2.CC_STAT_HEIGHT]
            if area >= min_comb_area and cw >= 8 and ch >= 8:
                comp_cx, comp_cy = centroids[idx]
                cx = bx1 + comp_cx
                cy = by1 + comp_cy
                head_w = max(int(0.015 * w_img), min(int(0.040 * w_img), int(cw * 1.30 + 0.005 * w_img)))
                head_h = max(int(0.018 * h_img), min(int(0.045 * h_img), int(ch * 1.30 + 0.006 * h_img)))
                hx1 = max(0, int(cx - head_w / 2.0))
                hy1 = max(0, int(cy - head_h / 2.0))
                hx2 = min(w_img - 1, int(cx + head_w / 2.0))
                hy2 = min(h_img - 1, int(cy + head_h / 2.0))
                heads.append({
                    "box": [hx1, hy1, hx2, hy2],
                    "center": (cx, cy),
                    "conf": float(conf)
                })
    # Deduplicate heads
    kept = []
    for h in sorted(heads, key=lambda x: x["conf"], reverse=True):
        if not any(math.hypot(h["center"][0]-k["center"][0], h["center"][1]-k["center"][1]) < (0.018 * w_img) for k in kept):
            kept.append(h)
    return kept

# Let's inspect nearest neighbor distance between heads in frame 1
ret, frame = cap.read()
res = model.predict(frame, imgsz=640, conf=0.05, verbose=False)[0]
heads0 = extract_snug_heads(frame, res.boxes.xyxy.cpu().numpy(), res.boxes.conf.cpu().numpy())
print(f"Frame 1 detected heads: {len(heads0)}")

dists = []
for i in range(len(heads0)):
    min_d = 99999
    for j in range(len(heads0)):
        if i != j:
            d = math.hypot(heads0[i]["center"][0]-heads0[j]["center"][0], heads0[i]["center"][1]-heads0[j]["center"][1])
            if d < min_d:
                min_d = d
    dists.append(min_d)
print(f"Minimum distance between any two different hens: {min(dists):.1f} px, Mean min-dist: {np.mean(dists):.1f} px, Max min-dist: {max(dists):.1f} px")
cap.release()
