import os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Create synthetic drawn test images
def create_drawn_eggs():
    img = np.ones((400, 600, 3), dtype=np.uint8) * 255 # White background
    # Draw 5 egg ovals with black outline (like drawn with a pen/marker)
    cv2.ellipse(img, (100, 200), (40, 60), 0, 0, 360, (0, 0, 0), 3)
    cv2.ellipse(img, (200, 180), (35, 55), 10, 0, 360, (50, 50, 50), 3)
    cv2.ellipse(img, (300, 210), (45, 65), -5, 0, 360, (0, 0, 0), 4)
    cv2.ellipse(img, (400, 190), (38, 58), 15, 0, 360, (30, 30, 30), 3)
    cv2.ellipse(img, (500, 200), (42, 62), -10, 0, 360, (0, 0, 0), 3)
    out_path = os.path.join(BASE_DIR, "test_drawn_eggs.jpg")
    cv2.imwrite(out_path, img)
    print(f"Created {out_path} (5 drawn eggs)")
    return out_path

def create_drawn_trays():
    img = np.ones((500, 700, 3), dtype=np.uint8) * 255 # White background
    # Draw 2 distinct egg tray grids (5x6 grid representations)
    # Tray 1
    cv2.rectangle(img, (50, 80), (300, 400), (0, 150, 0), 4)
    for i in range(1, 6):
        cv2.line(img, (50, 80 + i * (320 // 6)), (300, 80 + i * (320 // 6)), (0, 150, 0), 2)
    for j in range(1, 5):
        cv2.line(img, (50 + j * (250 // 5), 80), (50 + j * (250 // 5), 400), (0, 150, 0), 2)
    
    # Tray 2
    cv2.rectangle(img, (380, 80), (630, 400), (0, 100, 200), 4)
    for i in range(1, 6):
        cv2.line(img, (380, 80 + i * (320 // 6)), (630, 80 + i * (320 // 6)), (0, 100, 200), 2)
    for j in range(1, 5):
        cv2.line(img, (380 + j * (250 // 5), 80), (380 + j * (250 // 5), 400), (0, 100, 200), 2)
    
    out_path = os.path.join(BASE_DIR, "test_drawn_trays.jpg")
    cv2.imwrite(out_path, img)
    print(f"Created {out_path} (2 drawn trays)")
    return out_path

def create_drawn_hens():
    img = np.ones((400, 700, 3), dtype=np.uint8) * 255
    # Draw 3 simple chicken / hen doodles
    # Hen 1
    cv2.circle(img, (150, 220), 40, (0, 0, 0), 3) # Body
    cv2.circle(img, (180, 170), 20, (0, 0, 0), 3) # Head
    pts_beak = np.array([[200, 170], [215, 175], [200, 180]], np.int32)
    cv2.fillPoly(img, [pts_beak], (0, 165, 255)) # Orange beak
    pts_comb = np.array([[175, 150], [185, 140], [195, 150]], np.int32)
    cv2.fillPoly(img, [pts_comb], (0, 0, 255)) # Red comb
    cv2.line(img, (140, 260), (140, 300), (0, 0, 0), 3) # Leg 1
    cv2.line(img, (160, 260), (160, 300), (0, 0, 0), 3) # Leg 2

    # Hen 2
    cv2.circle(img, (350, 220), 40, (0, 0, 0), 3)
    cv2.circle(img, (380, 170), 20, (0, 0, 0), 3)
    pts_beak2 = np.array([[400, 170], [415, 175], [400, 180]], np.int32)
    cv2.fillPoly(img, [pts_beak2], (0, 165, 255))
    pts_comb2 = np.array([[375, 150], [385, 140], [395, 150]], np.int32)
    cv2.fillPoly(img, [pts_comb2], (0, 0, 255))
    cv2.line(img, (340, 260), (340, 300), (0, 0, 0), 3)
    cv2.line(img, (360, 260), (360, 300), (0, 0, 0), 3)

    # Hen 3
    cv2.circle(img, (550, 220), 40, (0, 0, 0), 3)
    cv2.circle(img, (580, 170), 20, (0, 0, 0), 3)
    pts_beak3 = np.array([[600, 170], [615, 175], [600, 180]], np.int32)
    cv2.fillPoly(img, [pts_beak3], (0, 165, 255))
    pts_comb3 = np.array([[575, 150], [585, 140], [595, 150]], np.int32)
    cv2.fillPoly(img, [pts_comb3], (0, 0, 255))
    cv2.line(img, (540, 260), (540, 300), (0, 0, 0), 3)
    cv2.line(img, (560, 260), (560, 300), (0, 0, 0), 3)

    out_path = os.path.join(BASE_DIR, "test_drawn_hens.jpg")
    cv2.imwrite(out_path, img)
    print(f"Created {out_path} (3 drawn hens)")
    return out_path

if __name__ == "__main__":
    create_drawn_eggs()
    create_drawn_trays()
    create_drawn_hens()
