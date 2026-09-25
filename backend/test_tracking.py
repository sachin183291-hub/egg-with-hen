import requests
import time
import json
import asyncio
import websockets

def test_upload():
    url = "http://127.0.0.1:8000/api/tracker/upload"
    video_path = r"C:\Users\sachi\Downloads\giotag project\backend\tiny_test.mp4"
    
    print(f"Uploading {video_path}...")
    with open(video_path, 'rb') as f:
        files = {'file': ('video.mp4', f, 'video/mp4')}
        response = requests.post(url, files=files)
        
    print(f"Response: {response.status_code}")
    if response.status_code != 200:
        print("Upload failed.")
        return None
        
    data = response.json()
    print("Upload Data:", data)
    return data.get("job_id")

async def test_websocket(job_id):
    ws_url = f"ws://127.0.0.1:8000/api/tracker/ws/{job_id}"
    print(f"Connecting to {ws_url}...")
    try:
        async with websockets.connect(ws_url) as websocket:
            print("Connected.")
            while True:
                msg = await websocket.recv()
                data = json.loads(msg)
                
                if data["type"] == "progress":
                    print(f"Progress: {data['progress']}% | Visible: {data['visible_hens']} | Total: {data['total_hens']}")
                elif data["type"] == "completed":
                    print(f"\n--- TRACKING COMPLETED ---")
                    print(f"FINAL TOTAL HENS: {data['total_hens']}")
                    break
                elif data["type"] == "error":
                    print(f"\n--- TRACKING ERROR ---")
                    print(data["message"])
                    break
    except websockets.exceptions.ConnectionClosed:
        print("WebSocket closed.")

if __name__ == "__main__":
    job_id = test_upload()
    if job_id:
        asyncio.run(test_websocket(job_id))
