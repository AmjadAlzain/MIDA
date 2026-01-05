"""Quick script to start the MIDA server."""
import os
import sys

# Change to server directory and load .env file
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

# Set environment variables
os.environ["PYTHONPATH"] = os.path.dirname(os.path.abspath(__file__))
os.environ["MIDA_API_BASE_URL"] = "http://localhost:8000"

# Add the server directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    import uvicorn
    print("\n" + "=" * 60)
    print("MIDA Server Starting...")
    print("=" * 60)
    print("\n  Web UI:  http://localhost:8000")
    print("  API Docs: http://localhost:8000/docs")
    print("\n" + "=" * 60 + "\n")
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
