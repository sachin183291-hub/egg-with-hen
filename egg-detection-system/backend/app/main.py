# pyrefly: ignore [missing-import]
from fastapi import FastAPI 
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware
# pyrefly: ignore [missing-import]
from fastapi.staticfiles import StaticFiles
import os

from app.routes import detection

app = FastAPI(
    title="AI Egg Detection & Counting System",
    description="API for detecting and counting eggs in images.",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For production, replace with specific frontend origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure output directories exist using absolute paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")
os.makedirs(os.path.join(OUTPUTS_DIR, "annotated"), exist_ok=True)
os.makedirs(os.path.join(OUTPUTS_DIR, "reports"), exist_ok=True)

# Serve static files for annotated images and reports
app.mount("/static", StaticFiles(directory=OUTPUTS_DIR), name="static")

# Include routes
app.include_router(detection.router, prefix="/api", tags=["Detection"])

@app.on_event("startup")
def startup_event():
    from app.services.yolo_service import load_model
    print("Preloading YOLO model to reduce initial latency...")
    load_model()
    print("YOLO model preloaded successfully.")

@app.get("/api/health", tags=["Health"])
def health_check():
    return {"status": "ok", "message": "Backend is running smoothly."}

if __name__ == "__main__":
    # pyrefly: ignore [missing-import]
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
