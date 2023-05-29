import os
import yaml

CONFIG_FILE = "config.yaml"


class Cfig:
    def __init__(self):
        if not os.path.exists(CONFIG_FILE):
            self.create_config_file()

    def create_config_file(self):
        """
        Creates a default configuration file if it doesn't exist.
        """
        default_config = {"auth_setup": False, "auth_setup_config": None}

        with open(CONFIG_FILE, "w") as f:
            yaml.dump(default_config, f)

    def load_config(self):
        """
        Loads the configuration data from the config file.
        If the file doesn't exist, creates a default file and loads the data.
        Returns the loaded configuration data.
        """
        if not os.path.exists(CONFIG_FILE):
            self.create_config_file()

        with open(CONFIG_FILE, "r") as f:
            config = yaml.safe_load(f)

        return config

    def save_config(self, config):
        """
        Saves the configuration data to the config file.
        """
        with open(CONFIG_FILE, "w") as f:
            yaml.dump(config, f)

    def is_auth_setup_configured(self):
        """
        Checks if the admin configuration setup is already done.
        Returns True if configured, False otherwise.
        """
        config = self.load_config()
        return config["auth_setup"]

    def set_auth_setup_config(self, setup_config):
        """
        Sets the authentication setup configuration.
        """
        config = self.load_config()
        config["auth_setup_config"] = setup_config
        config["auth_setup"] = True
        self.save_config(config)

    def get_admin_email(self):
        config = self.load_config()
        if "admin_email" in config:
            return config["admin_email"]
        else:
            return False
