import os
from dotenv import load_dotenv
from agixtsdk import AGiXTSDK

load_dotenv()
base_uri = os.getenv("BASE_URI", "http://localhost:7437")
ApiClient = AGiXTSDK(base_uri=base_uri)
