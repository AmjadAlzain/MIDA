from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)


def analyze_prebuilt_layout(pdf_bytes: bytes):
    """
    Returns an AnalyzeResult-like object with:
      - .content (full extracted text)
      - .tables (list of tables with cells)
    Works with either:
      - azure-ai-documentintelligence (new)
      - azure-ai-formrecognizer (fallback)
    """
    settings = get_settings()
    endpoint = settings.azure_di_endpoint
    key = settings.azure_di_key
    
    if not endpoint or not key:
        raise RuntimeError("Missing AZURE_DI_ENDPOINT or AZURE_DI_KEY in environment")

    logger.debug("Analyzing document with Azure Document Intelligence")

    # Try NEW SDK first
    try:
        from azure.core.credentials import AzureKeyCredential
        from azure.ai.documentintelligence import DocumentIntelligenceClient

        client = DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(key))
        poller = client.begin_analyze_document(model_id="prebuilt-layout", body=pdf_bytes)
        result = poller.result()
        logger.info("Document analysis completed successfully (new SDK)")
        return result
    except Exception as e:
        logger.debug(f"New SDK failed, falling back to older SDK: {e}")
        # Fallback to older/widely used SDK
        from azure.core.credentials import AzureKeyCredential
        from azure.ai.formrecognizer import DocumentAnalysisClient

        client = DocumentAnalysisClient(endpoint=endpoint, credential=AzureKeyCredential(key))
        poller = client.begin_analyze_document(model_id="prebuilt-layout", document=pdf_bytes)
        result = poller.result()
        logger.info("Document analysis completed successfully (fallback SDK)")
        return result
