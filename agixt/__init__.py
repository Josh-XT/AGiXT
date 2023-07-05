from agixtsdk import AGiXTSDK
import os
from dotenv import load_dotenv

load_dotenv()
agixt_api_key = os.getenv("AGIXT_API_KEY")
base_uri = "http://localhost:7437"
ApiClient = AGiXTSDK(base_uri=base_uri, api_key=agixt_api_key)
