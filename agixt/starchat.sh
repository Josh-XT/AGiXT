#!/bin/bash
git clone https://github.com/ggerganov/llama.cpp
git clone https://github.com/bigcode-project/starcoder.cpp
cd starcoder.cpp
python convert-hf-to-ggml.py bigcode/gpt_bigcode-santacoder
python convert-hf-to-ggml.py HuggingFaceH4/starchat-alpha
sudo make
./quantize models/bigcode/gpt_bigcode-santacoder-ggml.bin models/bigcode/gpt_bigcode-santacoder-ggml-q4_1.bin 3
./quantize models/HuggingFaceH4/starchat-alpha-ggml.bin models/HuggingFaceH4/starchat-alpha-ggml-q4_1.bin 3
cd ..
cd llama.cpp
pip install -r requirements.txt
sudo make
./server -m ../starchat.cpp/models/HuggingFaceH4/starchat-alpha-ggml-q4_1.bin --ctx_size 8000 -port 7171 -ngl 50


docker run --gpus all -v ../starchat.cpp/models:/models localagi/llama-cpp-python:main-cublas-12.1.1 --model /models/starchat-alpha-GGML/starchat-alpha-ggml-q5_1.bin  --n_ctx 8000 --last_n_tokens_size 255 --n_threads 24 --n_gpu_layers 40