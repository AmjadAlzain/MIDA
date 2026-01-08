"""Test the classify endpoint to see what UOM values are returned."""
import sys
sys.path.insert(0, '.')

import requests

# Test with your local server
BASE_URL = "http://localhost:8000"

# Let's check if the server is running
try:
    response = requests.get(f"{BASE_URL}/api/health")
    print(f"Server health: {response.status_code}")
except Exception as e:
    print(f"Server not reachable: {e}")
    sys.exit(1)

# Check if we can see any items from a previous classify call
print("\nTo test the UOM lookup, you can:")
print("1. Upload an invoice file through the UI")
print("2. Check the browser console/network tab to see the API response")
print("3. Look for the 'uom' field in each item")
