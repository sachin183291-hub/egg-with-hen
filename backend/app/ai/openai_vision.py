"""
OpenAI Vision Detector — egg & tray counting via GPT-4o.

This is the initial production implementation using the OpenAI Responses API.
It implements the ImageDetector interface so it can be swapped for a custom
YOLO model later without changing any frontend or API code.
"""
import base64
import json
import logging
from typing import Any, Optional

from app.ai.detector_interface import ImageDetector

logger = logging.getLogger(__name__)

# ─── System instruction sent to OpenAI / Gemini with every image request ───────
SYSTEM_INSTRUCTION = (
    "You are an expert visual inspection and counting assistant specialized in poultry farming: eggs, egg trays, and hens/chickens.\n\n"
    "Analyze the uploaded image carefully.\n\n"
    "CRITICAL DETECTION CAPABILITY FOR REAL & DRAWN / TEST SHAPES:\n"
    "- You MUST detect and accurately count BOTH real physical photographs AND all hand-drawn, sketched, doodled, whiteboard, digital, or synthetic test shapes.\n"
    "- Users frequently test this system by drawing mock shapes on paper, whiteboards, digital paint apps, or test sheets. You MUST recognize and count these test drawings with high precision.\n\n"
    "OBJECT DEFINITIONS & COUNTING RULES:\n"
    "1. EGGS (egg_count):\n"
    "   - Real physical eggs (brown, white, speckled, clean, unwashed).\n"
    "   - Hand-drawn shapes: Any drawn oval, circle, ellipse, egg doodle, sketch, outline, filled shape, or egg symbol on paper, whiteboard, or digital canvas.\n"
    "   - Count each distinct egg or drawn oval/circle one-by-one = exactly 1 egg.\n"
    "   - If multiple drawn eggs touch or are clustered, separate and count each individual egg.\n\n"
    "2. EGG TRAYS (tray_count):\n"
    "   - Real physical egg trays: plastic trays (green, blue, yellow, etc.), paper/cardboard pulp flats, egg cartons, and crates.\n"
    "   - Hand-drawn shapes: Any drawn tray grid, matrix of egg cells (e.g. 5x6, 6x5, 2x6 grids, rectangular boxes with egg slots/cells, waffle patterns), carton sketches, crate outlines, or tray diagrams.\n"
    "   - Stacked tray sketches: When trays or horizontal tray layers are drawn stacked on top of each other, count each individual drawn layer as 1 tray.\n"
    "   - CRITICAL RED LINE RULE: If you see red horizontal lines drawn over the trays in the image, count these red lines! The total number of red lines is exactly equal to the tray_count. Prioritize the red line count for trays if they are present.\n"
    "   - Each complete drawn tray structure, grid, or layer (or red line) = exactly 1 tray.\n"
    "   - Categorize tray types: green_plastic (if green/plastic style), paper_cardboard (if cardboard/pulp style), other (other colors/materials), unknown (unspecified sketches).\n\n"
    "3. HENS / CHICKENS (hen_count):\n"
    "   - Real live poultry: hens, chickens, roosters, broilers, layers.\n"
    "   - Hand-drawn shapes: Any drawn chicken, hen, rooster, stick-figure bird, chicken doodle, cartoon chicken, sketch, line art, or illustration with beak, comb, feathers, or legs.\n"
    "   - Each distinct drawn chicken/hen figure = exactly 1 hen.\n\n"
    "You MUST respond with a valid JSON object matching exactly this schema:\n"
    "{\n"
    '  "success": true,\n'
    '  "egg_count": <integer>,\n'
    '  "tray_count": <integer>,\n'
    '  "hen_count": <integer>,\n'
    '  "tray_types": {\n'
    '    "green_plastic": <integer>,\n'
    '    "paper_cardboard": <integer>,\n'
    '    "other": <integer>,\n'
    '    "unknown": <integer>\n'
    '  },\n'
    '  "confidence": "<high|medium|low>",\n'
    '  "image_quality": "<good|fair|poor>",\n'
    '  "notes": "<brief explanation describing detected objects, specifying whether real objects or hand-drawn/synthetic test shapes were counted. IMPORTANT: This MUST be in the Tamil language (Tamil script)>"\n'
    "}\n\n"
    "confidence rules:\n"
    "  high   = image or drawing is clear and objects are distinctly countable\n"
    "  medium = some objects are partially hidden, ambiguous, or overlapping\n"
    "  low    = image is heavily obscured or impossible to count reliably\n\n"
    "image_quality rules:\n"
    "  good = clear, well-lit photograph or sharp, clean drawing/diagram\n"
    "  fair = acceptable photograph or rough hand-drawn sketch\n"
    "  poor = blurry, dark, or severely occluded\n\n"
    "Return ONLY the JSON object. No markdown, no code fences, no extra text. IMPORTANT: The 'notes' field MUST be in Tamil language."
)

