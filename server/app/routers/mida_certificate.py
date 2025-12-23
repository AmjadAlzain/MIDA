from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.certificate_parser import parse_mida_certificate, parse_mida_certificate_debug

router = APIRouter()

@router.post("/certificate/parse")
async def certificate_parse(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF")
    pdf_bytes = await file.read()
    return parse_mida_certificate(pdf_bytes)

@router.post("/certificate/parse-debug")
async def certificate_parse_debug(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF")
    pdf_bytes = await file.read()
    return parse_mida_certificate_debug(pdf_bytes)
