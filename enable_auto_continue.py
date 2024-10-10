### python enable_auto_continue.py "http://localhost:7437" "Your agent" "Your API key"
import argparse
import requests

def enable_auto_continue(base_uri: str, agent_name: str, api_key: str):
    url = f"{base_uri}/api/agent/{agent_name}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "agent_name": agent_name,
        "settings": {
            "auto_continue": True
        }
    }
    response = requests.put(url, json=data, headers=headers)
    if response.status_code == 200:
        print("Auto-continue enabled successfully.")
    else:
        print(f"Failed to enable auto-continue: {response.status_code} - {response.text}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enable auto-continue for an AGiXT agent.")
    parser.add_argument("base_uri", type=str, help="The base URI of the AGiXT server.")
    parser.add_argument("agent_name", type=str, help="The name of the agent to enable auto-continue.")
    parser.add_argument("api_key", type=str, help="The API key for authentication.")
    args = parser.parse_args()
    enable_auto_continue(args.base_uri, args.agent_name, args.api_key)

