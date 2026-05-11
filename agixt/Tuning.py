import copy
import asyncio
import json
import os
from Globals import install_package_if_missing

# Install tuning dependencies if missing
install_package_if_missing("torch")
install_package_if_missing("transformers")
install_package_if_missing("peft")
install_package_if_missing("bitsandbytes")
install_package_if_missing("trl")
install_package_if_missing("datasets")
install_package_if_missing(
    "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git", "unsloth"
)

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    BitsAndBytesConfig,
)
from peft.utils import _get_submodules
import bitsandbytes as bnb
from trl import DPOTrainer
from datasets import Dataset
from unsloth import FastLanguageModel

from peft import PeftModel
from bitsandbytes.functional import dequantize_4bit
from XT import AGiXT


def _run_async(coro):
    """Run an async AGiXT helper from the background fine-tuning thread."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("fine_tune_llm must run outside an active event loop")


def _latest_dataset_path(dataset_dir: str, before: set[str]) -> str:
    dataset_files = {
        os.path.join(dataset_dir, filename)
        for filename in os.listdir(dataset_dir)
        if filename.endswith(".json")
    }
    new_files = dataset_files - before
    candidates = new_files or dataset_files
    if not candidates:
        raise FileNotFoundError(f"No dataset JSON files found in {dataset_dir}")
    return max(candidates, key=os.path.getmtime)


def fine_tune_llm(
    agent_name: str = "AGiXT",
    dataset_name: str = "dataset",
    model_name: str = "unsloth/mistral-7b-v0.2",
    max_seq_length: int = 16384,
    huggingface_output_path: str = "JoshXT/finetuned-mistral-7b-v0.2",
    private_repo: bool = True,
    user: str = "user",
    api_key: str = "",
):
    output_path = "./models"
    # Step 1: Build AGiXT dataset
    agixt = AGiXT(
        user=user,
        api_key=api_key,
        agent_name=agent_name,
        conversation_name=dataset_name,
    )
    agent_settings = agixt.agent_settings
    if not agent_settings:
        agent_settings = {}
    huggingface_api_key = (
        agent_settings["HUGGINGFACE_API_KEY"]
        if "HUGGINGFACE_API_KEY" in agent_settings
        else None
    )
    dataset_dir = os.path.join(agixt.agent_workspace, "datasets")
    os.makedirs(dataset_dir, exist_ok=True)
    existing_datasets = {
        os.path.join(dataset_dir, filename)
        for filename in os.listdir(dataset_dir)
        if filename.endswith(".json")
    }
    _run_async(
        agixt.create_dataset_from_memories(
            batch_size=5,
        )
    )
    dataset_path = _latest_dataset_path(dataset_dir, existing_datasets)
    agent_settings["training"] = True
    agixt.agent_interactions.agent.update_agent_config(
        new_config=agent_settings, config_key="settings"
    )
    try:
        # Step 2: Create qLora adapter
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=model_name,
            max_seq_length=max_seq_length,
            load_in_4bit=True,
            token=huggingface_api_key,
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
        with open(dataset_path, "r", encoding="utf-8") as dataset_file:
            train_dataset = Dataset.from_dict(json.load(dataset_file))
        dpo_trainer = DPOTrainer(
            model,
            model_ref=None,
            args=training_args,
            beta=0.1,
            train_dataset=train_dataset,
            tokenizer=tokenizer,
        )
        dpo_trainer.train()
        adapter_path = getattr(dpo_trainer, "model_path", training_args.output_dir)

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
            token=huggingface_api_key,
        ), AutoTokenizer.from_pretrained(model_name)
        os.makedirs(output_path, exist_ok=True)
        for name, module in model.named_modules():
            if isinstance(module, bnb.nn.Linear4bit):
                quant_state = copy.deepcopy(module.weight.quant_state)
                quant_state.dtype = torch.bfloat16
                weights = dequantize_4bit(
                    module.weight.data, quant_state=quant_state, quant_type="nf4"
                ).to(torch.bfloat16)
                new_module = torch.nn.Linear(
                    module.in_features,
                    module.out_features,
                    bias=None,
                    dtype=torch.bfloat16,
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
        model.save_pretrained(
            output_path, safe_serialization=True, max_shard_size="4GB"
        )
        if huggingface_api_key:
            model.push_to_hub(
                huggingface_output_path, use_temp_dir=False, private=private_repo
            )
            tokenizer.push_to_hub(
                huggingface_output_path, use_temp_dir=False, private=private_repo
            )
    finally:
        agent_settings["training"] = False
        agixt.agent_interactions.agent.update_agent_config(
            new_config=agent_settings, config_key="settings"
        )


if __name__ == "__main__":
    # Usage
    fine_tune_llm(
        agent_name="AGiXT",
        dataset_name="dataset",
        model_name="unsloth/llama-3-8b-Instruct-bnb-4bit",
        max_seq_length=16384,
        huggingface_output_path="JoshXT/finetuned-llama-3-8b",
        private_repo=True,
        user="user",
        api_key="Your AGiXT API Key",
    )
