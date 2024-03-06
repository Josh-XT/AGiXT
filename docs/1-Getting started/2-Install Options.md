# Install Options

You will be prompted to choose an option when you run `AGiXT.ps1`. If you're not actively developing on the AGiXT platform, I recommend choosing option 1. The other options are unsupported and may break at any time as they use the development branch of AGiXT.

```bash
1. Run AGiXT (Stable - Recommended!)
2. Run AGiXT (Development)
3. Run Backend Only (Development)
4. Exit
Enter your choice: 
```

1. **Run AGiXT (Stable - Recommended)**
    - This option will run [AGiXT](https://github.com/Josh-XT/AGiXT) and the [AGiXT Streamlit Web UI](https://github.com/AGiXT/streamlit) in Docker containers.  This is the recommended option for most users.
2. **Run AGiXT (Development)**
    - This option is like option 1, except it pulls from the main branch instead of the latest release version of AGiXT. This is not recommended or supported due to it being unstable and may break at any time.
3. **Run AGiXT Back End Only (Development)**
    - This option is like option 2, except it only runs the back end of AGiXT from the main branch.
