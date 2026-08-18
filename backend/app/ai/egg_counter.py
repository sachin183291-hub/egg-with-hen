import cv2
import numpy as np
import base64

def count_objects_in_image(image_bytes: bytes) -> dict:
    """
    Counts clustered objects (like eggs) in the image using OpenCV Watershed algorithm.
    Returns the count and a base64 encoded image with drawn bounding boxes.
    """
    # 1. Decode image
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        raise ValueError("Could not decode image.")
        
    # Resize image to speed up processing and standardize object sizes
    max_dim = 1024
    h, w = img.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)))

    # 2. Preprocessing
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Apply Gaussian blur to reduce detail noise
    blurred = cv2.GaussianBlur(gray, (15, 15), 0)
    
    # 3. Thresholding
    # Adaptive thresholding handles varying lighting conditions well
    thresh = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                   cv2.THRESH_BINARY_INV, 21, 2)
    
    # 4. Noise removal using morphological operations
    kernel = np.ones((5,5), np.uint8)
    opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=2)
    opening = cv2.morphologyEx(opening, cv2.MORPH_CLOSE, kernel, iterations=2)

    # 5. Sure background area (dilation)
    sure_bg = cv2.dilate(opening, kernel, iterations=3)

    # 6. Finding sure foreground area (distance transform)
    # This separates touching objects
    dist_transform = cv2.distanceTransform(opening, cv2.DIST_L2, 5)
    # Increased threshold (0.5) to be more conservative about what constitutes a center
    ret, sure_fg = cv2.threshold(dist_transform, 0.5 * dist_transform.max(), 255, 0)

    # 7. Finding unknown region
    sure_fg = np.uint8(sure_fg)
    unknown = cv2.subtract(sure_bg, sure_fg)

    # 8. Marker labelling for Watershed
    ret, markers = cv2.connectedComponents(sure_fg)

    # Add one to all labels so that sure background is not 0, but 1
    markers = markers + 1

    # Mark the region of unknown with zero
    markers[unknown == 255] = 0

    # 9. Apply watershed
    markers = cv2.watershed(img, markers)
    
    # 10. Count objects and draw bounding boxes
    count = 0
    # The labels in markers are 1 (background) to N (objects). -1 is boundary.
    for label in np.unique(markers):
        if label == 1 or label == -1:
            continue
            
        # Create a mask for the current object
        mask = np.zeros(gray.shape, dtype="uint8")
        mask[markers == label] = 255
        
        # Find contours for the current object
        contours, hierarchy = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if len(contours) > 0:
            c = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(c)
            perimeter = cv2.arcLength(c, True)
            if perimeter == 0: continue
            circularity = 4 * np.pi * (area / (perimeter * perimeter))
            
            # Filter out small noise and non-circular objects
            if area > 500 and circularity > 0.5:
                # Draw the bounding box
                x, y, w, h = cv2.boundingRect(c)
                cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)
                count += 1

    # 11. Encode the resulting image to base64
    _, buffer = cv2.imencode('.jpg', img)
    encoded_img = base64.b64encode(buffer).decode('utf-8')
    
    return {
        "count": count,
        "processed_image_b64": encoded_img
    }
