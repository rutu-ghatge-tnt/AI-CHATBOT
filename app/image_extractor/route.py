# app/image_extractor/route.py

from fastapi import APIRouter, UploadFile, File, HTTPException
from .claude import extract_structured_info
from .google_vision import extract_text_from_image

router = APIRouter()

@router.post("/extract-from-image")
async def extract_from_image(image: UploadFile = File(...)):
    try:
        image_bytes = await image.read()
        ocr_text = await extract_text_from_image(image_bytes)  # now fixed
        structured_data = await extract_structured_info(ocr_text)

        return {
            "ocr_text": ocr_text,
            "structured_data": structured_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
