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
from sqlalchemy.orm import sessionmaker
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
            print(f"Error connecting to PostgreSQL: {e}")
            print("Creating SQLite database...")
            try:
                engine = create_engine("sqlite:///agixt.db")
                engine.execute("SELECT 1")
                print("SQLite database created.")
            except Exception as e:
                print(f"Error creating SQLite database: {e}")
                raise e
        return engine

    def populate_extensions_and_commands(self):
        extensions_data = Extensions().get_extensions()

        # Delete existing data in Argument, Command, and Extension tables
        self.session.query(Argument).delete()
        self.session.query(Command).delete()
        self.session.query(Extension).delete()
        self.session.commit()

        # Insert extensions, commands, and command arguments
        for extension_data in extensions_data:
            extension_name = extension_data["extension_name"]
            description = extension_data["description"]
            extension = Extension(name=extension_name, description=description)
            self.session.add(extension)
            self.session.flush()

            commands = extension_data["commands"]

            for command in commands:
                if "friendly_name" not in command:
                    continue
                command_name = command["friendly_name"]
                cmd = Command(
                    extension_id=extension.id if extension else None,
                    name=command_name,
                )
                self.session.add(cmd)
                self.session.flush()
                if "command_args" not in command:
                    continue
                if command["command_args"]:
                    for arg, arg_type in command["command_args"].items():
                        command_arg = Argument(
                            command_id=cmd.id,
                            name=arg,
                        )
                        self.session.add(command_arg)
                        self.session.flush()
            self.session.commit()


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
    provider_id = Column(UUID(as_uuid=True), ForeignKey("provider.id"), nullable=False)


class Command(Base):
    __tablename__ = "command"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    extension_id = Column(UUID(as_uuid=True), ForeignKey("extension.id"))


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
    setting_id = Column(UUID(as_uuid=True), ForeignKey("setting.id"), nullable=False)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agent.id"), nullable=False)
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
    id = Column(UUID(as_uuid=True), primary_key=True)
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


Base.metadata.create_all(bind=engine)
db.populate_extensions_and_commands()
