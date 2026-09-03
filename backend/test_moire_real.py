import cv2
import numpy as np
import sys
import glob

def perform_moire_analysis(image_path: str):
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None: return
    img = cv2.resize(img, (512, 512))
    
    f = np.fft.fft2(img)
    fshift = np.fft.fftshift(f)
    magnitude_spectrum = 20 * np.log(np.abs(fshift) + 1)
    
    rows, cols = img.shape
    crow, ccol = rows // 2, cols // 2
    
    mask = np.ones((rows, cols), np.uint8)
    r = 50
    cv2.circle(mask, (ccol, crow), r, 0, -1)
    thickness = 20
    mask[crow-thickness:crow+thickness, :] = 0
    mask[:, ccol-thickness:ccol+thickness] = 0
    
    masked_spectrum = magnitude_spectrum * mask
    valid_pixels = masked_spectrum[mask > 0]
    
    mean_val = np.mean(valid_pixels)
    max_val = np.max(valid_pixels)
    
    peak_ratio = max_val / (mean_val + 1e-5)
    
    threshold = mean_val + 4 * np.std(valid_pixels)
    peaks = np.sum(valid_pixels > threshold)
    
    print(f"File: {image_path[-20:]} | Ratio: {peak_ratio:.2f} | Peaks: {peaks} | Max: {max_val:.2f} | Mean: {mean_val:.2f}")

for f in glob.glob("c:\\Users\\sachi\\Downloads\\giotag project\\backend\\uploads\\evidence\\*.jpg")[:5]:
    perform_moire_analysis(f)
