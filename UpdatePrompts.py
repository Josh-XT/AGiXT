from agixt.Globals import getenv
from agixtsdk import AGiXTSDK
import os


def update_prompts_in_database(failures=0):
    try:
        os.system("git pull")
    except:
        pass
    agixt = AGiXTSDK(base_uri=getenv("AGIXT_SERVER"), api_key=getenv("AGIXT_API_KEY"))
    # Get list of prompts from prompts/Default folder
    prompts = []
    for root, dirs, files in os.walk("agixt/prompts/Default"):
        for file in files:
            prompts.append(file.replace(".txt", ""))
    print(prompts)
    update_failed = False
    # For each prompt in the list, compare to the prompt from the API
    for prompt in prompts:
        agixt_prompt = agixt.get_prompt(prompt_name=prompt, prompt_category="Default")
        with open(f"prompts/Default/{prompt}.txt", "r") as file:
            try:
                content = file.read()
            except:
                content = ""
        if agixt_prompt != content:
            if content != "":
                print(f"Updating prompt: {prompt}")
                try:
                    agixt.update_prompt(
                        prompt_name=prompt, prompt=content, prompt_category="Default"
                    )
                except:
                    print(f"Failed to update prompt: {prompt}")
                    update_failed = True
    if update_failed:
        failures += 1
        if failures < 5:
            update_prompts_in_database(failures=failures)
    return "Prompts updated"
