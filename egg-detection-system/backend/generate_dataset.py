import os
import cv2
import numpy as np
import random
import math

base_dir = os.path.abspath(r"c:\Users\sachi\Downloads\giotag project\egg-detection-system\dataset")
for split in ["train", "val"]:
    os.makedirs(os.path.join(base_dir, "images", split), exist_ok=True)
    os.makedirs(os.path.join(base_dir, "labels", split), exist_ok=True)

def generate_background(width=640, height=640):
    bg_type = random.choice(["wood", "carton", "counter", "gradient", "noise", "plain"])
    
    if bg_type == "wood":
        # Wood texture: brownish base with horizontal or vertical grain
        base_color = np.array([random.randint(40, 80), random.randint(80, 140), random.randint(120, 190)], dtype=np.uint8)
        img = np.tile(base_color, (height, width, 1))
        # Add grain
        noise = np.random.normal(0, 15, (height, 1, 3)).astype(np.float32)
        noise = np.repeat(noise, width, axis=1)
        img = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    elif bg_type == "carton":
        # Cardboard / carton gray-brown texture
        c = random.randint(140, 190)
        img = np.full((height, width, 3), (c - 20, c - 10, c), dtype=np.uint8)
        noise = np.random.normal(0, 12, (height, width, 3)).astype(np.float32)
        img = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    elif bg_type == "counter":
        # Dark granite / kitchen counter
        c = random.randint(30, 70)
        img = np.full((height, width, 3), (c, c, c), dtype=np.uint8)
        speckles = (np.random.rand(height, width, 3) * 40).astype(np.uint8)
        img = cv2.add(img, speckles)
    elif bg_type == "gradient":
        # Smooth lighting gradient
        c1 = random.randint(80, 180)
        c2 = random.randint(40, 100)
        col1 = np.linspace(c1, c2, height, dtype=np.uint8)
        col2 = np.linspace(c1-10, c2-10, height, dtype=np.uint8)
        col3 = np.linspace(c1-20, c2-20, height, dtype=np.uint8)
        grad = np.stack([col3, col2, col1], axis=1)
        img = np.repeat(grad[:, np.newaxis, :], width, axis=1)
    elif bg_type == "noise":
        img = np.random.randint(60, 160, (height, width, 3), dtype=np.uint8)
        img = cv2.GaussianBlur(img, (21, 21), 0)
    else:
        c = random.randint(50, 200)
        img = np.full((height, width, 3), (c, c, c), dtype=np.uint8)
        
    return img

