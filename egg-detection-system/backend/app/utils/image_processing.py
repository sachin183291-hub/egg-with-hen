import cv2
import numpy as np

def resize_image(image_path: str, max_width: int = 1280):
    """
    Resizes image if it's too large to prevent out of memory issues.
    """
    image = cv2.imread(image_path)
    if image is None:
        return None
        
    h, w = image.shape[:2]
    if w > max_width:
        ratio = max_width / w
        new_h = int(h * ratio)
        image = cv2.resize(image, (max_width, new_h))
        cv2.imwrite(image_path, image)
        
    return image
