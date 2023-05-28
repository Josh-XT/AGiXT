import gpt4free
import time
import logging
import importlib


class Gpt4freeProvider:
    def __init__(
        self,
        AI_MODEL: str = "gpt-3.5-turbo",
        AI_TEMPERATURE: float = 0.7,
        MAX_TOKENS: int = 4000,
        **kwargs,
    ):
        self.requirements = ["gpt4free"]
        self.AI_MODEL = AI_MODEL
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.MAX_TOKENS = MAX_TOKENS
        self.FAILED_PROVIDERS = []
        self.providers = ["DeepAI", "You", "UseLess", "ForeFront", "Theb"]
        self.account_tokens = {}

    def instruct(self, prompt, tokens: int = 0):
        final_response = None
        while final_response is None:
            for provider in self.providers:
                try:
                    if provider not in self.FAILED_PROVIDERS:
                        logging.info(f"[GPT4Free] Using: {provider}")
                        if provider not in self.account_tokens:
                            try:
                                if provider == "Poe":
                                    module_name = "quora"
                                elif provider == "UseLess":
                                    module_name = "usesless"
                                else:
                                    module_name = provider.lower()
                                module = importlib.import_module(
                                    "gpt4free.%s" % module_name
                                )
                                if module and hasattr(module, "Account"):
                                    logging.info(f"Create account for: {provider}")
                                    self.account_tokens[
                                        provider
                                    ] = module.Account.create()
                            except ModuleNotFoundError:
                                self.account_tokens[provider] = None
                        args = {}
                        if provider in self.account_tokens:
                            if provider == "ForeFront":
                                args["account_data"] = self.account_tokens[provider]
                            elif provider == "UseLess":
                                args["token"] = self.account_tokens[provider]
                            elif provider == "Poe":
                                args["token"] = self.account_tokens[provider]
                                args["model"] = "GPT-4"

                        response = gpt4free.Completion.create(
                            getattr(gpt4free.Provider, provider), prompt=prompt, **args
                        )
                        if response:
                            if provider == "UseLess":
                                if "text" in response:
                                    response = response["text"]
                                if (
                                    "status" in response
                                    and response["status"] == "Fail"
                                ):
                                    self.FAILED_PROVIDERS.append(provider)
                                    logging.info(
                                        f"Failed to use {provider}: {response}"
                                    )
                                    response = None
                            if (
                                response
                                == "Unable to fetch the response, Please try again."
                            ):
                                self.FAILED_PROVIDERS.append(provider)
                                logging.info(f"Failed to use {provider}: {response}")
                                response = None
                            if final_response == None:
                                final_response = response
                    if final_response:
                        if len(final_response) > 1:
                            return final_response
                except Exception as e:
                    logging.info(f"Failed to use {provider}: {e}")
                    self.FAILED_PROVIDERS.append(provider)
                    final_response = None

            if len(self.FAILED_PROVIDERS) == len(self.providers):
                self.FAILED_PROVIDERS = []
                logging.info(
                    "All providers failed, sleeping for 10 seconds before trying again..."
                )
                time.sleep(10)
