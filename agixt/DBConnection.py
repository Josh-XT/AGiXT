import os
import uuid
from sqlalchemy import (
    create_engine,
    Column,
    Text,
    String,
    Integer,
    ForeignKey,
    DateTime,
    Boolean,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import text
from Extensions import Extensions
from dotenv import load_dotenv

load_dotenv()


class DBConnection:
    def __init__(self):
        self.username = os.getenv("POSTGRES_USER", "postgres")
        self.password = os.getenv("POSTGRES_PASSWORD", "postgres")
        self.server = os.getenv("POSTGRES_SERVER", "localhost")
        self.port = os.getenv("POSTGRES_PORT", "5432")
        self.database_name = os.getenv("POSTGRES_DB", "postgres")
        self.engine = self.get_engine()
        self.Base = declarative_base(bind=self.engine)
        self.Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()
        self.connection = self.engine.connect()

    def get_engine(self):
        try:
            engine = create_engine(
                f"postgresql://{self.username}:{self.password}@{self.server}:{self.port}/{self.database_name}"
            )
            engine.execute("SELECT 1")
        except Exception as e:
            print(f"Error connecting to database: {e}")
            print("Creating database...")
            try:
                engine = create_engine(
                    f"postgresql://{self.username}:{self.password}@{self.server}:{self.port}/{self.database_name}"
                )
                engine.execute(f"CREATE DATABASE {self.database_name}")
            except Exception as e:
                print(f"Error creating database: {e}")
                raise e
        return engine

    def populate_extensions_and_commands(self):
        extensions_data = Extensions().get_extensions()

        # Get the existing extensions and commands from the database
        existing_extensions = session.query(Extension).all()
        existing_commands = session.query(Command).all()

        # Delete commands that don't exist in the extensions data
        for command in existing_commands:
            command_exists = any(
                extension_data["extension_name"] == command.extension.name
                and any(
                    cmd["friendly_name"] == command.name
                    for cmd in extension_data["commands"]
                )
                for extension_data in extensions_data
            )
            if not command_exists:
                session.delete(command)

        # Add new extensions and commands, and update existing commands
        for extension_data in extensions_data:
            extension_name = extension_data["extension_name"]
            description = extension_data["description"]

            # Find the existing extension or create a new one
            extension = next(
                (ext for ext in existing_extensions if ext.name == extension_name),
                None,
            )
            if extension is None:
                extension = Extension(name=extension_name, description=description)
                session.add(extension)
                session.flush()
                existing_extensions.append(extension)

            commands = extension_data["commands"]

            for command_data in commands:
                if "friendly_name" not in command_data:
                    continue

                command_name = command_data["friendly_name"]

                # Find the existing command or create a new one
                command = next(
                    (
                        cmd
                        for cmd in existing_commands
                        if cmd.extension_id == extension.id and cmd.name == command_name
                    ),
                    None,
                )
                if command is None:
                    command = Command(
                        extension_id=extension.id,
                        name=command_name,
                    )
                    session.add(command)
                    session.flush()
                    existing_commands.append(command)

                # Delete existing arguments of the command
                session.query(Argument).filter(
                    Argument.command_id == command.id
                ).delete()

                # Add command arguments
                if "command_args" in command_data:
                    command_args = command_data["command_args"]
                    print(
                        f"Adding command arguments: {command_args} for {command_name}"
                    )
                    for arg, arg_type in command_args.items():
                        command_arg = Argument(
                            command_id=command.id,
                            name=arg,
                        )
                        session.add(command_arg)

        session.commit()

    def populate_prompts(self):
        # Add default category if it doesn't exist
        default_category = (
            self.session.query(PromptCategory).filter_by(name="Default").first()
        )

        if not default_category:
            default_category = PromptCategory(
                name="Default", description="Default category"
            )
            self.session.add(default_category)
            self.session.commit()

        # Get all prompt files in the specified folder
        for root, dirs, files in os.walk("prompts"):
            for file in files:
                prompt_category = None
                if root != "prompts":
                    # Use subfolder name as the prompt category
                    category_name = os.path.basename(root)
                    prompt_category = (
                        self.session.query(PromptCategory)
                        .filter_by(name=category_name)
                        .first()
                    )
                    if not prompt_category:
                        prompt_category = PromptCategory(
                            name=category_name, description=f"{category_name} category"
                        )
                        self.session.add(prompt_category)
                        self.session.commit()
                else:
                    # Assign to "Uncategorized" category if prompt is in the root folder
                    prompt_category = default_category

                # Read the prompt content from the file
                with open(os.path.join(root, file), "r") as f:
                    prompt_content = f.read()

                # Check if prompt with the same name and category already exists
                prompt_name = os.path.splitext(file)[0]
                existing_prompt = (
                    self.session.query(Prompt)
                    .filter_by(name=prompt_name, prompt_category=prompt_category)
                    .first()
                )
                if not existing_prompt:
                    # Create the prompt entry in the database
                    prompt = Prompt(
                        name=prompt_name,
                        description="",
                        content=prompt_content,
                        prompt_category=prompt_category,
                    )
                    self.session.add(prompt)
                    self.session.commit()

                    # Populate prompt arguments
                    prompt_args = self.get_prompt_args(prompt_content)
                    print(f"Adding prompt arguments: {prompt_args} for {prompt_name}")
                    for arg in prompt_args:
                        argument = Argument(
                            prompt_id=prompt.id,
                            name=arg,
                        )
                        self.session.add(argument)
                    self.session.commit()

    def get_prompt_args(self, prompt_text):
        # Find anything in the file between { and } and add them to a list to return
        prompt_vars = []
        for word in prompt_text.split():
            if word.startswith("{") and word.endswith("}"):
                prompt_vars.append(word[1:-1])
        return prompt_vars


db = DBConnection()

Base = db.Base
engine = db.engine
session = db.session


class Provider(Base):
    __tablename__ = "provider"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)


