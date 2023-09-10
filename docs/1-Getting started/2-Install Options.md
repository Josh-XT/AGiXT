### Install Options
You will be prompted to choose an install option.  The first 3 options require you to have Docker installed. The options are as follows:

![image](https://github.com/Josh-XT/AGiXT/assets/102809327/944c9600-d67f-45da-ac1e-715e4c9d3912)

1. **Run AGiXT (Recommended)**
    - This option will run [AGiXT](https://github.com/Josh-XT/AGiXT) and the [AGiXT Streamlit Web UI](https://github.com/AGiXT/streamlit) in Docker containers.  This is the recommended option for most users.
2. **Run AGiXT with Text Generation Web UI (NVIDIA Only)**
    - This option is only available if you have an NVIDIA GPU and will not work if you do not.
    - This option will run [AGiXT](https://github.com/Josh-XT/AGiXT), the [AGiXT Streamlit Web UI](https://github.com/AGiXT/streamlit), and the [Oobabooga Text Generation Web UI](https://github.com/oobabooga/text-generation-webui) in Docker containers. This is the recommended option for most users who want to use local models on GPU. You will need a powerful video card to run this option. We highly recommend reviewing their documentation before using this option unless you have run local models on GPU before.
3. **Run AGiXT with Text Generation Web UI and Stable Diffusion (NVIDIA Only)**
   - All of the same as option 2, except this also launches an [AUTOMATIC1111 Stable Diffusion Web UI](https://github.com/AUTOMATIC1111/stable-diffusion-webui) as well.

**Developer Only Options (Not recommended or supported):**

4. **Run AGiXT from Main Branch**
    - This option is like option 1, except it pulls from the main branch instead of the latest release version of AGiXT. This is not recommended or supported due to it being unstable and may break at any time.
5. **Run AGiXT from Main Branch + Addons (NVIDIA Only)**
    - This option is like option 3, except it pulls from the main branch instead of the latest release version of AGiXT. This is not recommended or supported due to it being unstable and may break at any time.
6. **Run AGiXT without Docker**
    - This option will run AGiXT without Docker. This is not recommended or supported due to it being unstable and may break at any time.

**Manage:**

7. **Enable/Disable Automatic Updates**
    - This option will enable or disable automatic updates for AGiXT.
8. **Exit**
    - This option will exit the installer.
