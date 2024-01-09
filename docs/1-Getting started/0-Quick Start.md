## Quick Start Guide

### Windows and Mac Prerequisites

- [Git](https://git-scm.com/downloads)
- [Docker Desktop](https://docs.docker.com/docker-for-windows/install/)
- [PowerShell 7.X](https://learn.microsoft.com/en-us/powershell/scripting/install/installing-powershell?view=powershell-7.4)

### Linux Prerequisites

- [Git](https://git-scm.com/downloads)
- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)
- [PowerShell 7.X](https://learn.microsoft.com/en-us/powershell/scripting/install/installing-powershell?view=powershell-7.4) (Optional if you want to use the launcher script, but not required)
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) (if using local models on GPU)

### Download and Install

Open a PowerShell terminal and run the following to download and install AGiXT:

```bash
git clone https://github.com/Josh-XT/AGiXT
cd AGiXT
./AGiXT.ps1
```

When you run the `AGiXT.ps1` script for the first time, it will create a `.env` file automatically. There are a few questions asked on first run to help you get started. The default options are recommended for most users.

For advanced environment variable setup, see the [Environment Variable Setup](https://josh-xt.github.io/AGiXT/1-Getting%20started/1-Environment%20Variables.html) documentation for guidance on setup.

```bash
    ___   _______ _  ________
   /   | / ____(_) |/ /_  __/
  / /| |/ / __/ /|   / / /
 / ___ / /_/ / //   | / /
/_/  |_\____/_//_/|_|/_/

-------------------------------
Visit our documentation at https://AGiXT.com
Welcome to the AGiXT Environment Setup!
Would you like AGiXT to auto update? (y/n - default: y):
Would you like to set an API Key for AGiXT? Enter it if so, otherwise press enter to proceed. (default is blank):
Enter the number of AGiXT workers to run (default: 10):
```

After the environment setup is complete, you will have the following options:

```bash
1. Run AGiXT (Stable - Recommended!)
2. Run AGiXT (Development)
3. Run Backend Only (Development)
4. Exit
Enter your choice: 
```

Choose Option 1 to run AGiXT with the latest stable release. This is the recommended option for most users. If you're not actively developing AGiXT, this is the option you should choose.

### Running and Updating AGiXT

Any time you want to run or update AGiXT, run the following commands from your `AGiXT` directory:

```bash
./AGiXT.ps1
```

- Access the web interface at <http://localhost:8501>
- Access the AGiXT API documentation at <http://localhost:7437>
