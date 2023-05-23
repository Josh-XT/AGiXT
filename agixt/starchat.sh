#!/bin/bash
git clone https://github.com/bigcode-project/starcoder.cpp
cd starcoder.cpp
python convert-hf-to-ggml.py bigcode/gpt_bigcode-santacoder
python convert-hf-to-ggml.py HuggingFaceH4/starchat-alpha
python convert-hf-to-ggml.py sentence-transformers/gtr-t5-large
sudo make
./quantize models/bigcode/gpt_bigcode-santacoder-ggml.bin models/bigcode/gpt_bigcode-santacoder-ggml-q4_1.bin 3
./quantize models/HuggingFaceH4/starchat-alpha-ggml.bin models/HuggingFaceH4/starchat-alpha-ggml-q4_1.bin 3
./quantize models/sentence-transformers/gtr-t5-large-ggml.bin models/sentence-transformers/gtr-t5-large-ggml-q4_1.bin 3
# ./main -m models/HuggingFaceH4/starchat-alpha-ggml-q4_1.bin -p "def fibonnaci(" --top_k 0 --top_p 0.95 --temp 0.2
cd ..
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp
pip install -r requirements.txt
sudo make
./server --model ../starchat.cpp/models/HuggingFaceH4/starchat-alpha-ggml-q4_1.bin --ctx_size 8000 -port 7171
./server --model ../starchat.cpp/models/sentence-transformers/gtr-t5-large-ggml-q4_1.bin --ctx_size 128 -port 7172 --embeddings