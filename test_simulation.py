import cv2, math, time
import numpy as np
from ultralytics import YOLO

OUT_W, OUT_H = 640, 360

def compute_iou(b1, b2):
    ix1, iy1 = max(b1[0], b2[0]), max(b1[1], b2[1])
    ix2, iy2 = min(b1[2], b2[2]), min(b1[3], b2[3])
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0: return 0.0
    a1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
    a2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
    u = a1 + a2 - inter
    return inter / u if u > 0 else 0.0

def filter_and_scale_dets(raw_boxes, raw_confs, disp_img, in_w=OUT_W, in_h=OUT_H):
    scale_x = OUT_W / float(in_w)
    scale_y = OUT_H / float(in_h)
    valid = []
    for b, c in zip(raw_boxes, raw_confs):
        if float(c) < 0.12:  # High-sensitivity 0.12 for maximum recall
            continue
        x1 = max(0, min(OUT_W - 1, int(float(b[0]) * scale_x)))
        y1 = max(0, min(OUT_H - 1, int(float(b[1]) * scale_y)))
        x2 = max(0, min(OUT_W - 1, int(float(b[2]) * scale_x)))
        y2 = max(0, min(OUT_H - 1, int(float(b[3]) * scale_y)))
        bw, bh = x2 - x1, y2 - y1
        if bw < 6 or bh < 6:
            continue

        cx = int((x1 + x2) / 2.0)
        cy = int((y1 + y2) / 2.0)

        valid.append({
            "box": [x1, y1, x2, y2],
            "center": (cx, cy),
            "conf": float(c),
            "diag": math.hypot(bw, bh)
        })

    valid.sort(key=lambda d: d["conf"], reverse=True)
    kept = []
    head_radius = 16.0  # Tight comb NMS: only suppress duplicate boxes on SAME comb, never separate hens
    for d in valid:
        overlap = False
        for ex in kept:
            iou = compute_iou(d["box"], ex["box"])
            cdist = math.hypot(d["center"][0] - ex["center"][0], d["center"][1] - ex["center"][1])
            if iou > 0.45 or cdist < head_radius:
                overlap = True
                break
        if not overlap:
            kept.append(d)
    return kept

model = YOLO("backend/best.pt")
cap = cv2.VideoCapture("test_720p.mp4")

hens = {}
next_id = 1
frame_no = 0

print("Testing instant disappearing when hen leaves & zero-lag comb lock...", flush=True)

