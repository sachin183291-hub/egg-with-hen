import asyncio
from app.ai.stable_tracker import StableHenTracker

def test_tracker():
    tracker = StableHenTracker("best.pt")
    
    counts_dict = {"test": {"visible_hens": 0, "total_hens": 0}}
    
    # Need a small test video
    # I will just run the generator for 5 frames and print the counts
    # But wait, we don't have a video path right now.
    print("Tracker loaded")

if __name__ == "__main__":
    test_tracker()
