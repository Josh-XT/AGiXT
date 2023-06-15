import gpt4free
import time
import logging
import importlib
import sys


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
        self.providers = [
            "DeepAI",
            "You",
            "UseLess",
            "ForeFront",
            "Theb",
            "AiColors",
        ]
        self.account_tokens = {}

    def create_account(self, provider, module):
        try:
            # the following call will not terminate the program even if it calls quit()
            return module.Account.create()
        except SystemExit:
            logging.error(f"Account creation for {provider} called quit(), ignoring")
            return None
        except Exception as e:
            # handle other exceptions here
            logging.error(f"Failed to create account for {provider}: {e}")
            return None

    async def provider_failure(self, provider):
        if provider not in self.FAILED_PROVIDERS:
            self.FAILED_PROVIDERS.append(provider)
            logging.info(f"[GPT4Free] Failed provider: {provider}")
            if len(self.FAILED_PROVIDERS) == len(self.providers):
                self.FAILED_PROVIDERS = []
                logging.info(
                    "All providers failed, sleeping for 10 seconds before trying again..."
                )
                time.sleep(10)

    async def instruct(self, prompt, tokens: int = 0):
        while True:
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
                                    self.account_tokens[provider] = self.create_account(
                                        provider, module
                                    )
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
                                    response = None
                            if (
                                response
                                == "Unable to fetch the response, Please try again."
                            ):
                                response = None
                        if response and len(response) > 1:
                            return response
                        else:
                            await self.provider_failure(provider)
                except Exception as e:
                    logging.info(f"[GPT4Free] Exception: {e}")
                    await self.provider_failure(provider)
