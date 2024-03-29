import argparse
import json
import os
import sys
import subprocess
import copy

try:
    import torch
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "torch"])
    import torch
try:
    from transformers import TrainingArguments
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "transformers"])
    from transformers import TrainingArguments
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
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)
from agixtsdk import AGiXTSDK

agixt = AGiXTSDK(base_uri="http://localhost:7437", api_key="Your AGiXT API Key")

# Define the agent we're working with
agent_name = "gpt4free"

# Consume the whole AGiXT GitHub Repository to the agent's memory.
agixt.learn_github_repo(
    agent_name=agent_name,
    github_repo="Josh-XT/AGiXT",
    collection_number=0,
)

# Create a synthetic dataset in DPO/CPO/ORPO format.
agixt.create_dataset(
    agent_name=agent_name, dataset_name="Your_dataset_name", batch_size=5
)


def create_qlora(model_name, train_dataset, max_seq_length=2048):
    # Supports automatic RoPE Scaling, so choose any number.
    # Load model
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_name,
        max_seq_length=max_seq_length,
        dtype=None,  # None for auto detection. Float16 for Tesla T4, V100, Bfloat16 for Ampere+
        load_in_4bit=True,  # Use 4bit quantization to reduce memory usage. Can be False.
        # token = "hf_...", # use one if using gated models like meta-llama/Llama-2-7b-hf
    )

    # Do model patching and add fast LoRA weights
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        lora_alpha=16,
        lora_dropout=0,  # Dropout = 0 is currently optimized
        bias="none",  # Bias = "none" is currently optimized
        use_gradient_checkpointing=True,
        random_state=3407,
    )

    training_args = TrainingArguments(output_dir="./WORKSPACE")

    dpo_trainer = DPOTrainer(
        model,
        model_ref=None,
        args=training_args,
        beta=0.1,
        train_dataset=train_dataset,
        tokenizer=tokenizer,
    )
    dpo_trainer.train()


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=str)
    parser.add_argument("--peft", type=str)
    parser.add_argument("--out", type=str)
    parser.add_argument("--push", action="store_true")
    return parser.parse_args()


def dequantize_model(model, tokenizer, to, dtype=torch.bfloat16, device="cuda"):
    """
    'model': the peftmodel you loaded with qlora.
    'tokenizer': the model's corresponding hf's tokenizer.
    'to': directory to save the dequantized model
    'dtype': dtype that the model was trained using
    'device': device to load the model to
    """
    if os.path.exists(to):
        return AutoModelForCausalLM.from_pretrained(
            to, torch_dtype=torch.bfloat16, device_map="auto"
        )
    os.makedirs(to, exist_ok=True)
    cls = bnb.nn.Linear4bit
    with torch.no_grad():
        for name, module in model.named_modules():
            if isinstance(module, cls):
                print(f"Dequantizing `{name}`...")
                quant_state = copy.deepcopy(module.weight.quant_state)
                quant_state.dtype = dtype
                weights = dequantize_4bit(
                    module.weight.data, quant_state=quant_state, quant_type="nf4"
                ).to(dtype)
                new_module = torch.nn.Linear(
                    module.in_features, module.out_features, bias=None, dtype=dtype
                )
                new_module.weight = torch.nn.Parameter(weights)
                new_module.to(device=device, dtype=dtype)
                parent, target, target_name = _get_submodules(model, name)
                setattr(parent, target_name, new_module)
        model.is_loaded_in_4bit = False
        print("Saving dequantized model...")
        model.save_pretrained(to)
        tokenizer.save_pretrained(to)
        config_data = json.loads(open(os.path.join(to, "config.json"), "r").read())
        config_data.pop("quantization_config", None)
        config_data.pop("pretraining_tp", None)
        with open(os.path.join(to, "config.json"), "w") as config:
            config.write(json.dumps(config_data, indent=2))
        return model


def main():
    args = get_args()
    model_path = args.base
    adapter_path = args.peft
    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
    )
    print(f"Loading base model: {model_path}")
    model = None
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    if os.path.exists(f"{model_path}-dequantized"):
        model = AutoModelForCausalLM.from_pretrained(
            f"{model_path}-dequantized",
            torch_dtype=torch.bfloat16,
            device_map="auto",
        )
    else:
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            load_in_4bit=True,
            torch_dtype=torch.bfloat16,
            quantization_config=quantization_config,
            device_map="auto",
        )
        model = dequantize_model(model, tokenizer, to=f"{model_path}-dequantized")
    model = PeftModel.from_pretrained(model=model, model_id=adapter_path)
    model = model.merge_and_unload()
    print("Successfully loaded and merged model, saving...")
    model.save_pretrained(args.out, safe_serialization=True, max_shard_size="4GB")
    tokenizer.save_pretrained(args.out)
    config_data = json.loads(open(os.path.join(args.out, "config.json"), "r").read())
    config_data.pop("quantization_config", None)
    config_data.pop("pretraining_tp", None)
    with open(os.path.join(args.out, "config.json"), "w") as config:
        config.write(json.dumps(config_data, indent=2))
    print(f"Model saved: {args.out}")
    if args.push:
        print(f"Saving to hub ...")
        model.push_to_hub(args.out, use_temp_dir=False)
        tokenizer.push_to_hub(args.out, use_temp_dir=False)
        print("Model successfully pushed to hf.")
