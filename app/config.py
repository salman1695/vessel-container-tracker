import os
from dotenv import load_dotenv

load_dotenv()

SINAY_API_KEY = os.getenv("SINAY_API_KEY") or os.getenv("SAFECUBE_API_KEY")
BASE_URL = "https://api.sinay.ai"
ENDPOINT = "/container-tracking/api/v2/shipment"
CACHE_TTL_HOURS = 6  # 6 ghante tak dubara API credit kharch nahi hoga