import subprocess


def is_cuda():
    try:
        result = subprocess.run(
            ["nvidia-smi"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        return "NVIDIA-SMI" in result.stdout
    except:
        return False


if __name__ == "__main__":
    print(is_cuda())
