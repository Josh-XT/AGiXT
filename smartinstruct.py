import requests
import argparse


if __name__ == "__main__":
    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", type=str, default="Write a tweet about AI.")
    parser.add_argument("--agent_name", type=str, default="huggingchat")
    parser.add_argument("--shots", type=int, default=3)
    parser.add_argument("--base_uri", type=str, default="http://localhost:7437")
    args = parser.parse_args()

    # SMART Instruct the agent
    response = requests.post(
        f"{args.base_uri}/api/agent/{args.agent_name}/smartinstruct/{args.shots}",
        json={"prompt": args.task},
    )
    data = response.json()
    print(data)