class ProviderSetting(Base):
    __tablename__ = "provider_setting"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("provider.id"), nullable=False)
    name = Column(Text, nullable=False)


class AgentProviderSetting(Base):
    __tablename__ = "agent_provider_setting"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_setting_id = Column(
        UUID(as_uuid=True), ForeignKey("provider_setting.id"), nullable=False
    )
    agent_provider_id = Column(
        UUID(as_uuid=True), ForeignKey("agent_provider.id"), nullable=False
    )
    value = Column(Text, nullable=False)


class AgentProvider(Base):
    __tablename__ = "agent_provider"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("provider.id"), nullable=False)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agent.id"), nullable=False)


class Agent(Base):
    __tablename__ = "agent"
    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(Text, nullable=False)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("provider.id"), nullable=True)


class Command(Base):
    __tablename__ = "command"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    extension_id = Column(UUID(as_uuid=True), ForeignKey("extension.id"))
    extension = relationship("Extension", backref="commands")


class AgentCommand(Base):
    __tablename__ = "agent_command"
    id = Column(UUID(as_uuid=True), primary_key=True)
    command_id = Column(UUID(as_uuid=True), ForeignKey("command.id"), nullable=False)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agent.id"), nullable=False)
    state = Column(Boolean, nullable=False)


class Conversation(Base):
    __tablename__ = "conversation"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agent.id"), nullable=False)
    name = Column(Text, nullable=False)


class Message(Base):
    __tablename__ = "message"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, server_default=text("now()"))
    conversation_id = Column(
        UUID(as_uuid=True), ForeignKey("conversation.id"), nullable=False
    )


class Setting(Base):
    __tablename__ = "setting"
    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(Text, nullable=False)
    extension_id = Column(UUID(as_uuid=True), ForeignKey("extension.id"))


class AgentSetting(Base):
    __tablename__ = "agent_setting"
    id = Column(UUID(as_uuid=True), primary_key=True)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agent.id"), nullable=False)
    name = Column(Text, nullable=False)
    value = Column(String, nullable=False)


class Chain(Base):
    __tablename__ = "chain"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=False)


class ChainStep(Base):
    __tablename__ = "chain_step"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chain_id = Column(UUID(as_uuid=True), ForeignKey("chain.id"), nullable=False)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agent.id"), nullable=False)
    target_chain_id = Column(UUID(as_uuid=True), ForeignKey("chain.id"))
    target_command_id = Column(UUID(as_uuid=True), ForeignKey("command.id"))
    target_prompt_id = Column(UUID(as_uuid=True), ForeignKey("prompt.id"))
    step_number = Column(Integer, nullable=False)
    responses = relationship("ChainStepResponse", backref="chain_step")

    def add_response(self, content):
        response = ChainStepResponse(content=content, chain_step=self)
        session.add(response)
        session.commit()


class ChainStepArgument(Base):
    __tablename__ = "chain_step_argument"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    argument_id = Column(UUID(as_uuid=True), ForeignKey("argument.id"), nullable=False)
    chain_step_id = Column(
        UUID(as_uuid=True), ForeignKey("chain_step.id"), nullable=False
    )
    value = Column(Text, nullable=False)


class ChainStepResponse(Base):
    __tablename__ = "chain_step_response"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chain_step_id = Column(
        UUID(as_uuid=True), ForeignKey("chain_step.id"), nullable=False
    )
    timestamp = Column(DateTime, server_default=text("now()"))
    content = Column(Text, nullable=False)


class Extension(Base):
    __tablename__ = "extension"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=False)


class Argument(Base):
    __tablename__ = "argument"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prompt_id = Column(UUID(as_uuid=True), ForeignKey("prompt.id"))
    command_id = Column(UUID(as_uuid=True), ForeignKey("command.id"))
    chain_id = Column(UUID(as_uuid=True), ForeignKey("chain.id"))
    name = Column(Text, nullable=False)


class PromptCategory(Base):
    __tablename__ = "prompt_category"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=False)


class Prompt(Base):
    __tablename__ = "prompt"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prompt_category_id = Column(
        UUID(as_uuid=True), ForeignKey("prompt_category.id"), nullable=False
    )
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    content = Column(Text, nullable=False)

    prompt_category = relationship("PromptCategory", backref="prompts")


Base.metadata.create_all(bind=engine)
db.populate_extensions_and_commands()
db.populate_prompts()
