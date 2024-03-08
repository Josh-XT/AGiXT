import json
import requests
import asyncio
import requests


class NvidiaProvider:
    def __init__(
        self,
        API_KEY: str = "",
        API_URI: str = "https://api.nvcf.nvidia.com/v2/nvcf/pexec/functions/1361fa56-61d7-4a12-af32-69a3825746fa",
        FETCH_URL_FORMAT: str = "https://api.nvcf.nvidia.com/v2/nvcf/pexec/status/",
        MAX_TOKENS: int = 1024,
        AI_TEMPERATURE: float = 0.2,
        AI_TOP_P: float = 0.7,
        WAIT_BETWEEN_REQUESTS: int = 0,
        WAIT_AFTER_FAILURE: int = 3,
        **kwargs,
    ):
        self.requirements = ["requests"]
        self.API_URI = API_URI
        self.FETCH_URL_FORMAT = FETCH_URL_FORMAT
        self.MAX_TOKENS = MAX_TOKENS
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.AI_TOP_P = AI_TOP_P
        self.API_KEY = API_KEY
        self.WAIT_AFTER_FAILURE = WAIT_AFTER_FAILURE
        self.WAIT_BETWEEN_REQUESTS = WAIT_BETWEEN_REQUESTS
        self.FAILURES = []

    async def inference(self, prompt, tokens: int = 0):
        if int(self.WAIT_BETWEEN_REQUESTS) > 0:
            await asyncio.sleep(int(self.WAIT_BETWEEN_REQUESTS))

        # Adjusting max tokens based on the additional tokens parameter
        max_tokens = int(self.MAX_TOKENS) - tokens

        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.AI_TEMPERATURE,
            "top_p": self.AI_TOP_P,
            "max_tokens": max_tokens,
            "stream": False,
            "stop": None,
        }

        session = requests.Session()

        headers = {
            "Authorization": f"Bearer {self.API_KEY}",
            "Accept": "application/json",
        }

        response = session.post(self.API_URI, headers=headers, json=payload)
        response.raise_for_status()

        while response.status_code == 202:
            request_id = response.headers.get("NVCF-REQID")
            fetch_url = self.FETCH_URL_FORMAT + request_id
            response = session.get(fetch_url, headers=headers)

        response.raise_for_status()
        response_body = response.json()
        content_line = (
            response_body.get("choices", [{}])[0].get("message", {}).get("content")
        )
        if content_line:
            decoded_content = decode_json_line(content_line)
            return decoded_content
        else:
            raise ValueError("Content not found in the response")


def custom_decoder(obj):
    """
    Custom decoder to handle complex types and newline characters in JSON strings.
    """
    # Convert a custom type to a serializable format
    if "__custom_type__" in obj:
        return complex(obj["real"], obj["imag"])

    # Replace newline characters in string values
    if isinstance(obj, str):
        return obj.replace("\n", " ")

    return obj


def is_json_string(line):
    """
    Check if the line starts with a character that indicates a JSON object or array.
    """
    # Check if the line starts with a character that indicates a JSON object or array
    return line.strip() and line.strip()[0] in ("{", "[", '"')


def escape_newlines(line):
    """
    Escape newline characters in the line.
    """
    ## Replace newline characters with a space temporarily until different function is added to fix to address this problem first.
    return line.replace("\n", " ")


def decode_json_string(json_str):
    """
    Decode a JSON string, handling regular strings and newline characters.
    """
    # Escape newline characters in the string
    escaped_str = escape_newlines(json_str)

    # Check if the string is a JSON string
    if not is_json_string(escaped_str):
        # If it's not a JSON string, return it as is
        return escaped_str.strip()

    try:
        # Try loading the string as JSON with custom decoding
        decoded_str = json.loads(
            escaped_str,
            object_hook=custom_decoder,
            object_pairs_hook=lambda pairs: {
                k: v for k, v in pairs if isinstance(k, str)
            },
        )
        return decoded_str
    except json.JSONDecodeError as e:
        # If the string is not a valid JSON string, return the original string
        print("Error decoding JSON string:", e)
        return escaped_str.strip()


def decode_json_line(line):
    """
    Decode a JSON line, handling regular strings, newline characters, and complex types.
    """
    # Decode JSON string
    decoded_str = decode_json_string(line)

    # If it's a JSON string, parse it
    if isinstance(decoded_str, str) and is_json_string(decoded_str):
        return json.loads(decoded_str)
    else:
        # If not, apply custom processing to unescape underscores
        return unescape_underscores(decoded_str)


def unescape_underscores(text):
    """
    Unescape underscores in the text.
    """
    return text.replace(r"\_", "_")
