import requests
import argparse


if __name__ == "__main__":
    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--task",
        type=str,
        default="What are the latest breakthroughs and news in AI today?",
    )
    parser.add_argument("--agent_name", type=str, default="huggingchat")
    parser.add_argument("--shots", type=int, default=3)
    parser.add_argument("--base_uri", type=str, default="http://localhost:7437")
    args = parser.parse_args()

    # SmarterChat with the agent will enable it to browse the web for answers to your prompt.
    response = requests.post(
        f"{args.base_uri}/api/agent/{args.agent_name}/smarterchat/{args.shots}",
        json={"prompt": args.task},
    )
    data = response.json()
    print(data)
