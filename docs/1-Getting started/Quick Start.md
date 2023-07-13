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

### Environment Setup
During the installation, you will be prompted to enter some settings unless you already have your `.env` file set up.  If you do not have your `.env` file set up, you can use the following as a guide:

![image](https://github.com/Josh-XT/AGiXT/assets/102809327/c8ae9698-f1e0-44b8-9fb2-85cb66b684b7)

- `AGIXT_API_KEY` is the API key to use for the AGiXT API.  This is empty by default, if you would like to set it, change it in the env file.  The header format for requests will be `Authorization: Bearer {your_api_key}` for any requests to your AGiXT server or you can pass the `api_key` to the AGiXT SDK.

- `AGIXT_HUB` is the name of the AGiXT hub, this should be `AGiXT/hub` if you want to use the [Open Source AGiXT hub.](https://github.com/AGiXT/hub) If you want to use your own fork of AGiXT hub, change this to your username and the name of your fork.

- `AGIXT_URI` is the URI of the AGiXT hub, this should be `http://agixt:7437` by default. If hosting the AGiXT server separately, change this to the URI of your AGiXT server, otherwise leave it as-is.
- `GITHUB_USER` is your GitHub username, this is only required if using your own AGiXT hub to pull your repository data.
- `GITHUB_TOKEN` is your GitHub personal access token, this is only required if using your own AGiXT hub to pull your repository data.
- `UVICORN_WORKERS` is the number of workers to run the web server with, this is `6` by default, adjust this to your system's capabilities.

**Database configuration only applicable if using database**
- `DB_CONNECTED` is whether or not you want to use a database, this should be `false` by default, change this to `true` if you want to use a database. If you choose to, you will need to edit the database configuration options below, otherwise they can be left alone.
- `POSTGRES_SERVER` is the name of the database server, this should be `db` by default.
- `POSTGRES_DB` is the name of the database, this should be `postgres` by default.
- `POSTGRES_PORT` is the port that the database is listening on, this should be `5432` by default.
- `POSTGRES_USER` is the username to connect to the database with, this should be `postgres` by default.
- `POSTGRES_PASSWORD` **is the password to connect to the database with, this should be changed from the example file if using database.**

**Oobabooga Text Generation Web UI Configuration**
- `TORCH_CUDA_ARCH_LIST` is the CUDA architecture list to use for the Oobabooga text generation web UI. Example: RTX3000-5000 series are version `7.5`. Find yours at https://developer.nvidia.com/cuda-gpus .
- `CLI_ARGS` is the CLI arguments to pass to the Oobabooga text generation web UI. By default, this is set to `--listen --api --chat` and is not configurable in the AGiXT installer, it will need changed manually in the `.env` file if you want to change it to add additional arguments.

### Install Options
You will be prompted to choose an install option.  The options are as follows:

![image](https://github.com/Josh-XT/AGiXT/assets/102809327/dd83bda7-f592-4bd8-a377-e2eb5e7e5dcb)

1. **Run AGiXT with Docker (Recommended)**
    - This option will run [AGiXT](https://github.com/Josh-XT/AGiXT) and the [AGiXT Streamlit Web UI](https://github.com/AGiXT/streamlit) in Docker containers.  This is the recommended option for most users.
2. **Run AGiXT Locally (Developers Only - Not Recommended or Supported)**
    - This option will run [AGiXT](https://github.com/Josh-XT/AGiXT) and the [AGiXT Streamlit Web UI](https://github.com/AGiXT/streamlit) locally. This is not recommended or supported due to it requiring you to have a lot of dependencies installed on your computer that may conflict with other software you have installed. This is only recommended for developers who want to contribute to AGiXT.
3. **Run AGiXT and Text Generation Web UI with Docker (NVIDIA Only)**
    - This option is only available if you have an NVIDIA GPU and will not work if you do not.
    - This option will run [AGiXT](https://github.com/Josh-XT/AGiXT), the [AGiXT Streamlit Web UI](https://github.com/AGiXT/streamlit), and the [Oobabooga Text Generation Web UI](https://github.com/oobabooga/text-generation-webui) in Docker containers. This is the recommended option for most users who want to use local models on GPU. You will need a powerful video card to run this option. We highly recommend reviewing their documentation before using this option unless you have run local models on GPU before.
4. **Update AGiXT**
    - This option will update [AGiXT](https://github.com/Josh-XT/AGiXT), [AGiXT Streamlit Web UI](https://github.com/AGiXT/streamlit), and [Oobabooga Text Generation Web UI](https://github.com/oobabooga/text-generation-webui) if you have them installed.  It is always recommended to be on the latest version of all.
5. **Wipe AGiXT Hub (Irreversible)**
    - This option will delete `agixt/providers`, `agixt/extensions`, `agixt/chains`, and `agixt/prompts`. The next time you start AGiXT, it will redownload all of them from the [AGiXT Hub](https://github.com/AGiXT/hub) that you have configured in your `.env` file. This is mostly used for development and testing purposes.
6. **Exit**
    - This option will exit the installer.

### Running and Updating AGiXT
Any time you want to run or update AGiXT, run the following commands from your `AGiXT` directory:
```
./AGiXT.sh
```

Then follow the prompts to run or update AGiXT either locally or with Docker. We generally recommend running with Docker.

- Access the web interface at http://localhost:8501
- Access the AGiXT API documentation at http://localhost:7437

If you're running with the option `Run AGiXT and Text Generation Web UI with Docker (NVIDIA Only)`, you can access the Text Generation Web UI at http://localhost:7860/?__theme=dark to download and and configure your models. The `AI_PROVIDER_URI` will be `http://text-generation-webui:5000` for your AGiXT agents.
