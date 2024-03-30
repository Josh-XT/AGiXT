import subprocess
import sys
import os
import copy

try:
    import torch
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "torch"])
    import torch
try:
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        TrainingArguments,
        BitsAndBytesConfig,
    )
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "transformers"])
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        TrainingArguments,
        BitsAndBytesConfig,
    )
try:
    from peft.utils import _get_submodules
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "peft"])
    from peft.utils import _get_submodules
try:
    import bitsandbytes as bnb
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "bitsandbytes"])
    import bitsandbytes as bnb
try:
    from trl import DPOTrainer
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "trl"])
    from trl import DPOTrainer
try:
    from unsloth import FastLanguageModel
except ImportError:
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git",
        ]
    )
    from unsloth import FastLanguageModel

from peft import PeftModel
from bitsandbytes.functional import dequantize_4bit
from agixtsdk import AGiXTSDK
from Memories import Memories


def fine_tune_llm(
    agent_name: str = "AGiXT",
    dataset_name: str = "dataset",
    base_uri: str = "http://localhost:7437",
    api_key: str = "Your AGiXT API Key",
    model_name: str = "unsloth/mistral-7b-v0.2",
    max_seq_length: int = 16384,
    output_path: str = "./WORKSPACE/merged_model",
    push: bool = False,
):
    # Step 1: Build AGiXT dataset
    sdk = AGiXTSDK(base_uri=base_uri, api_key=api_key)
    response = Memories(
        agent_name=agent_name,
        agent_config=sdk.get_agentconfig(agent_name),
        collection_number=0,
        ApiClient=sdk,
    ).create_dataset_from_memories(dataset_name=dataset_name, batch_size=5)
    dataset_name = (
        response["message"].split("Creation of dataset ")[1].split(" for agent")[0]
    )
    dataset_path = f"./WORKSPACE/{dataset_name}.json"

    # Step 2: Create qLora adapter
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_name, max_seq_length=max_seq_length, load_in_4bit=True
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        lora_alpha=16,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing=True,
    )
    training_args = TrainingArguments(output_dir="./WORKSPACE")
    train_dataset = torch.load(dataset_path)
    dpo_trainer = DPOTrainer(
        model,
        model_ref=None,
        args=training_args,
        beta=0.1,
        train_dataset=train_dataset,
        tokenizer=tokenizer,
    )
    dpo_trainer.train()
    adapter_path = dpo_trainer.model_path

    # Step 3: Merge base model with qLora adapter
    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
    )
    model, tokenizer = AutoModelForCausalLM.from_pretrained(
        model_name,
        load_in_4bit=True,
        torch_dtype=torch.bfloat16,
        quantization_config=quantization_config,
        device_map="auto",
    ), AutoTokenizer.from_pretrained(model_name)
    os.makedirs(output_path, exist_ok=True)
    if os.path.exists(output_path):
        return AutoModelForCausalLM.from_pretrained(
            output_path, torch_dtype=torch.bfloat16, device_map="auto"
        )
    for name, module in model.named_modules():
        if isinstance(module, bnb.nn.Linear4bit):
            quant_state = copy.deepcopy(module.weight.quant_state)
            quant_state.dtype = torch.bfloat16
            weights = dequantize_4bit(
                module.weight.data, quant_state=quant_state, quant_type="nf4"
            ).to(torch.bfloat16)
            new_module = torch.nn.Linear(
                module.in_features, module.out_features, bias=None, dtype=torch.bfloat16
            )
            new_module.weight = torch.nn.Parameter(weights)
            new_module.to(device="cuda", dtype=torch.bfloat16)
            parent, target, target_name = _get_submodules(model, name)
            setattr(parent, target_name, new_module)
    model.is_loaded_in_4bit = False
    model.save_pretrained(output_path)
    tokenizer.save_pretrained(output_path)
    model = PeftModel.from_pretrained(model=model, model_id=adapter_path)
    model = model.merge_and_unload()
    model.save_pretrained(output_path, safe_serialization=True, max_shard_size="4GB")
    if push:
        model.push_to_hub(output_path, use_temp_dir=False)
        tokenizer.push_to_hub(output_path, use_temp_dir=False)


if __name__ == "__main__":
    # Usage
    fine_tune_llm(
        agent_name="AGiXT",
        dataset_name="dataset",
        base_uri="http://localhost:7437",
        api_key="Your AGiXT API Key",
        model_name="unsloth/mistral-7b-v0.2",
        max_seq_length=16384,
        output_path="./WORKSPACE/merged_model",
        push=False,
    )
