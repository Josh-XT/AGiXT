#!/bin/bash
git clone https://github.com/bigcode-project/starcoder.cpp
cd starcoder.cpp
python convert-hf-to-ggml.py bigcode/gpt_bigcode-santacoder
python convert-hf-to-ggml.py HuggingFaceH4/starchat-alpha
sudo make
./quantize models/bigcode/gpt_bigcode-santacoder-ggml.bin models/bigcode/gpt_bigcode-santacoder-ggml-q4_1.bin 3
./quantize models/HuggingFaceH4/starchat-alpha-ggml.bin models/HuggingFaceH4/starchat-alpha-ggml-q4_1.bin 3
cd ..
./server -m models/HuggingFaceH4/starchat-alpha-ggml-q4_1.bin --ctx_size 8000 -port 7171 -ngl 50