import os

from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://analyst-assessment-production.up.railway.app"
API_BASE_URL = f"{BASE_URL}/api/v1"

CRM_API_TOKEN = os.getenv("CRM_API_TOKEN")

if not CRM_API_TOKEN:
    raise RuntimeError(
        "CRM_API_TOKEN is missing. Add it to your local .env file."
    )

HEADERS = {
    "Authorization": f"Bearer {CRM_API_TOKEN}",
    "Content-Type": "application/json",
}