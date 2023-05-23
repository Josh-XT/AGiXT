# Import the required libraries
from huggingface_hub import hf_hub_download
import subprocess

# git clone https://github.com/ggerganov/llama.cpp
subprocess.run(["git", "clone", "https://github.com/ggerganov/llama.cpp"])
# create llama.cpp/models directory if it does not exist
subprocess.run(["mkdir", "-p", "./llama.cpp/models"])
# Download the model and tokenizer from Hugging Face
model_id = "HuggingFaceH4/starchat-alpha"
filename = "pytorch_model.bin"
model_file = hf_hub_download(
    repo_id=model_id, filename=filename, cache_dir="./llama.cpp/models"
)

# Convert the model to GGML format using llama.cpp
subprocess.run(["./llama.cpp/convert.py", "starchat-alpha", "starchat-alpha.ggml"])
# Llamacpp API Server
# ./server --model "/path/to/ggml-model.bin" --ctx_size 2048 --ngl 32 -port 7171
# Embedding server
# ./server --model "/path/to/ggml-model.bin" --ctx_size 2048 --ngl 32 -port 7172 --embedding

subprocess.run(
    [
        "./llama.cpp/server",
        "--model",
        "./models/starchat-alpha.ggml",
        "--ctx_size",
        "2048",
        "--ngl",
        "32",
        "-port",
        "7171",
    ]
)
subprocess.run(
    [
        "./llama.cpp/server",
        "--model",
        "./models/starchat-alpha.ggml",
        "--ctx_size",
        "2048",
        "--ngl",
        "32",
        "-port",
        "7172",
        "--embedding",
    ]
)