while cap.isOpened() and frame_no < 150:
    ret, frame = cap.read()
    if not ret: break
    frame_no += 1
    display = cv2.resize(frame, (OUT_W, OUT_H))
    
    # AI every 2 frames for fast, responsive comb tracking
    if frame_no % 2 == 0 or frame_no == 1:
        res = model.predict(display, imgsz=640, conf=0.12, verbose=False)[0]
        if res.boxes is not None:
            bx = res.boxes.xyxy.cpu().numpy()
            cf = res.boxes.conf.cpu().numpy()
            fresh = filter_and_scale_dets(bx, cf, display, OUT_W, OUT_H)
        else:
            fresh = []
            
        used_dets = set()
        used_hens = set()
        
        if len(hens) == 0:
            fresh.sort(key=lambda d: d["center"][1] * 2.0 + d["center"][0])
            for det in fresh:
                hid = next_id
                next_id += 1
                hens[hid] = {
                    "box": list(det["box"]),
                    "center": det["center"],
                    "velocity": (0.0, 0.0),
                    "lost": 0,
                    "hits": 3
                }
        else:
            MAX_MATCH_DIST = 70.0
            active_matches = []
            for det_idx, det in enumerate(fresh):
                cx, cy = det["center"]
                for hid, hdata in hens.items():
                    if hdata["lost"] > 25:
                        continue
                    hx, hy = hdata["center"]
                    vx, vy = hdata.get("velocity", (0.0, 0.0))
                    pred_hx, pred_hy = hx + vx, hy + vy
                    dist = min(math.hypot(cx - hx, cy - hy), math.hypot(cx - pred_hx, cy - pred_hy))
                    iou = compute_iou(hdata["box"], det["box"])
                    if iou >= 0.05 or dist <= MAX_MATCH_DIST:
                        cost = (1.0 - iou) * 0.3 + (dist / MAX_MATCH_DIST) * 0.7
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

                old_cx, old_cy = hens[hid]["center"]
                raw_vx = max(-35.0, min(35.0, det_cx - old_cx))
                raw_vy = max(-35.0, min(35.0, det_cy - old_cy))
                ovx, ovy = hens[hid].get("velocity", (0.0, 0.0))
                hens[hid]["velocity"] = (0.6 * raw_vx + 0.4 * ovx, 0.6 * raw_vy + 0.4 * ovy)

                # Direct zero-lag box update on the comb
                hens[hid]["box"] = list(nb)
                hens[hid]["center"] = (det_cx, det_cy)
                hens[hid]["lost"] = 0
                hens[hid]["hits"] = hens[hid].get("hits", 0) + 1

            REID_DIST = 180.0
            for det_idx, det in enumerate(fresh):
                if det_idx in used_dets:
                    continue
                cx, cy = det["center"]
                best_hid, best_d = None, float("inf")
                for hid, hdata in hens.items():
                    if hid in used_hens:
                        continue
                    hx, hy = hdata["center"]
                    vx, vy = hdata.get("velocity", (0.0, 0.0))
                    pred_hx, pred_hy = hx + vx, hy + vy
                    dist = min(math.hypot(cx - hx, cy - hy), math.hypot(cx - pred_hx, cy - pred_hy))
                    if dist < REID_DIST and dist < best_d:
                        best_d = dist
                        best_hid = hid
                if best_hid is not None:
                    used_dets.add(det_idx)
                    used_hens.add(best_hid)
                    det = fresh[det_idx]
                    hens[best_hid]["box"] = list(det["box"])
                    hens[best_hid]["center"] = det["center"]
                    hens[best_hid]["velocity"] = (0.0, 0.0)
                    hens[best_hid]["lost"] = 0
                    hens[best_hid]["hits"] = hens[best_hid].get("hits", 0) + 1

            for hid, hdata in hens.items():
                if hid not in used_hens:
                    hdata["lost"] += 1

            MIN_NEW_DIST = 100.0
            for det_idx, det in enumerate(fresh):
                if det_idx in used_dets:
                    continue
                cx, cy = det["center"]
                too_close = any(
                    min(
                        math.hypot(cx - h["center"][0], cy - h["center"][1]),
                        math.hypot(cx - (h["center"][0] + h.get("velocity", (0, 0))[0]), cy - (h["center"][1] + h.get("velocity", (0, 0))[1]))
                    ) < MIN_NEW_DIST
                    for h in hens.values()
                )
                if not too_close:
                    hid = next_id
                    next_id += 1
                    hens[hid] = {
                        "box": list(det["box"]),
                        "center": (cx, cy),
                        "velocity": (0.0, 0.0),
                        "lost": 0,
                        "hits": 1
                    }
                    used_hens.add(hid)
                    print(f"  [Frame {frame_no}] New hen ID minted: Hen {hid}", flush=True)

    for hid in list(hens.keys()):
        b = hens[hid]["box"]
        if b[2] < -30 or b[0] > OUT_W + 30 or b[3] < -30 or b[1] > OUT_H + 30:
            del hens[hid]

    # USER INSTRUCTION: Only render box while hen is actively visible in this frame (lost == 0)!
    # As soon as hen leaves or disappears, the box disappears immediately!
    candidate_visible = [hid for hid, d in hens.items() if d["lost"] == 0 and d.get("hits", 0) >= 1]
    candidate_visible.sort(key=lambda hid: (hens[hid].get("hits", 0), -hens[hid].get("lost", 0)), reverse=True)

    visible_hens = []
    for hid in candidate_visible:
        cx, cy = hens[hid]["center"]
        box = hens[hid]["box"]
        is_duplicate = False
        for v_hid in visible_hens:
            v_cx, v_cy = hens[v_hid]["center"]
            v_box = hens[v_hid]["box"]
            dist = math.hypot(cx - v_cx, cy - v_cy)
            iou = compute_iou(box, v_box)
            if dist < 16.0 or iou > 0.40:
                is_duplicate = True
                break
        if not is_duplicate:
            visible_hens.append(hid)

    current_live_count = len(visible_hens)
    current_total_count = max(current_live_count, len([hid for hid, d in hens.items() if d.get("hits", 0) >= 2]))

    if frame_no % 30 == 0 or frame_no == 1:
        print(f"Frame {frame_no:3d}: live_combs={current_live_count:2d}, total_hens={current_total_count:2d}, visible_ids={sorted(visible_hens)}", flush=True)

cap.release()
print("Simulation complete! Final total count:", current_total_count, flush=True)
