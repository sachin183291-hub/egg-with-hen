import cv2
import threading
import time
from ultralytics import YOLO

class LiveHenTracker:
    def __init__(self, model_path='yolov8n.pt', video_source=0):
        """
        Initialize the tracker.
        :param model_path: Path to your trained YOLOv8 model (e.g., 'best.pt')
        :param video_source: 0 for webcam, or path to a video file (e.g., 'test.mp4')
        """
        print(f"Loading model from {model_path}...")
        self.model = YOLO(model_path)
        
        self.video_source = video_source
        self.cap = cv2.VideoCapture(video_source)
        
        # Shared variables between main thread and ML thread
        self.latest_frame = None
        self.frame_lock = threading.Lock()
        
        self.latest_results = None
        self.results_lock = threading.Lock()
        
        self.unique_hen_ids = set()
        self.is_running = True
        
    def ml_processing_thread(self):
        """Background thread for running ML tracking on the latest frame without blocking video."""
        while self.is_running:
            # Grab the most recent frame
            with self.frame_lock:
                frame = self.latest_frame
                
            if frame is None:
                time.sleep(0.01)
                continue
                
            # Run YOLO tracking in the background
            # persist=True enables object tracking (ByteTrack/BoT-SORT) 
            # which assigns consistent IDs across frames even when the camera moves.
            results = self.model.track(frame, persist=True, verbose=False, conf=0.25)
            
            # Update unique IDs based on tracker output
            if results and len(results) > 0 and results[0].boxes and results[0].boxes.id is not None:
                track_ids = results[0].boxes.id.int().cpu().tolist()
                for track_id in track_ids:
                    self.unique_hen_ids.add(track_id)
            
            # Save results so the main thread can draw bounding boxes
            with self.results_lock:
                self.latest_results = results[0] if len(results) > 0 else None
                
    def run(self):
        # Start ML background thread
        ml_thread = threading.Thread(target=self.ml_processing_thread)
        ml_thread.daemon = True
        ml_thread.start()
        
        print("Starting live video... Press 'q' to quit.")
        
        while self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret:
                print("End of video stream or cannot read frame.")
                break
                
            # Update the latest frame for the background thread
            with self.frame_lock:
                self.latest_frame = frame.copy()
                
            # Get the latest available ML results
            with self.results_lock:
                results = self.latest_results
                
            # Draw results on the CURRENT frame
            display_frame = frame.copy()
            if results is not None and results.boxes is not None:
                for box in results.boxes:
                    # Filter for specific classes if using generic yolov8n (Class 14 is 'bird' in COCO)
                    # If you use your trained model, you can remove this check or adjust class IDs
                    cls_id = int(box.cls[0])
                    
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    track_id = int(box.id[0]) if box.id is not None else -1
                    conf = float(box.conf[0])
                    
                    # Draw Bounding Box
                    cv2.rectangle(display_frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
                    
                    # Label text
                    label = f"Hen {track_id}" if track_id != -1 else "Hen"
                    cv2.putText(display_frame, label, (x1, y1 - 10), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
                
            # Display Live Unique Hen Count
            count_text = f"Live Unique Hen Count: {len(self.unique_hen_ids)}"
            # Background rectangle for text
            cv2.rectangle(display_frame, (10, 10), (550, 70), (0, 0, 0), -1)
            cv2.putText(display_frame, count_text, (20, 50), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)
                        
            # Show the video continuously at camera speed
            cv2.imshow("Live Hen Tracker", display_frame)
            
            # 1ms delay for continuous non-blocking video playback
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
        # Cleanup
        self.is_running = False
        ml_thread.join()
        self.cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    # --- IMPORTANT ---
    # 1. model_path = 'your_trained_model.pt' (Replace with your actual custom trained model path)
    # 2. video_source = 0 (for webcam) OR 'test.mp4' (for a saved video)
    tracker = LiveHenTracker(model_path='yolov8n.pt', video_source=0)
    tracker.run()
