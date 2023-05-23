#!/bin/bash
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp
pip install -r requirements.txt
cd models
git lfs install
git clone https://huggingface.co/HuggingFaceH4/starchat-alpha
cd ..
sudo make LLAMA_CUBLAS=1
python3 -m convert.py models/starchat-alpha/
./quantize ./models/starchat-alpha/pytorch_model.bin ./models/starchat-alpha/quantized_model.bin q5_0
./server --model models/starchat-alpha/quantized_model.bin --ctx_size 8000 --ngl 32 -port 7171