# ─── Chat instruction (same core rules, conversational tone) ──────────────────
CHAT_SYSTEM_INSTRUCTION = (
    "You are an expert visual inspection assistant specialized in poultry egg trays, eggs, and hens/chickens. "
    "You help users count and identify eggs, egg trays, and hens in images they upload.\n\n"
    "When the user provides an image, analyze it carefully:\n"
    "- Count individual eggs, egg trays, and hens as SEPARATE items\n"
    "- Recognize BOTH real physical photographs AND hand-drawn/synthetic/graphic representations of eggs (e.g. ovals, circles), egg trays (e.g. grid diagrams, cartons, stacked layers), and hens (e.g. chicken doodles, cartoons, stick figures)\n"
    "- For stacked trays: each physical or drawn horizontal layer = 1 tray\n"
    "- CRITICAL RED LINE RULE: If you see red horizontal lines drawn over the trays, count those red lines. The total number of red lines is the tray count.\n"
    "- Recognize tray types: green plastic, paper/cardboard, other colors, etc.\n"
    "- Answer user questions clearly and provide accurate counts for eggs, trays, and hens.\n\n"
    "Answer the user's question directly and concisely.\n"
    "IMPORTANT: You MUST reply entirely in the Tamil language (using Tamil script)."
)


class OpenAIVisionDetector(ImageDetector):
    """
    Egg & tray counter using OpenAI GPT-4o Vision (Responses API).
    Implements the ImageDetector interface for drop-in replacement later.
    """

    def __init__(self) -> None:
        from app.config import settings
        from openai import OpenAI

        if not settings.OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. "
                "Add it to backend/.env: OPENAI_API_KEY=sk-..."
            )

        self._client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self._model = settings.OPENAI_MODEL or "gpt-4o"

    def analyze(self, image_bytes: bytes, mime_type: str = "image/jpeg", target: str = "trays") -> dict:
        """
        Send the image to OpenAI GPT-4o and return a structured count result.

        Args:
            image_bytes: Raw image bytes (jpg/jpeg/png/webp).
            mime_type: MIME type of the image.
            target: The detection target ('eggs', 'hens', 'trays').

        Returns:
            Validated dict with egg_count, tray_count, hen_count, tray_types, confidence,
            image_quality, and notes.
        """
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        image_url = f"data:{mime_type};base64,{b64}"
        
        target_str = "eggs, egg trays, and hens"
        if target == "eggs":
            target_str = "ONLY eggs (count all real physical eggs AND all hand-drawn ovals/circles/egg sketches accurately into egg_count)"
        elif target == "hens":
            target_str = "ONLY hens/chickens (count all real live hens/chickens AND all hand-drawn chicken doodles/cartoons/sketches accurately into hen_count)"
        elif target == "trays":
            target_str = "ONLY egg trays (count all real egg trays, stack layers, AND all hand-drawn tray grids/matrices/cartons accurately into tray_count)"

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_INSTRUCTION
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": image_url, "detail": "high"},
                            },
                            {
                                "type": "text",
                                "text": (
                                    "Please analyze this image carefully.\n"
                                    f"Target: {target_str}.\n"
                                    "Count both real physical objects and any hand-drawn/synthetic test shapes accurately.\n"
                                    "Return your answer as the JSON object described in the instructions with exact integer values for egg_count, tray_count, and hen_count."
                                ),
                            },
                        ],
                    }
                ],
                temperature=0,
            )

            raw_text = response.choices[0].message.content.strip()
            logger.debug("OpenAI raw response: %s", raw_text[:500])

            return self._parse_and_validate(raw_text)

        except Exception as exc:
            logger.error("OpenAI Vision API error: %s", exc, exc_info=True)
            raise

    def chat_analyze(self, message: str, image_bytes: Optional[bytes], mime_type: str = "image/jpeg") -> dict:
        """
        Answer a user question about an image (conversational mode).

        Args:
            message: User's text question.
            image_bytes: Optional raw image bytes.
            mime_type: MIME type if image is provided.

        Returns:
            {
                "reply": str,             # plain-text answer
                "analysis": dict | None   # structured result if image was provided
            }
        """
        content: list[dict[str, Any]] = []

        if image_bytes:
            b64 = base64.b64encode(image_bytes).decode("utf-8")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{b64}", "detail": "high"},
            })

        content.append({"type": "text", "text": message})

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": CHAT_SYSTEM_INSTRUCTION},
                    {"role": "user", "content": content}
                ],
                temperature=0.3,
            )

            reply_text = response.choices[0].message.content.strip()

            # If image was provided, also run a full structured analysis in parallel
            analysis = None
            if image_bytes:
                try:
                    analysis = self.analyze(image_bytes, mime_type)
                except Exception as e:
                    logger.warning("Structured analysis failed during chat: %s", e)

            return {"reply": reply_text, "analysis": analysis}

        except Exception as exc:
            logger.error("OpenAI chat analyze error: %s", exc, exc_info=True)
            raise

    def analyze_dual(self, top_image_bytes: bytes, side_image_bytes: bytes, mime_type_top: str = "image/jpeg", mime_type_side: str = "image/jpeg", target: str = "trays") -> dict:
        """
        Analyze dual images (top view and side view) to count trays.
        """
        b64_top = base64.b64encode(top_image_bytes).decode("utf-8")
        top_image_url = f"data:{mime_type_top};base64,{b64_top}"
        
        b64_side = base64.b64encode(side_image_bytes).decode("utf-8")
        side_image_url = f"data:{mime_type_side};base64,{b64_side}"

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_INSTRUCTION
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "You are provided with TWO images. The FIRST image is the TOP VIEW. The SECOND image is the SIDE VIEW.\n"
                                    "To correctly count the egg trays, STRICTLY follow these rules:\n"
                                    "1. Look at the SIDE VIEW (second image) and count how many trays are placed in a single vertical stack. Usually, there will be 1 tray visible on top and 19 trays underneath it, making exactly 20 trays per stack.\n"
                                    "2. Look at the TOP VIEW (first image) and count how many individual stacks of trays are visible.\n"
                                    "3. Multiply the number of stacks from the Top View by the number of trays in a single stack from the Side View (e.g. 20) to get the total `tray_count`.\n"
                                    "4. Calculate the total `egg_count` as EXACTLY: `tray_count` * 30 (since each tray holds 30 eggs).\n"
                                    "Count both real physical objects and any hand-drawn/synthetic test shapes accurately. DO NOT guess the tray count. Calculate carefully.\n"
                                    "Return your answer as the JSON object described in the instructions with exact integer values for egg_count, tray_count, and hen_count."
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": top_image_url, "detail": "high"},
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": side_image_url, "detail": "high"},
                            },
                        ],
                    }
                ],
                temperature=0,
            )

            raw_text = response.choices[0].message.content.strip()
            logger.debug("OpenAI dual analyze raw response: %s", raw_text[:500])

            return self._parse_and_validate(raw_text)

        except Exception as exc:
            logger.error("OpenAI Vision dual API error: %s", exc, exc_info=True)
            raise

    # ─── Internal helpers ─────────────────────────────────────────────────────

    def _parse_and_validate(self, raw_text: str) -> dict:
        """Parse OpenAI response text and validate/normalise it."""

        # Strip markdown code fences if the model added them despite instructions
        cleaned = raw_text
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(
                ln for ln in lines
                if not ln.strip().startswith("```")
            ).strip()

        try:
            data: dict = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse OpenAI JSON: %s\nRaw text: %s", exc, raw_text[:300])
            raise ValueError(f"OpenAI returned invalid JSON: {exc}") from exc

        # Normalise and fill in defaults
        result = {
            "success": bool(data.get("success", True)),
            "egg_count": int(data.get("egg_count", 0)),
            "tray_count": int(data.get("tray_count", 0)),
            "hen_count": int(data.get("hen_count", 0)),
            "tray_types": {
                "green_plastic": int((data.get("tray_types") or {}).get("green_plastic", 0)),
                "paper_cardboard": int((data.get("tray_types") or {}).get("paper_cardboard", 0)),
                "other": int((data.get("tray_types") or {}).get("other", 0)),
                "unknown": int((data.get("tray_types") or {}).get("unknown", 0)),
            },
            "confidence": _normalise_enum(
                data.get("confidence", "medium"), ["high", "medium", "low"], "medium"
            ),
            "image_quality": _normalise_enum(
                data.get("image_quality", "fair"), ["good", "fair", "poor"], "fair"
            ),
            "notes": str(data.get("notes", "")),
        }

        # Sanity-check tray_types total vs tray_count
        types_total = sum(result["tray_types"].values())
        if types_total != result["tray_count"] and types_total > 0:
            # Redistribute into unknown to keep totals consistent
            result["tray_types"]["unknown"] += result["tray_count"] - types_total

        return result


def _normalise_enum(value: Any, choices: list[str], default: str) -> str:
    if isinstance(value, str) and value.lower() in choices:
        return value.lower()
    return default
