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
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import text
from dotenv import load_dotenv

load_dotenv()


username = os.getenv("POSTGRES_USER", "postgres")
password = os.getenv("POSTGRES_PASSWORD", "postgres")
server = os.getenv("POSTGRES_SERVER", "localhost")
port = os.getenv("POSTGRES_PORT", "5432")
database_name = os.getenv("POSTGRES_DB", "postgres")
db_connected = True if os.getenv("DB_CONNECTED", "false").lower() == "true" else False
Base = declarative_base()
if db_connected:
    try:
        engine = create_engine(
            f"postgresql://{username}:{password}@{server}:{port}/{database_name}"
        )
    except Exception as e:
        print(f"Error connecting to database: {e}")
    Session = sessionmaker(bind=engine)
    session = Session()
    connection = engine.connect()
else:
    session = None


class Provider(Base):
    __tablename__ = "provider"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    provider_settings = relationship("ProviderSetting", backref="provider")


class ProviderSetting(Base):
    __tablename__ = "provider_setting"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("provider.id"), nullable=False)
    name = Column(Text, nullable=False)
    value = Column(
        Text
    )  # Add the 'value' column without the 'nullable=False' constraint


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
    settings = relationship("AgentProviderSetting", backref="agent_provider")


class Agent(Base):
    __tablename__ = "agent"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    provider_id = Column(
        UUID(as_uuid=True), ForeignKey("provider.id"), nullable=True, default=None
    )
    settings = relationship("AgentSetting", backref="agent")  # One-to-many relationship


class Command(Base):
    __tablename__ = "command"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    extension_id = Column(UUID(as_uuid=True), ForeignKey("extension.id"))
    extension = relationship("Extension", backref="commands")


class AgentCommand(Base):
    __tablename__ = "agent_command"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    command_id = Column(UUID(as_uuid=True), ForeignKey("command.id"), nullable=False)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agent.id"), nullable=False)
    state = Column(Boolean, nullable=False)
    command = relationship("Command")  # Add this line to define the relationship


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
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    extension_id = Column(UUID(as_uuid=True), ForeignKey("extension.id"))
    value = Column(Text)


class AgentSetting(Base):
    __tablename__ = "agent_setting"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agent.id"), nullable=False)
    name = Column(String)
    value = Column(String)


class Chain(Base):
    __tablename__ = "chain"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    steps = relationship(
        "ChainStep",
        backref="chain",
        cascade="all, delete",  # Add the cascade option for deleting steps
        passive_deletes=True,
        foreign_keys="ChainStep.chain_id",
    )
    target_steps = relationship(
        "ChainStep", backref="target_chain", foreign_keys="ChainStep.target_chain_id"
    )


class ChainStep(Base):
    __tablename__ = "chain_step"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chain_id = Column(
        UUID(as_uuid=True), ForeignKey("chain.id", ondelete="CASCADE"), nullable=False
    )
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agent.id"), nullable=False)
    prompt_type = Column(Text)  # Add the prompt_type field
    prompt = Column(Text)  # Add the prompt field
    target_chain_id = Column(
        UUID(as_uuid=True), ForeignKey("chain.id", ondelete="SET NULL")
    )
    target_command_id = Column(
        UUID(as_uuid=True), ForeignKey("command.id", ondelete="SET NULL")
    )
    target_prompt_id = Column(
        UUID(as_uuid=True), ForeignKey("prompt.id", ondelete="SET NULL")
    )
    step_number = Column(Integer, nullable=False)
    responses = relationship(
        "ChainStepResponse", backref="chain_step", cascade="all, delete"
    )

    def add_response(self, content):
        response = ChainStepResponse(content=content, chain_step=self)
        session.add(response)
        session.commit()


class ChainStepArgument(Base):
    __tablename__ = "chain_step_argument"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    argument_id = Column(UUID(as_uuid=True), ForeignKey("argument.id"), nullable=False)
    chain_step_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chain_step.id", ondelete="CASCADE"),
        nullable=False,  # Add the ondelete option
    )
    value = Column(Text, nullable=False)


class ChainStepResponse(Base):
    __tablename__ = "chain_step_response"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chain_step_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chain_step.id", ondelete="CASCADE"),
        nullable=False,  # Add the ondelete option
    )
    timestamp = Column(DateTime, server_default=text("now()"))
    content = Column(Text, nullable=False)


class Extension(Base):
    __tablename__ = "extension"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True, default="")


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


if __name__ == "__main__":
    Base.metadata.create_all(engine)
