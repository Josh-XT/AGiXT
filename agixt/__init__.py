from agixtsdk import AGiXTSDK
import os
from dotenv import load_dotenv

load_dotenv()
ApiClient = AGiXTSDK(
    base_uri="http://localhost:7437", api_key=os.getenv("AGIXT_API_KEY")
)
