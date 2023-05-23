#!/bin/bash
# This is set up for running an NVIDIA RTX 3080 GPU or better.
# Install cuda first if not installed, make will fail if it is not installed.
# https://developer.nvidia.com/cuda-downloads
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp
pip install -r requirements.txt
sudo make LLAMA_CUBLAS=1
cd models
git lfs install
# Starchat 8K model
git clone https://huggingface.co/HuggingFaceH4/starchat-alpha
# Embedding model
git clone https://huggingface.co/sentence-transformers/gtr-t5-large
cd ..
python3 -m convert.py models/starchat-alpha/
python3 -m convert.py models/gtr-t5-large/
./quantize ./models/starchat-alpha/pytorch_model.bin ./models/starchat-alpha/quantized_model.bin q5_0
./quantize ./models/gtr-t5-large/pytorch_model.bin ./models/gtr-t5-large/quantized_model.bin q5_0
./server --model models/starchat-alpha/quantized_model.bin --ctx_size 8000 --ngl 32 -port 7171
./server --model models/gtr-t5-large/quantized_model.bin --ctx_size 128 --ngl 32 -port 7172 --embeddings