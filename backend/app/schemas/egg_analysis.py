"""
Pydantic schemas for egg & tray analysis (OpenAI Vision endpoint).
"""
from typing import Literal, Optional
from pydantic import BaseModel, Field


class TrayTypes(BaseModel):
    green_plastic: int = Field(default=0, ge=0, description="Number of green plastic egg trays")
    paper_cardboard: int = Field(default=0, ge=0, description="Number of paper/cardboard egg trays")
    other: int = Field(default=0, ge=0, description="Number of other-type egg trays")
    unknown: int = Field(default=0, ge=0, description="Trays whose material/type could not be determined")


class EggAnalysisResponse(BaseModel):
    success: bool = True
    egg_count: int = Field(default=0, ge=0, description="Number of individual visible eggs")
    tray_count: int = Field(default=0, ge=0, description="Number of physical egg trays")
    hen_count: int = Field(default=0, ge=0, description="Number of hens")
    tray_types: TrayTypes = Field(default_factory=TrayTypes)
    confidence: Literal["high", "medium", "low"] = Field(
        default="medium",
        description=(
            "high = clear image, all objects countable; "
            "medium = some partial occlusion; "
            "low = blurry/heavily occluded"
        ),
    )
    image_quality: Literal["good", "fair", "poor"] = Field(
        default="fair",
        description="Overall visual quality of the uploaded image",
    )
    notes: str = Field(default="", description="Brief explanation of findings or uncertainty")


class ChatAnalyzeResponse(BaseModel):
    reply: str = Field(description="AI assistant's natural-language answer")
    analysis: Optional[EggAnalysisResponse] = Field(
        default=None,
        description="Structured analysis result if an image was provided",
    )
