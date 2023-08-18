import os
from agixtsdk import AGiXTSDK
from dotenv import load_dotenv

load_dotenv()
AGIXT_API_KEY = os.getenv("AGIXT_API_KEY", None)
DB_CONNECTED = True if os.getenv("DB_CONNECTED", "false").lower() == "true" else False
ApiClient = AGiXTSDK(base_uri="http://localhost:7437", api_key=AGIXT_API_KEY)