def draw_realistic_egg(img, cx, cy, ax, ay, angle):
    """Draws a 3D-shaded realistic egg with soft shadow and returns its exact bounding box (x1, y1, x2, y2)."""
    h_img, w_img = img.shape[:2]
    
    # 1. Egg color choice: white, light cream, warm brown, deep brown
    color_scheme = random.choice(["white", "cream", "light_brown", "dark_brown"])
    if color_scheme == "white":
        base_bgr = [random.randint(220, 245), random.randint(225, 248), random.randint(230, 252)]
        shadow_bgr = [base_bgr[0] - 60, base_bgr[1] - 55, base_bgr[2] - 50]
    elif color_scheme == "cream":
        base_bgr = [random.randint(180, 210), random.randint(205, 230), random.randint(225, 245)]
        shadow_bgr = [base_bgr[0] - 50, base_bgr[1] - 50, base_bgr[2] - 40]
    elif color_scheme == "light_brown":
        base_bgr = [random.randint(120, 160), random.randint(150, 190), random.randint(190, 230)]
        shadow_bgr = [base_bgr[0] - 40, base_bgr[1] - 45, base_bgr[2] - 50]
    else: # dark brown
        base_bgr = [random.randint(70, 110), random.randint(100, 140), random.randint(140, 185)]
        shadow_bgr = [base_bgr[0] - 30, base_bgr[1] - 35, base_bgr[2] - 40]

    # Create local egg canvas for smooth rendering
    max_r = int(max(ax, ay) * 1.6)
    size = max_r * 2 + 10
    egg_layer = np.zeros((size, size, 4), dtype=np.uint8)
    center = (size // 2, size // 2)
    
    # Draw soft drop shadow on the main image
    shadow_offset_x = random.randint(4, 12)
    shadow_offset_y = random.randint(6, 16)
    shadow_mask = np.zeros((h_img, w_img), dtype=np.uint8)
    cv2.ellipse(shadow_mask, (cx + shadow_offset_x, cy + shadow_offset_y), (ax, ay), angle, 0, 360, 255, -1)
    shadow_mask = cv2.GaussianBlur(shadow_mask, (25, 25), 0)
    
    shadow_factor = (shadow_mask.astype(np.float32) / 255.0)[:, :, np.newaxis] * 0.45
    img[:] = np.clip(img.astype(np.float32) * (1.0 - shadow_factor), 0, 255).astype(np.uint8)

    # Render egg body with radial gradient (simulating light source)
    # Mask of the egg ellipse
    egg_mask = np.zeros((size, size), dtype=np.uint8)
    cv2.ellipse(egg_mask, center, (ax, ay), angle, 0, 360, 255, -1)
    
    # Compute lighting from top-left
    rad_ang = math.radians(angle)
    light_x = center[0] - int(ax * 0.35)
    light_y = center[1] - int(ay * 0.35)
    
    y_coords, x_coords = np.ogrid[:size, :size]
    dist_from_light = np.sqrt((x_coords - light_x)**2 + (y_coords - light_y)**2)
    max_d = max(ax, ay) * 1.5
    light_intensity = np.clip(1.0 - (dist_from_light / max_d), 0.0, 1.0)
    
    for c in range(3):
        channel = shadow_bgr[c] + (base_bgr[c] - shadow_bgr[c]) * light_intensity
        egg_layer[:, :, c] = np.clip(channel, 0, 255).astype(np.uint8)
    egg_layer[:, :, 3] = egg_mask

    # Add specular highlight
    highlight_mask = np.zeros((size, size), dtype=np.uint8)
    cv2.ellipse(highlight_mask, (light_x, light_y), (max(3, int(ax * 0.25)), max(3, int(ay * 0.2))), angle, 0, 360, 255, -1)
    highlight_mask = cv2.GaussianBlur(highlight_mask, (11, 11), 0)
    for c in range(3):
        hl = egg_layer[:, :, c].astype(np.float32) + (highlight_mask.astype(np.float32) / 255.0) * 50
        egg_layer[:, :, c] = np.clip(hl, 0, 255).astype(np.uint8)

    # Optional speckles (for natural egg texture)
    if random.random() > 0.4:
        speckle_noise = (np.random.rand(size, size) > 0.96).astype(np.uint8) * 35
        for c in range(3):
            egg_layer[:, :, c] = np.clip(egg_layer[:, :, c].astype(np.int16) - speckle_noise, 0, 255).astype(np.uint8)

    # Alpha blend egg into main image
    x1_dest = max(0, cx - center[0])
    y1_dest = max(0, cy - center[1])
    x2_dest = min(w_img, cx + center[0])
    y2_dest = min(h_img, cy + center[1])
    
    x1_src = max(0, center[0] - cx)
    y1_src = max(0, center[1] - cy)
    x2_src = x1_src + (x2_dest - x1_dest)
    y2_src = y1_src + (y2_dest - y1_dest)
    
    if x2_dest > x1_dest and y2_dest > y1_dest:
        crop_src = egg_layer[y1_src:y2_src, x1_src:x2_src]
        alpha = (crop_src[:, :, 3].astype(np.float32) / 255.0)[:, :, np.newaxis]
        target = img[y1_dest:y2_dest, x1_dest:x2_dest].astype(np.float32)
        blended = target * (1.0 - alpha) + crop_src[:, :, :3].astype(np.float32) * alpha
        img[y1_dest:y2_dest, x1_dest:x2_dest] = blended.astype(np.uint8)

    # Calculate exact bounding box using rotated ellipse points
    # Parametric equations of rotated ellipse:
    rad = math.radians(angle)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    w_extent = math.sqrt((ax * cos_a)**2 + (ay * sin_a)**2)
    h_extent = math.sqrt((ax * sin_a)**2 + (ay * cos_a)**2)
    
    bx1 = max(0, int(cx - w_extent))
    by1 = max(0, int(cy - h_extent))
    bx2 = min(w_img, int(cx + w_extent))
    by2 = min(h_img, int(cy + h_extent))
    
    return bx1, by1, bx2, by2

def generate_image_with_eggs(num_eggs, img_size=640):
    img = generate_background(img_size, img_size)
    labels = []
    
    # Generate eggs with placement strategies: random or tray-grid
    use_grid = random.random() < 0.4 and num_eggs >= 4
    
    positions = []
    if use_grid:
        rows = math.ceil(math.sqrt(num_eggs))
        cols = math.ceil(num_eggs / rows)
        spacing_x = int(480 / max(1, cols))
        spacing_y = int(480 / max(1, rows))
        for r in range(rows):
            for c in range(cols):
                if len(positions) < num_eggs:
                    px = 80 + c * spacing_x + random.randint(-15, 15)
                    py = 80 + r * spacing_y + random.randint(-15, 15)
                    positions.append((px, py))
    else:
        for _ in range(num_eggs):
            px = random.randint(70, img_size - 70)
            py = random.randint(70, img_size - 70)
            positions.append((px, py))
            
    for (cx, cy) in positions:
        # Egg dimensions: radius a and b (aspect ratio ~1.25 to 1.45)
        base_radius = random.randint(26, 52)
        ratio = random.uniform(1.22, 1.44)
        ax = base_radius
        ay = int(base_radius * ratio)
        angle = random.randint(0, 180)
        
        bx1, by1, bx2, by2 = draw_realistic_egg(img, cx, cy, ax, ay, angle)
        
        # Normalize for YOLO (class x_center y_center width height)
        bw = (bx2 - bx1) / float(img_size)
        bh = (by2 - by1) / float(img_size)
        bcx = (bx1 + bx2) / 2.0 / float(img_size)
        bcy = (by1 + by2) / 2.0 / float(img_size)
        
        if bw > 0.03 and bh > 0.03:
            labels.append(f"0 {bcx:.6f} {bcy:.6f} {bw:.6f} {bh:.6f}")
            
    # Final image augmentation: slight blur or noise
    if random.random() < 0.3:
        img = cv2.GaussianBlur(img, (3, 3), 0)
        
    return img, labels

def main():
    print("Generating 150 diverse training images and 30 validation images...")
    for split, count in [("train", 150), ("val", 30)]:
        for i in range(count):
            num_eggs = random.choice([1, 2, 3, 4, 6, 8, 10, 12, 15, 20])
            img, labels = generate_image_with_eggs(num_eggs, img_size=640)
            
            img_path = os.path.join(base_dir, "images", split, f"egg_{split}_{i:03d}.jpg")
            label_path = os.path.join(base_dir, "labels", split, f"egg_{split}_{i:03d}.txt")
            
            cv2.imwrite(img_path, img)
            with open(label_path, "w") as f:
                f.write("\n".join(labels))
                
    print(f"Generated realistic dataset successfully in {base_dir}")

if __name__ == "__main__":
    main()
