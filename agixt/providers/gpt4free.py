import logging
import time

from dataclasses import dataclass

from g4f.Provider import (
    BaseProvider,
    GetGpt,
    H2o,
    Liaobots,
    Vercel,
    Equing,
    Aichat,
    Ails,
    Yqcloud,
    Acytoo,
    Opchatgpts,
    Wewordle,
    DeepAi,
    ChatgptLogin,
    EasyChat,
    You,
    AiService,
    AItianhu,
    Bing,
    Lockchat,
    Theb,
    FastGpt,
    Forefront,
    ChatgptAi,
)


# Hard coding all of this to not import Bard because it is causing issues on import.
@dataclass
class Model:
    name: str
    base_provider: str
    best_provider: type[BaseProvider]


# GPT-3.5 / GPT-4
gpt_35_turbo = Model(
    name="gpt-3.5-turbo",
    base_provider="openai",
    best_provider=GetGpt,
)

gpt_4 = Model(
    name="gpt-4",
    base_provider="openai",
    best_provider=Liaobots,
)

# H2o
falcon_7b = Model(
    name="h2oai/h2ogpt-gm-oasst1-en-2048-falcon-7b-v3",
    base_provider="huggingface",
    best_provider=H2o,
)

falcon_40b = Model(
    name="h2oai/h2ogpt-gm-oasst1-en-2048-falcon-40b-v1",
    base_provider="huggingface",
    best_provider=H2o,
)

llama_13b = Model(
    name="h2oai/h2ogpt-gm-oasst1-en-2048-open-llama-13b",
    base_provider="huggingface",
    best_provider=H2o,
)

# Vercel
claude_instant_v1 = Model(
    name="anthropic:claude-instant-v1",
    base_provider="anthropic",
    best_provider=Vercel,
)

claude_v1 = Model(
    name="anthropic:claude-v1",
    base_provider="anthropic",
    best_provider=Vercel,
)

claude_v2 = Model(
    name="anthropic:claude-v2",
    base_provider="anthropic",
    best_provider=Vercel,
)

command_light_nightly = Model(
    name="cohere:command-light-nightly",
    base_provider="cohere",
    best_provider=Vercel,
)

command_nightly = Model(
    name="cohere:command-nightly",
    base_provider="cohere",
    best_provider=Vercel,
)

gpt_neox_20b = Model(
    name="huggingface:EleutherAI/gpt-neox-20b",
    base_provider="huggingface",
    best_provider=Vercel,
)

oasst_sft_1_pythia_12b = Model(
    name="huggingface:OpenAssistant/oasst-sft-1-pythia-12b",
    base_provider="huggingface",
    best_provider=Vercel,
)

oasst_sft_4_pythia_12b_epoch_35 = Model(
    name="huggingface:OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5",
    base_provider="huggingface",
    best_provider=Vercel,
)

santacoder = Model(
    name="huggingface:bigcode/santacoder",
    base_provider="huggingface",
    best_provider=Vercel,
)

bloom = Model(
    name="huggingface:bigscience/bloom",
    base_provider="huggingface",
    best_provider=Vercel,
)

flan_t5_xxl = Model(
    name="huggingface:google/flan-t5-xxl",
    base_provider="huggingface",
    best_provider=Vercel,
)

code_davinci_002 = Model(
    name="openai:code-davinci-002",
    base_provider="openai",
    best_provider=Vercel,
)

gpt_35_turbo_16k = Model(
    name="openai:gpt-3.5-turbo-16k",
    base_provider="openai",
    best_provider=Vercel,
)

gpt_35_turbo_16k_0613 = Model(
    name="openai:gpt-3.5-turbo-16k-0613",
    base_provider="openai",
    best_provider=Equing,
)

gpt_4_0613 = Model(
    name="openai:gpt-4-0613",
    base_provider="openai",
    best_provider=Vercel,
)

text_ada_001 = Model(
    name="openai:text-ada-001",
    base_provider="openai",
    best_provider=Vercel,
)

text_babbage_001 = Model(
    name="openai:text-babbage-001",
    base_provider="openai",
    best_provider=Vercel,
)

text_curie_001 = Model(
    name="openai:text-curie-001",
    base_provider="openai",
    best_provider=Vercel,
)

text_davinci_002 = Model(
    name="openai:text-davinci-002",
    base_provider="openai",
    best_provider=Vercel,
)

text_davinci_003 = Model(
    name="openai:text-davinci-003",
    base_provider="openai",
    best_provider=Vercel,
)

llama13b_v2_chat = Model(
    name="replicate:a16z-infra/llama13b-v2-chat",
    base_provider="replicate",
    best_provider=Vercel,
)

llama7b_v2_chat = Model(
    name="replicate:a16z-infra/llama7b-v2-chat",
    base_provider="replicate",
    best_provider=Vercel,
)


