# pyrefly: ignore [missing-import]
from fastapi import APIRouter, UploadFile, File, Form, HTTPException 
# pyrefly: ignore [missing-import]
from fastapi.responses import JSONResponse 
import os
import time
from typing import Optional

from app.services.yolo_service import detect_eggs

router = APIRouter()

@router.post("/detect-eggs")
async def detect_eggs_endpoint(
    image: UploadFile = File(...),
    confidence_threshold: float = Form(0.5)
):
    """
    Endpoint to process an uploaded image and detect eggs.
    """
    if not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File provided is not an image.")

    try:
        # Read image content
        contents = await image.read()
        
        # Process the image directly without saving to disk
        from app.services.yolo_service import detect_trays
        result = detect_trays(contents, confidence_threshold)
        
        if result is None:
            raise HTTPException(status_code=500, detail="Failed to process image.")
            
        return JSONResponse(content=result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
