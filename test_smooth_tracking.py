import cv2
import numpy as np
import math

from live_hen_tracker import LiveHenTracker

def test_smoothness(video_path, frames=50):
    print(f"\nTesting smooth tracking on: {video_path}")
    tracker = LiveHenTracker(video_source=video_path, show_hud=False)
    cap = cv2.VideoCapture(video_path)
    
    # We will measure:
    # 1. Total unique IDs allocated across all frames (should NOT increase after frame 5)
    # 2. Maximum jump in pixels between consecutive frames for each hen (smoothness)
    # 3. Minimum distance between any two hens (should never be < 45px = double box)
    
    prev_centers = {}
    id_allocations = set()
    double_boxes_count = 0
    max_jump = 0
    
    for fn in range(1, frames + 1):
        ret, frame = cap.read()
        if not ret: break
        
        # Inference
        results = tracker.model.predict(frame, conf=0.22, verbose=False, imgsz=640)
        boxes_xyxy = results[0].boxes.xyxy.cpu().numpy() if len(results) > 0 and results[0].boxes is not None else np.empty((0, 4))
        confs = results[0].boxes.conf.cpu().numpy() if len(results) > 0 and results[0].boxes is not None else np.empty((0,))
        dets = tracker.extract_snug_heads(frame, boxes_xyxy, confs)
        
        # In frame 1
        if fn == 1:
            dets.sort(key=lambda d: d["center"][1] * 2.0 + d["center"][0])
            for d in dets:
                num = tracker.next_hen_number
                tracker.next_hen_number += 1
                tracker.hens[num] = {
                    "center": d["center"],
                    "box": list(d["box"]),
                    "lost": 0,
                    "hits": 3
                }
                id_allocations.add(num)
            print(f"Frame 1: Registered {len(tracker.hens)} hens: {sorted(list(id_allocations))}")
            continue
            
        # Match detections to existing hens using global minimum distance
        matched_dets = set()
        used_hens = set()
        
        cands = []
        for d_idx, det in enumerate(dets):
            cx, cy = det["center"]
            for num, hdata in tracker.hens.items():
                if hdata["lost"] > 45: continue
                hx, hy = hdata["center"]
                dist = math.hypot(cx - hx, cy - hy)
                cands.append((dist, d_idx, num))
                
        cands.sort(key=lambda x: x[0])
        for dist, d_idx, num in cands:
            if d_idx in matched_dets or num in used_hens:
                continue
            if dist > 220.0:
                continue
            matched_dets.add(d_idx)
            used_hens.add(num)
            det = dets[d_idx]
            old_cx, old_cy = tracker.hens[num]["center"]
            jump = math.hypot(det["center"][0] - old_cx, det["center"][1] - old_cy)
            if jump > max_jump:
                max_jump = jump
            # Smooth EMA position update
            new_cx = 0.85 * det["center"][0] + 0.15 * old_cx
            new_cy = 0.85 * det["center"][1] + 0.15 * old_cy
            tracker.hens[num]["center"] = (new_cx, new_cy)
            tracker.hens[num]["box"] = list(det["box"])
            tracker.hens[num]["lost"] = 0
            tracker.hens[num]["hits"] = tracker.hens[num].get("hits", 0) + 1
            
        # Any hen not matched gets lost += 1
        for num, hdata in tracker.hens.items():
            if num not in used_hens:
                hdata["lost"] += 1
                
        # Only genuinely new hens if far from ALL existing hens (> 160px)
        for d_idx, det in enumerate(dets):
            if d_idx in matched_dets: continue
            cx, cy = det["center"]
            if all(math.hypot(cx - h["center"][0], cy - h["center"][1]) > 160.0 for h in tracker.hens.values() if h["lost"] <= 45):
                num = tracker.next_hen_number
                tracker.next_hen_number += 1
                tracker.hens[num] = {"center": (cx, cy), "box": list(det["box"]), "lost": 0, "hits": 1}
                id_allocations.add(num)
                print(f"Frame {fn}: Truly new hen entered -> Hen {num}")
                
        # Check double boxes
        active_hens = [num for num, h in tracker.hens.items() if h["lost"] <= 2]
        for i in range(len(active_hens)):
            for j in range(i + 1, len(active_hens)):
                h1 = tracker.hens[active_hens[i]]
                h2 = tracker.hens[active_hens[j]]
                d = math.hypot(h1["center"][0] - h2["center"][0], h1["center"][1] - h2["center"][1])
                if d < 45.0:
                    double_boxes_count += 1
                    
        if fn % 15 == 0:
            print(f"Frame {fn:02d}: ActiveVisible={len(active_hens)}, TotalAllocated={len(id_allocations)}")
            
    cap.release()
    print(f"Result: Max jump = {max_jump:.1f}px, Double boxes = {double_boxes_count}, Final IDs count = {len(id_allocations)}")

if __name__ == '__main__':
    test_smoothness('uploads/demo_hen_video.mp4', frames=45)
    test_smoothness('uploads/DJI_20260911145052_0001_S.MP4', frames=30)
