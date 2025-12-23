import os
from dotenv import load_dotenv

def _load_env():
    # loads server/.env when running from server/
    load_dotenv()

def analyze_prebuilt_layout(pdf_bytes: bytes):
    """
    Returns an AnalyzeResult-like object with:
      - .content (full extracted text)
      - .tables (list of tables with cells)
    Works with either:
      - azure-ai-documentintelligence (new)
      - azure-ai-formrecognizer (fallback)
    """
    _load_env()
    endpoint = os.getenv("AZURE_DI_ENDPOINT")
    key = os.getenv("AZURE_DI_KEY")
    if not endpoint or not key:
        raise RuntimeError("Missing AZURE_DI_ENDPOINT or AZURE_DI_KEY in environment")

    # Try NEW SDK first
    try:
        from azure.core.credentials import AzureKeyCredential
        from azure.ai.documentintelligence import DocumentIntelligenceClient

        client = DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(key))
        poller = client.begin_analyze_document(model_id="prebuilt-layout", body=pdf_bytes)
        return poller.result()
    except Exception:
        # Fallback to older/widely used SDK
        from azure.core.credentials import AzureKeyCredential
        from azure.ai.formrecognizer import DocumentAnalysisClient

        client = DocumentAnalysisClient(endpoint=endpoint, credential=AzureKeyCredential(key))
        poller = client.begin_analyze_document(model_id="prebuilt-layout", document=pdf_bytes)
        return poller.result()
