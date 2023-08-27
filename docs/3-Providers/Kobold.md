# Kobold
- [Kobold](https://github.com/KoboldAI/KoboldAI-Client)
- [AGiXT](https://github.com/Josh-XT/AGiXT)

## Quick Start Guide
_Note: AI_MODEL should stay `default` unless there is a folder in `prompts` specific to the model that you're using. You can also create one and add your own prompts._

### Update your agent settings
1. Set `AI_MODEL` to `default` or the name of the model from the `prompts` folder.
2. Set `AI_PROVIDER_URI` to `http://localhost:5050/api/v1`, or the URI of your Kobold server.
3. If you're running from options 1-3 in the AGiXT installer, localhost would be the incorrect destination for your Kobold instance. You will need to use your local IP for the computer it is hosted on. Keep in mind that in docker, your local machine is not the localhost, it is like a machine within your machine and will have to communicate with your machine over the network by your IP that should be something similar to 192.168.1.xxx.

### Setting the correct host for Koboldcpp

#### Easy way:
1. Find out the name of your local host using the command in your system's terminal `hostname` and use it in `AI_PROVIDER_URI`. `AI_PROVIDER_URI` is set as `http://localhost:8000/api/v1`.
2. In the new graphical interface of Koboldcpp, set the HOST to `0.0.0.0` in the network settings to make the server listen on all interfaces, and choose any available port, for example, `8000`.

##### Security note:
External access: If the Kobold server listens on all interfaces, it can be accessible from outside your network if the corresponding ports are not properly secured. This means you should configure adequate firewall rules and security measures to protect your server from unauthorized access.

#### More complex and correct way:

##### Updating Koboldcpp server settings:
1. Open the settings of `Koboldcpp` in the graphical interface.
2. In the network settings section, find the `HOST` parameter and set its value to `0.0.0.0`. This will allow the Koboldcpp server to accept connections on all interfaces.
3. Choose a free port, for example, `8000`, and set it in the `PORT` parameter or a similar parameter in the graphical interface.
4. Save the changes in the settings of the Koboldcpp server.

##### Determining the IP address of the AGiXT Docker network gateway:
###### To find the IP address of the Docker network gateway for the AGiXT project, follow these steps:
1. Open a terminal on your system.
2. Execute the following command to get a list of all active Docker networks: docker network ls
3. In this list, find the network associated with the AGiXT project. It may have a name specified in the AGiXT settings. Note: usually, the network name starts with the prefix specified in the AGiXT settings. For example, it might be named `agixt_default`.
4. Once you find the AGiXT project network, record its name or identifier.
5. Now, execute the following command to get the IP address of the Docker network gateway for the AGiXT project network. Replace `<NETWORK_NAME>` with the name or identifier of the network from the previous step: docker network inspect <NETWORK_NAME> | grep Gateway For example: docker network inspect agixt_default | grep Gateway
6. The result of this command will be a line containing the IP address of the Docker network gateway. Record this IP address.

##### Updating AGiXT agent settings:
1. Open the settings of your AGiXT agent.
2. Find the `AI_PROVIDER_URI` parameter and set it to `http://IP_GATEWAY_NETWORK:8000/api/v1`, where `IP_GATEWAY_NETWORK` is the IP address of the AGiXT Docker network gateway that you obtained in the previous steps. For example: `http://172.18.0.1:8000/api/v1`

##### Checking the availability of Koboldcpp for Docker AGIXT containers:
- You must have Koboldcpp running with your selected model.
- The Koboldcpp server must be available at `http://0.0.0.0:8000` on your host system.
- Your AGiXT project must be running.
