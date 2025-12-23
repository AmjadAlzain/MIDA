from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from app.routers import mida_certificate

load_dotenv()

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(mida_certificate.router, prefix="/api/mida/certificate", tags=["mida"])

@app.get("/")
async def root():
    return {"message": "MIDA OCR API"}