class ModelUtils:
    convert: dict[str, Model] = {
        # GPT-3.5 / GPT-4
        "gpt-3.5-turbo": gpt_35_turbo,
        "gpt-4": gpt_4,
        # H2o
        "falcon-40b": falcon_40b,
        "falcon-7b": falcon_7b,
        "llama-13b": llama_13b,
        # Vercel
        "claude-instant-v1": claude_instant_v1,
        "claude-v1": claude_v1,
        "claude-v2": claude_v2,
        "command-light-nightly": command_light_nightly,
        "command-nightly": command_nightly,
        "gpt-neox-20b": gpt_neox_20b,
        "oasst-sft-1-pythia-12b": oasst_sft_1_pythia_12b,
        "oasst-sft-4-pythia-12b-epoch-3.5": oasst_sft_4_pythia_12b_epoch_35,
        "santacoder": santacoder,
        "bloom": bloom,
        "flan-t5-xxl": flan_t5_xxl,
        "code-davinci-002": code_davinci_002,
        "gpt-3.5-turbo-16k": gpt_35_turbo_16k,
        "gpt-3.5-turbo-16k-0613": gpt_35_turbo_16k_0613,
        "gpt-4-0613": gpt_4_0613,
        "text-ada-001": text_ada_001,
        "text-babbage-001": text_babbage_001,
        "text-curie-001": text_curie_001,
        "text-davinci-002": text_davinci_002,
        "text-davinci-003": text_davinci_003,
        "llama13b-v2-chat": llama13b_v2_chat,
        "llama7b-v2-chat": llama7b_v2_chat,
    }


from g4f import ChatCompletion

providers = [
    # Working:
    GetGpt,
    # Works sometimes:
    Aichat,
    Ails,
    Vercel,
    Yqcloud,
    Acytoo,
    Equing,
    Opchatgpts,
    Wewordle,
    DeepAi,  # Wierd response seem complete the prompt only
    ChatgptLogin,  # seem to works but long
    EasyChat,
    You,
    # Not working today:
    AiService,
    AItianhu,
    Bing,
    # Provider.DfeHub, endless loop
    Lockchat,
    Theb,
    FastGpt,
    Forefront,
    ChatgptAi,
    H2o,
]


def validate_response(response):
    if not response:
        raise RuntimeError("Empty response")
    elif not isinstance(response, str):
        raise RuntimeError("Response is not a string")
    elif response in (
        "Vercel is currently not working.",
        "Unable to fetch the response, Please try again.",
    ) or response.startswith('{"error":{"message":'):
        raise RuntimeError(f"Response: {response}")
    else:
        return response


class Gpt4freeProvider:
    def __init__(
        self,
        AI_MODEL: str = "gpt-3.5-turbo",
        AI_TEMPERATURE: float = 0.7,
        AI_TOP_P: float = 0.7,
        MAX_TOKENS: int = 4096,
        WAIT_BETWEEN_REQUESTS: int = 1,
        WAIT_AFTER_FAILURE: int = 3,
        **kwargs,
    ):
        self.requirements = ["g4f", "GoogleBard"]
        self.AI_MODEL = AI_MODEL if AI_MODEL else "gpt-3.5-turbo"
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 0.7
        self.MAX_TOKENS = MAX_TOKENS if MAX_TOKENS else 4096
        self.AI_TOP_P = AI_TOP_P if AI_TOP_P else 0.7
        self.WAIT_BETWEEN_REQUESTS = (
            WAIT_BETWEEN_REQUESTS if WAIT_BETWEEN_REQUESTS else 1
        )
        self.WAIT_AFTER_FAILURE = WAIT_AFTER_FAILURE if WAIT_AFTER_FAILURE else 3

    async def instruct(self, prompt, tokens: int = 0):
        max_new_tokens = (
            int(self.MAX_TOKENS) - int(tokens) if tokens > 0 else self.MAX_TOKENS
        )
        for provider in providers:
            if not provider.working:
                continue
            if int(self.WAIT_BETWEEN_REQUESTS) > 0:
                time.sleep(int(self.WAIT_BETWEEN_REQUESTS))
            try:
                logging.info(f"[Gpt4Free] Use provider: {provider.__name__}")
                response = ChatCompletion.create(
                    model=ModelUtils.convert[self.AI_MODEL],
                    provider=provider,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_new_tokens,
                    temperature=float(self.AI_TEMPERATURE),
                    top_p=float(self.AI_TOP_P),
                    stream=False,
                )
                return validate_response(response=response)
            except Exception as e:
                logging.error(f"[Gpt4Free] Skip provider: {e}")
                if int(self.WAIT_AFTER_FAILURE) > 0:
                    time.sleep(int(self.WAIT_AFTER_FAILURE))
