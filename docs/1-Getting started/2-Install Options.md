### Install Options
You will be prompted to choose an install option.  The first 3 options require you to have Docker installed. The options are as follows:

![image](https://github.com/Josh-XT/AGiXT/assets/102809327/517e9986-4eb6-45e5-9268-444788bac200)

1. **Run AGiXT (Recommended)**
    - This option will run [AGiXT](https://github.com/Josh-XT/AGiXT) and the [AGiXT Streamlit Web UI](https://github.com/AGiXT/streamlit) in Docker containers.  This is the recommended option for most users.
2. **Run AGiXT with Text Generation Web UI (NVIDIA Only)**
    - This option is only available if you have an NVIDIA GPU and will not work if you do not.
    - This option will run [AGiXT](https://github.com/Josh-XT/AGiXT), the [AGiXT Streamlit Web UI](https://github.com/AGiXT/streamlit), and the [Oobabooga Text Generation Web UI](https://github.com/oobabooga/text-generation-webui) in Docker containers. This is the recommended option for most users who want to use local models on GPU. You will need a powerful video card to run this option. We highly recommend reviewing their documentation before using this option unless you have run local models on GPU before.
3. **Run AGiXT with Text Generation Web UI and Stable Diffusion (NVIDIA Only)**
   - All of the same as option 2, except this also launches an [AUTOMATIC1111 Stable Diffusion Web UI](https://github.com/AUTOMATIC1111/stable-diffusion-webui) as well.

**Developer Only Options (Not recommended or supported):**

4. **Run AGiXT (Recommended)**
    - This option will run [AGiXT](https://github.com/Josh-XT/AGiXT) and the [AGiXT Streamlit Web UI](https://github.com/AGiXT/streamlit) in Docker containers.  This is the recommended option for most users.
5. **Run AGiXT on local machine**
    - This option will run [AGiXT](https://github.com/Josh-XT/AGiXT) and the [AGiXT Streamlit Web UI](https://github.com/AGiXT/streamlit) locally. This is not recommended or supported due to it requiring you to have a lot of dependencies installed on your computer that may conflict with other software you have installed. This is only recommended for developers who want to contribute to AGiXT.

**Manage:**

6. **Update AGiXT**
    - This option will update [AGiXT](https://github.com/Josh-XT/AGiXT), [AGiXT Streamlit Web UI](https://github.com/AGiXT/streamlit), and [Oobabooga Text Generation Web UI](https://github.com/oobabooga/text-generation-webui) if you have them installed.  It is always recommended to be on the latest version of all.
7. **Wipe AGiXT Hub (Irreversible)**
    - This option will delete `agixt/providers`, `agixt/extensions`, `agixt/chains`, and `agixt/prompts`. The next time you start AGiXT, it will redownload all of them from the [AGiXT Hub](https://github.com/AGiXT/hub) that you have configured in your `.env` file. This is mostly used for development and testing purposes.
7. **Exit**
    - This option will exit the installer.
