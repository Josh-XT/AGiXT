import os
import json
import glob
import shutil
from dotenv import load_dotenv
load_dotenv()

class Config():
    def __init__(self):
        # General Configuration
        self.AGENT_NAME = os.getenv("AGENT_NAME", "Agent-LLM")
        self.AGENTS = glob.glob(os.path.join("memories", "*.yaml"))
        # Goal Configuation
        self.OBJECTIVE = os.getenv("OBJECTIVE", "Solve world hunger")
        self.INITIAL_TASK = os.getenv("INITIAL_TASK", "Develop a task list")
        
        # AI Configuration
        self.AI_PROVIDER = os.getenv("AI_PROVIDER", "openai").lower()

        # AI_PROVIDER_URI is only needed for custom AI providers such as Oobabooga Text Generation Web UI
        self.AI_PROVIDER_URI = os.getenv("AI_PROVIDER_URI", "http://127.0.0.1:7860")
        self.MODEL_PATH = os.getenv("MODEL_PATH")

        # Bing Conversation Style if using Bing. Options are creative, balanced, and precise
        self.BING_CONVERSATION_STYLE = os.getenv("BING_CONVERSATION_STYLE", "creative").lower()

        # ChatGPT Configuration
        self.CHATGPT_USERNAME = os.getenv("CHATGPT_USERNAME")
        self.CHATGPT_PASSWORD = os.getenv("CHATGPT_PASSWORD")

        self.COMMANDS_ENABLED = os.getenv("COMMANDS_ENABLED", "true").lower()
        self.WORKING_DIRECTORY = os.getenv("WORKING_DIRECTORY", "WORKSPACE")
        if not os.path.exists(self.WORKING_DIRECTORY):
            os.makedirs(self.WORKING_DIRECTORY)
        
        # Memory Settings
        self.NO_MEMORY = os.getenv("NO_MEMORY", "false").lower()
        self.USE_LONG_TERM_MEMORY_ONLY = os.getenv("USE_LONG_TERM_MEMORY_ONLY", "false").lower()

        # Model configuration
        self.AI_MODEL = os.getenv("AI_MODEL", "gpt-3.5-turbo").lower()
        self.AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", 0.4))
        self.MAX_TOKENS = os.getenv("MAX_TOKENS", 2000)
        
        # Extensions Configuration

        # OpenAI
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

        # Huggingface
        self.HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")
        self.HUGGINGFACE_AUDIO_TO_TEXT_MODEL = os.getenv("HUGGINGFACE_AUDIO_TO_TEXT_MODEL", "facebook/wav2vec2-large-960h-lv60-self")
        
        # Selenium
        self.SELENIUM_WEB_BROWSER = os.getenv("SELENIUM_WEB_BROWSER", "chrome").lower()

        # Twitter
        self.TW_CONSUMER_KEY = os.getenv("TW_CONSUMER_KEY")
        self.TW_CONSUMER_SECRET = os.getenv("TW_CONSUMER_SECRET")
        self.TW_ACCESS_TOKEN = os.getenv("TW_ACCESS_TOKEN")
        self.TW_ACCESS_TOKEN_SECRET = os.getenv("TW_ACCESS_TOKEN_SECRET")

        # Github
        self.GITHUB_API_KEY = os.getenv("GITHUB_API_KEY")
        self.GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")

        # Sendgrid
        self.SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
        self.SENDGRID_EMAIL = os.getenv("SENDGRID_EMAIL")

        # Microsft 365
        self.MICROSOFT_365_CLIENT_ID = os.getenv("MICROSOFT_365_CLIENT_ID")
        self.MICROSOFT_365_CLIENT_SECRET = os.getenv("MICROSOFT_365_CLIENT_SECRET")
        self.MICROSOFT_365_REDIRECT_URI = os.getenv("MICROSOFT_365_REDIRECT_URI")

        # Voice (Choose one: ElevenLabs, Brian, Mac OS)
        # Elevenlabs
        self.ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
        self.ELEVENLABS_VOICE = os.getenv("ELEVENLABS_VOICE", "Josh")
        # Mac OS TTS
        self.USE_MAC_OS_TTS = os.getenv("USE_MAC_OS_TTS", "false").lower()

        # Brian TTS
        self.USE_BRIAN_TTS = os.getenv("USE_BRIAN_TTS", "true").lower()
        
        self.get_prompts()
        self.agent_instances = {}

    def get_prompts(self):
        if not os.path.exists(f"model-prompts/{self.CFG.AI_MODEL}"):
            self.CFG.AI_MODEL = "default"
        with open(f"model-prompts/{self.CFG.AI_MODEL}/execute.txt", "r") as f:
            self.EXECUTION_PROMPT = f.read()
        with open(f"model-prompts/{self.CFG.AI_MODEL}/task.txt", "r") as f:
            self.TASK_PROMPT = f.read()
        with open(f"model-prompts/{self.CFG.AI_MODEL}/priority.txt", "r") as f:
            self.PRIORITY_PROMPT = f.read()
    
    def create_agent_folder(self, agent_name):
        agent_folder = f"agents/{agent_name}"
        if not os.path.exists("agents"):
            os.makedirs("agents")
        if not os.path.exists(agent_folder):
            os.makedirs(agent_folder)
        return agent_folder

    def create_agent_config_file(self, agent_folder):
        agent_config_file = os.path.join(agent_folder, "config.json")
        if not os.path.exists(agent_config_file):
            with open(agent_config_file, "w") as f:
                f.write(json.dumps({"commands": {command_name: "true" for command_name, _, _ in self.commands}}))
        return agent_config_file

    def load_agent_config(self, agent_name):
        with open(os.path.join("agents", agent_name, "config.json")) as agent_config:
            try:
                agent_config_data = json.load(agent_config)
            except json.JSONDecodeError:
                agent_config_data = {}
                # Populate the agent_config with all commands enabled
                agent_config_data["commands"] = {command_name: "true" for command_name, _, _ in self.load_commands(agent_name)}
                # Save the updated agent_config to the file
                with open(os.path.join("agents", agent_name, "config.json"), "w") as agent_config_file:
                    json.dump(agent_config_data, agent_config_file)
        if agent_config_data == {} or "commands" not in agent_config_data:
            # Add all commands to agent/{agent_name}/config.json in this format {"command_name": "true"}
            agent_config_file = os.path.join("agents", agent_name, "config.json")
            with open(agent_config_file, "w") as f:
                f.write(json.dumps({"commands": {command_name: "true" for command_name, _, _ in self.commands}}))
        return agent_config_data
    
    def create_agent_yaml_file(self, agent_name):
        memories_dir = "agents"
        if not os.path.exists(memories_dir):
            os.makedirs(memories_dir)
        i = 0
        agent_file = f"{agent_name}.yaml"
        while os.path.exists(os.path.join(memories_dir, agent_file)):
            i += 1
            agent_file = f"{agent_name}_{i}.yaml"
        with open(os.path.join(memories_dir, agent_file), "w") as f:
            f.write("")
        return agent_file
    
    def write_agent_config(self, agent_config, config_data):
        with open(agent_config, "w") as f:
            json.dump(config_data, f)

    def add_agent(self, agent_name):
        agent_file = self.create_agent_yaml_file(agent_name)
        agent_folder = self.create_agent_folder(agent_name)
        agent_config = self.create_agent_config_file(agent_folder)
        commands_list = self.load_commands(agent_name)
        command_dict = {}
        for command in commands_list:
            friendly_name, command_name, command_args = command
            command_dict[friendly_name] = True
        self.write_agent_config(agent_config, {"commands": command_dict})
        return {"agent_file": agent_file}

    def rename_agent(self, agent_name, new_name):
        agent_file = f"agents/{agent_name}.yaml"
        agent_folder = f"agents/{agent_name}/"
        agent_file = os.path.abspath(agent_file)
        agent_folder = os.path.abspath(agent_folder)
        if os.path.exists(agent_file):
            os.rename(agent_file, os.path.join("agents", f"{new_name}.yaml"))
        if os.path.exists(agent_folder):
            os.rename(agent_folder, os.path.join("agents", f"{new_name}"))

    def delete_agent(self, agent_name):
        agent_file = f"agents/{agent_name}.yaml"
        agent_folder = f"agents/{agent_name}/"
        agent_file = os.path.abspath(agent_file)
        agent_folder = os.path.abspath(agent_folder)
        try:
            os.remove(agent_file)
        except FileNotFoundError:
            return {"message": f"Agent file {agent_file} not found."}, 404

        if os.path.exists(agent_folder):
            shutil.rmtree(agent_folder)

        return {"message": f"Agent {agent_name} deleted."}, 200

    def get_agents(self):
        memories_dir = "agents"
        agents = []
        for file in os.listdir(memories_dir):
            if file.endswith(".yaml"):
                agents.append(file.replace(".yaml", ""))
        # Check agent status and return {"agents": [{"name": "agent_name", "status": "running"}]
        output = []
        for agent in agents:
            try:
                agent_instance = self.agent_instances[agent]
                status = agent_instance.get_status()
            except:
                status = False
            output.append({"name": agent, "status": status})
        return output

    def get_chat_history(self, agent_name):
        with open(os.path.join("agents", f"{agent_name}.yaml"), "r") as f:
            chat_history = f.read()
        return chat_history

    def wipe_agent_memories(self, agent_name):
        agent_folder = f"agents/{agent_name}/"
        agent_folder = os.path.abspath(agent_folder)
        memories_folder = os.path.join(agent_folder, "memories")
        if os.path.exists(memories_folder):
            shutil.rmtree(memories_folder)