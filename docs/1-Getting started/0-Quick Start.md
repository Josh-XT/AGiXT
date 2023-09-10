## Quick Start Guide



### Prerequisites
- [Git](https://git-scm.com/downloads)
- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)
- [Python 3.10](https://www.python.org/downloads/)
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) (if using local models on GPU)

If using Windows and trying to run locally, it is unsupported, but you will need [Windows Subsystem for Linux](https://docs.microsoft.com/en-us/windows/wsl/install-win10) and [Docker Desktop](https://docs.docker.com/docker-for-windows/install/) at a minimum in addition to the above.
### Download and Install
Open a terminal and run the following to download and install AGiXT:

```
git clone https://github.com/Josh-XT/AGiXT
cd AGiXT
./AGiXT.sh
```
### Getting Started with Local Models and AGiXT Video
This is a video that walks through the process of setting up and using AGiXT to interact with locally hosted language models. This is a great way to get started with AGiXT and see how it works. 

[![Getting Started with Local Models and AGiXT](https://img.youtube.com/vi/XbjjPdYRM_k/0.jpg)](https://www.youtube.com/watch?v=XbjjPdYRM_k)

### Environment Setup
You can choose to skip the environment setup and accept default values by entering `Y` on the first question `Quick Setup without advanced configuration? (Y for yes, N for No)`.

![image](https://github.com/Josh-XT/AGiXT/assets/102809327/7539d4cf-8081-4bca-97b9-a2affb427d59)

If you chose `N`, see the [Environment Variable Setup](https://josh-xt.github.io/AGiXT/1-Getting%20started/1-Environment%20Variables.html) documentation for guidance on setup.

### Install Options
You will be prompted to choose an install option. Choose Option 1 to get started quickly.

![image](https://github.com/Josh-XT/AGiXT/assets/102809327/944c9600-d67f-45da-ac1e-715e4c9d3912)

### Running and Updating AGiXT
Any time you want to run or update AGiXT, run the following commands from your `AGiXT` directory:
```
./AGiXT.sh
```

- Access the web interface at http://localhost:8501
- Access the AGiXT API documentation at http://localhost:7437

If you're running with the option `Run AGiXT and Text Generation Web UI with Docker (NVIDIA Only)`, you can access the Text Generation Web UI at http://localhost:7860/?__theme=dark to download and and configure your models. The `AI_PROVIDER_URI` will be `http://text-generation-webui:5000` for your AGiXT agents.
