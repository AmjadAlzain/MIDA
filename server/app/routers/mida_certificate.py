from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.certificate_parser import parse_mida_certificate, parse_mida_certificate_debug
import io

router = APIRouter()


def get_local_pdf_page_count(pdf_bytes: bytes) -> int:
    """Get page count from PDF bytes using pypdf."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        return len(reader.pages)
    except Exception:
        return -1  # Indicate failure


@router.post("/parse")
async def certificate_parse(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF")
    pdf_bytes = await file.read()
    return parse_mida_certificate(pdf_bytes)

@router.post("/parse-debug")
async def certificate_parse_debug(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF")
    pdf_bytes = await file.read()
    
    # Compute local PDF info
    pdf_page_count_local = get_local_pdf_page_count(pdf_bytes)
    input_pdf_size_bytes = len(pdf_bytes)
    
    # Pass to parser with extra info
    result = parse_mida_certificate_debug(pdf_bytes)
    
    # Add local PDF diagnostics to debug
    result["debug"]["pdf_page_count_local"] = pdf_page_count_local
    result["debug"]["input_pdf_size_bytes"] = input_pdf_size_bytes
    
    return result
