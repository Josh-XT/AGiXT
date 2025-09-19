import uuid
import time
import logging
from sqlalchemy import (
    create_engine,
    Column,
    Text,
    String,
    Integer,
    ForeignKey,
    DateTime,
    Boolean,
    event,
    or_,
    func,
    text,
)
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.types import TypeDecorator, VARCHAR
from sqlalchemy.sql.sqltypes import ARRAY, Float
from cryptography.fernet import Fernet
from Globals import getenv
import numpy as np


class ExtensionDatabaseMixin:
    """
    Mixin class for extensions that need database tables
    """

    extension_models = []  # Extensions should override this with their models
    _registered_models = set()  # Track which models have been logged
    _created_tables = set()  # Track which tables have been created

    @classmethod
    def register_models(cls):
        """Register extension models with SQLAlchemy"""
        if hasattr(cls, "extension_models"):
            for model in cls.extension_models:
                # Only log once per model to avoid spam
                if model.__tablename__ not in cls._registered_models:
                    cls._registered_models.add(model.__tablename__)

                # Create table if not already created
                if model.__tablename__ not in cls._created_tables:
                    try:
                        model.__table__.create(engine, checkfirst=True)
                        cls._created_tables.add(model.__tablename__)
                    except Exception as e:
                        # Check if error is about existing index - this is expected behavior
                        if "already exists" in str(e).lower():
                            logging.debug(
                                f"Table/index already exists for {model.__tablename__}: {e}"
                            )
                            cls._created_tables.add(model.__tablename__)
                        else:
                            logging.error(
                                f"Error creating table {model.__tablename__}: {e}"
                            )

    @classmethod
    def create_tables(cls):
        """Create database tables for this extension"""
        if hasattr(cls, "extension_models"):
            for model in cls.extension_models:
                if model.__tablename__ not in cls._created_tables:
                    try:
                        model.__table__.create(engine, checkfirst=True)
                        cls._created_tables.add(model.__tablename__)
                    except Exception as e:
                        # Check if error is about existing index - this is expected behavior
                        if "already exists" in str(e).lower():
                            logging.debug(
                                f"Table/index already exists for {model.__tablename__}: {e}"
                            )
                            cls._created_tables.add(model.__tablename__)
                        else:
                            logging.error(
                                f"Error creating table {model.__tablename__}: {e}"
                            )


logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)
DEFAULT_USER = getenv("DEFAULT_USER")
try:
    DATABASE_TYPE = getenv("DATABASE_TYPE")
    DATABASE_NAME = getenv("DATABASE_NAME")
    if DATABASE_TYPE != "sqlite":
        DATABASE_USER = getenv("DATABASE_USER")
        DATABASE_PASSWORD = getenv("DATABASE_PASSWORD")
        DATABASE_HOST = getenv("DATABASE_HOST")
        DATABASE_PORT = getenv("DATABASE_PORT")
        DATABASE_SSL = getenv("DATABASE_SSL", "disable")
        if DATABASE_SSL == "disable":
            LOGIN_URI = f"{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"
        else:
            LOGIN_URI = f"{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}?sslmode={DATABASE_SSL}"
        DATABASE_URI = f"postgresql://{LOGIN_URI}"
    else:
        import os

        if "/" in DATABASE_NAME:
            db_folder = os.path.dirname(DATABASE_NAME)
            if not os.path.exists(db_folder):
                os.makedirs(db_folder)
        DATABASE_URI = f"sqlite:///{DATABASE_NAME}.db"

    # Database connection pool settings with dynamic calculation
    # Get number of uvicorn workers
    UVICORN_WORKERS = int(getenv("UVICORN_WORKERS", "60"))

    # Allow customization via environment variables
    # Default to generous settings to prevent connection exhaustion
    DB_POOL_MULTIPLIER = float(
        getenv("DB_POOL_MULTIPLIER", "3")
    )  # 3 connections per worker
    DB_OVERFLOW_MULTIPLIER = float(getenv("DB_OVERFLOW_MULTIPLIER", "2"))  # 2x overflow

    # Calculate pool sizes dynamically based on worker count
    # This ensures we have enough connections for all workers plus overhead
    DB_POOL_SIZE = int(
        getenv("DB_POOL_SIZE", str(int(UVICORN_WORKERS * DB_POOL_MULTIPLIER)))
    )
    DB_MAX_OVERFLOW = int(
        getenv("DB_MAX_OVERFLOW", str(int(DB_POOL_SIZE * DB_OVERFLOW_MULTIPLIER)))
    )

    # Other pool settings
    DB_POOL_TIMEOUT = int(getenv("DB_POOL_TIMEOUT", "30"))
    DB_POOL_RECYCLE = int(getenv("DB_POOL_RECYCLE", "3600"))

    # Total connections available
    TOTAL_CONNECTIONS = DB_POOL_SIZE + DB_MAX_OVERFLOW

    # Warn if configuration seems insufficient
    if TOTAL_CONNECTIONS < UVICORN_WORKERS * 2:
        logging.warning(
            f"Database pool may be insufficient: {TOTAL_CONNECTIONS} total connections "
            f"for {UVICORN_WORKERS} workers. Consider increasing DB_POOL_MULTIPLIER or DB_POOL_SIZE."
        )

    engine = create_engine(
        DATABASE_URI,
        pool_size=DB_POOL_SIZE,
        max_overflow=DB_MAX_OVERFLOW,
        pool_timeout=DB_POOL_TIMEOUT,
        pool_recycle=DB_POOL_RECYCLE,
        pool_pre_ping=True,  # Verify connections before use
        echo=False,  # Set to True for SQL debugging
    )

    # Test connection immediately
    connection = engine.connect()
    connection.close()  # Close test connection
    Base = declarative_base()

except Exception as e:
    logging.error(f"Error connecting to database: {e}")
    Base = None
    engine = None


from contextlib import contextmanager


def get_session():
    Session = sessionmaker(bind=engine, autoflush=False)
    session = Session()
    return session


@contextmanager
def get_db_session():
    """Context manager for database sessions that ensures proper cleanup"""
    session = get_session()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        try:
            session.close()
        except Exception as e:
            logging.error(f"Error closing database session: {e}")


def get_new_id():
    return str(uuid.uuid4())


class UserRole(Base):
    __tablename__ = "Role"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    friendly_name = Column(String)


class Company(Base):
    __tablename__ = "Company"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    company_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String
    )  # Parent company reference
    name = Column(String)
    encryption_key = Column(String, nullable=False)
    token = Column(String, nullable=True)
    training_data = Column(String, nullable=True)
    agent_name = Column(String, nullable=True, default=getenv("AGENT_NAME"))
    status = Column(Boolean, nullable=True, default=True)
    address = Column(String, nullable=True, default=None)
    phone_number = Column(String, nullable=True, default=None)
    email = Column(String, nullable=True, default=None)
    website = Column(String, nullable=True, default=None)
    city = Column(String, nullable=True, default=None)
    state = Column(String, nullable=True, default=None)
    zip_code = Column(String, nullable=True, default=None)
    country = Column(String, nullable=True, default=None)
    notes = Column(Text, nullable=True, default=None)
    users = relationship("UserCompany", back_populates="company")

    @classmethod
    def create(cls, session, **kwargs):
        kwargs["encryption_key"] = Fernet.generate_key().decode()
        new_company = cls(**kwargs)
        session.add(new_company)
        session.flush()
        return new_company


class UserCompany(Base):
    __tablename__ = "UserCompany"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    user_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id"),
        nullable=False,
    )
    company_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("Company.id"),
        nullable=False,
    )
    role_id = Column(Integer, ForeignKey("Role.id"), nullable=False, server_default="3")

    user = relationship("User", back_populates="user_companys")
    company = relationship("Company", back_populates="users")
    role = relationship("UserRole")


class Invitation(Base):
    __tablename__ = "Invitation"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    email = Column(String, nullable=False)
    company_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("Company.id"),
    )
    role_id = Column(Integer, ForeignKey("Role.id"), nullable=False)
    inviter_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id"),
    )
    created_at = Column(DateTime, server_default=func.now())
    is_accepted = Column(Boolean, default=False)

    company = relationship("Company")
    role = relationship("UserRole")
    inviter = relationship("User")


class User(Base):
    __tablename__ = "user"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    email = Column(String, unique=True)
    first_name = Column(String, default="", nullable=True)
    last_name = Column(String, default="", nullable=True)
    admin = Column(Boolean, default=False, nullable=False)
    mfa_token = Column(String, default="", nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    is_active = Column(Boolean, default=True)
    user_companys = relationship("UserCompany", back_populates="user")


class UserPreferences(Base):
    __tablename__ = "user_preferences"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    user_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id"),
    )
    pref_key = Column(String, nullable=False)
    pref_value = Column(String, nullable=True)


class UserOAuth(Base):
    __tablename__ = "user_oauth"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    user_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id"),
    )
    user = relationship("User")
    provider_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("oauth_provider.id"),
    )
    provider = relationship("OAuthProvider")
    account_name = Column(String, nullable=False)
    access_token = Column(String, default="", nullable=False)
    refresh_token = Column(String, default="", nullable=False)
    token_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class OAuthProvider(Base):
    __tablename__ = "oauth_provider"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    name = Column(String, default="", nullable=False)


class FailedLogins(Base):
    __tablename__ = "failed_logins"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    user_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id"),
    )
    user = relationship("User")
    ip_address = Column(String, default="", nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class Provider(Base):
    __tablename__ = "provider"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    name = Column(Text, nullable=False)
    provider_settings = relationship("ProviderSetting", backref="provider")


class ProviderSetting(Base):
    __tablename__ = "provider_setting"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    provider_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("provider.id"),
        nullable=False,
    )
    name = Column(Text, nullable=False)
    value = Column(Text, nullable=True)


class AgentProviderSetting(Base):
    __tablename__ = "agent_provider_setting"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    provider_setting_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("provider_setting.id"),
        nullable=False,
    )
    agent_provider_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("agent_provider.id"),
        nullable=False,
    )
    value = Column(Text, nullable=True)


class AgentProvider(Base):
    __tablename__ = "agent_provider"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    provider_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("provider.id"),
        nullable=False,
    )
    agent_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("agent.id"),
        nullable=False,
    )
    settings = relationship("AgentProviderSetting", backref="agent_provider")


class AgentBrowsedLink(Base):
    __tablename__ = "agent_browsed_link"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    agent_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("agent.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("conversation.id", ondelete="CASCADE"),
        nullable=True,
    )
    link = Column(Text, nullable=False)
    timestamp = Column(DateTime, server_default=func.now())


class Agent(Base):
    __tablename__ = "agent"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    name = Column(Text, nullable=False)
    provider_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("provider.id"),
        nullable=True,
        default=None,
    )
    user_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id"),
        nullable=True,
    )
    settings = relationship("AgentSetting", backref="agent")  # One-to-many relationship
    browsed_links = relationship("AgentBrowsedLink", backref="agent")
    user = relationship("User", backref="agent")


class Command(Base):
    __tablename__ = "command"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    name = Column(Text, nullable=False)
    extension_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("extension.id", ondelete="CASCADE"),
    )
    extension = relationship("Extension", backref="commands")


class AgentCommand(Base):
    __tablename__ = "agent_command"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    command_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("command.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("agent.id"),
        nullable=False,
    )
    state = Column(Boolean, nullable=False)
    command = relationship("Command")  # Add this line to define the relationship


class Conversation(Base):
    __tablename__ = "conversation"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    name = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    attachment_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    user_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id"),
        nullable=True,
    )
    user = relationship("User", backref="conversation")


class Message(Base):
    __tablename__ = "message"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    role = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, server_default=func.now())
    conversation_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("conversation.id"),
        nullable=False,
    )
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id"),
        nullable=True,
    )
    feedback_received = Column(Boolean, default=False)
    notify = Column(Boolean, default=False, nullable=False)


class Setting(Base):
    __tablename__ = "setting"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    name = Column(Text, nullable=False)
    extension_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("extension.id"),
    )
    value = Column(Text)


class AgentSetting(Base):
    __tablename__ = "agent_setting"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    agent_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("agent.id"),
        nullable=False,
    )
    name = Column(String)
    value = Column(String)


class Chain(Base):
    __tablename__ = "chain"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    user_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id"),
        nullable=True,
    )
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
    user = relationship("User", backref="chain")
    runs = relationship("ChainRun", backref="chain", cascade="all, delete-orphan")


class ChainStep(Base):
    __tablename__ = "chain_step"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    chain_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("chain.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("agent.id"),
        nullable=False,
    )
    prompt_type = Column(Text)  # Add the prompt_type field
    prompt = Column(Text)  # Add the prompt field
    target_chain_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("chain.id", ondelete="SET NULL"),
    )
    target_command_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("command.id", ondelete="CASCADE"),
    )
    target_prompt_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("prompt.id", ondelete="SET NULL"),
    )
    step_number = Column(Integer, nullable=False)
    responses = relationship(
        "ChainStepResponse", backref="chain_step", cascade="all, delete"
    )

    def add_response(self, content):
        session = get_session()
        try:
            response = ChainStepResponse(content=content, chain_step=self)
            session.add(response)
            session.commit()
        finally:
            session.close()


class ChainStepArgument(Base):
    __tablename__ = "chain_step_argument"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    argument_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("argument.id"),
        nullable=False,
    )
    chain_step_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("chain_step.id", ondelete="CASCADE"),
        nullable=False,  # Add the ondelete option
    )
    value = Column(Text, nullable=True)


class ChainRun(Base):
    __tablename__ = "chain_run"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    chain_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("chain.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id"),
        nullable=True,
    )
    timestamp = Column(DateTime, server_default=func.now())
    chain_step_responses = relationship(
        "ChainStepResponse", backref="chain_run", cascade="all, delete-orphan"
    )


class ChainStepResponse(Base):
    __tablename__ = "chain_step_response"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    chain_step_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("chain_step.id", ondelete="CASCADE"),
        nullable=False,  # Add the ondelete option
    )
    chain_run_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("chain_run.id", ondelete="CASCADE"),
        nullable=True,
    )
    timestamp = Column(DateTime, server_default=func.now())
    content = Column(Text, nullable=False)


class ExtensionCategory(Base):
    __tablename__ = "extension_category"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    name = Column(Text, nullable=False, unique=True)
    description = Column(Text, nullable=True, default="")


class Extension(Base):
    __tablename__ = "extension"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True, default="")
    category_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("extension_category.id"),
        nullable=True,
    )
    category = relationship("ExtensionCategory", backref="extensions")


class Argument(Base):
    __tablename__ = "argument"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    prompt_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("prompt.id"),
    )
    command_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("command.id"),
    )
    chain_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("chain.id"),
    )
    name = Column(Text, nullable=False)


class PromptCategory(Base):
    __tablename__ = "prompt_category"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    user_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id"),
        nullable=True,
    )
    user = relationship("User", backref="prompt_category")


class TaskCategory(Base):
    __tablename__ = "task_category"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    user_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id"),
    )
    name = Column(String)
    description = Column(String)
    memory_collection = Column(String, default="0")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    category_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("task_category.id"),
        nullable=True,
    )
    parent_category = relationship("TaskCategory", remote_side=[id])
    user = relationship("User", backref="task_category")


class TaskItem(Base):
    __tablename__ = "task_item"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    user_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id"),
    )
    category_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("task_category.id"),
    )
    category = relationship("TaskCategory")
    title = Column(String)
    description = Column(String)
    memory_collection = Column(String, default="0")
    # agent_id is the action item owner. If it is null, it is an item for the user
    agent_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("agent.id"),
        nullable=True,
    )
    estimated_hours = Column(Integer)
    scheduled = Column(Boolean, default=False)
    completed = Column(Boolean, default=False)
    due_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime, nullable=True)
    priority = Column(Integer)
    user = relationship("User", backref="task_item")


class WebhookIncoming(Base):
    __tablename__ = "webhook_incoming"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    webhook_id = Column(String, unique=True, nullable=False)  # URL path identifier
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    agent_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("agent.id"),
        nullable=False,
    )
    user_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id"),
        nullable=False,
    )
    api_key = Column(String, nullable=False)  # For authentication
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    agent = relationship("Agent", backref="incoming_webhooks")
    user = relationship("User", backref="incoming_webhooks")


class WebhookOutgoing(Base):
    __tablename__ = "webhook_outgoing"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    user_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id"),
        nullable=False,
    )
    company_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("Company.id"),
        nullable=True,
    )
    agent_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("agent.id"),
        nullable=True,
    )
    event_types = Column(Text)  # JSON array stored as text
    target_url = Column(String, nullable=False)
    headers = Column(Text)  # JSON object stored as text
    secret = Column(String, nullable=True)  # Secret for HMAC signature verification
    retry_count = Column(Integer, default=3)
    retry_delay = Column(Integer, default=60)  # Seconds between retries
    timeout = Column(Integer, default=30)  # Request timeout in seconds
    active = Column(Boolean, default=True)
    filters = Column(Text)  # JSON object stored as text for event filters
    consecutive_failures = Column(Integer, default=0)
    total_events_sent = Column(Integer, default=0)
    successful_deliveries = Column(Integer, default=0)
    failed_deliveries = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", backref="outgoing_webhooks")
    company = relationship("Company", backref="outgoing_webhooks")
    agent = relationship("Agent", backref="outgoing_webhooks")


class WebhookLog(Base):
    __tablename__ = "webhook_log"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    webhook_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        nullable=False,
    )
    direction = Column(String, nullable=False)  # 'incoming' or 'outgoing'
    payload = Column(Text)  # JSON payload
    response = Column(Text, nullable=True)  # Response data
    status_code = Column(Integer, nullable=True)
    timestamp = Column(DateTime, server_default=func.now())
    retry_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)


class Prompt(Base):
    __tablename__ = "prompt"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    prompt_category_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("prompt_category.id"),
        nullable=False,
    )
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    user_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id"),
        nullable=True,
    )
    prompt_category = relationship("PromptCategory", backref="prompts")
    user = relationship("User", backref="prompt")
    arguments = relationship("Argument", backref="prompt", cascade="all, delete-orphan")


class Vector(TypeDecorator):
    """Unified vector storage for both SQLite and PostgreSQL"""

    impl = VARCHAR if DATABASE_TYPE == "sqlite" else ARRAY(Float)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Convert vector to storage format"""
        if value is None:
            return None

        # Convert to numpy array and ensure 1D
        if isinstance(value, np.ndarray):
            value = value.reshape(-1).tolist()
        elif isinstance(value, list):
            # Handle nested lists
            value = np.array(value).reshape(-1).tolist()

        # For SQLite, store as string representation
        if DATABASE_TYPE == "sqlite":
            return f'[{",".join(map(str, value))}]'

        # For PostgreSQL, return as list
        return value

    def process_result_value(self, value, dialect):
        """Convert from storage format to numpy array"""
        if value is None:
            return None

        # For SQLite, parse string representation
        if DATABASE_TYPE == "sqlite":
            try:
                value = eval(value)
            except:
                return None

        # Convert to 1D numpy array
        return np.array(value).reshape(-1)


# Update the embedding function to ensure consistent output shape
def process_embedding_for_storage(embedding):
    """Ensure embedding is in the correct format for storage"""
    if embedding is None:
        return None

    # Convert to numpy array and ensure 1D
    if isinstance(embedding, list) or isinstance(embedding, np.ndarray):
        return np.array(embedding).reshape(-1)

    return None


class TokenBlacklist(Base):
    __tablename__ = "token_blacklist"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    token = Column(String, nullable=False, unique=True)
    user_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id"),
        nullable=False,
    )
    blacklisted_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime, nullable=False)  # JWT expiration time

    # Relationships
    user = relationship("User", backref="blacklisted_tokens")


class Memory(Base):
    __tablename__ = "memory"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    agent_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("agent.id"),
        nullable=False,
    )
    conversation_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("conversation.id"),
        nullable=True,  # Null for core memories (collection "0")
    )
    embedding = Column(Vector)
    text = Column(Text, nullable=False)
    external_source = Column(String, default="user input")
    description = Column(Text)
    timestamp = Column(DateTime, server_default=func.now())
    additional_metadata = Column(Text)

    # Relationships
    agent = relationship("Agent", backref="memories")
    conversation = relationship("Conversation", backref="memories")

    def __init__(self, **kwargs):
        if "agent_id" not in kwargs or not kwargs["agent_id"]:
            raise ValueError("agent_id is required")
        super().__init__(**kwargs)


@event.listens_for(Memory.__table__, "after_create")
def setup_vector_column(target, connection, **kw):
    try:
        # Create basic indices that will be useful for both databases
        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS memory_agent_conv_idx 
                ON memory (agent_id, conversation_id);
                """
            )
        )
    except Exception as e:
        logging.error(f"Error setting up memory indices: {e}")


def calculate_vector_similarity(query_embedding, stored_embedding):
    """Calculate cosine similarity between two vectors"""
    if query_embedding is None or stored_embedding is None:
        return 0.0

    try:
        # Convert inputs to numpy arrays if they aren't already
        if not isinstance(query_embedding, np.ndarray):
            query_embedding = np.array(query_embedding)
        if not isinstance(stored_embedding, np.ndarray):
            stored_embedding = np.array(stored_embedding)

        # Ensure vectors are 1D and have the same shape
        query_embedding = query_embedding.reshape(-1)  # Flatten to 1D
        stored_embedding = stored_embedding.reshape(-1)  # Flatten to 1D

        # Verify shapes match
        if query_embedding.shape != stored_embedding.shape:
            logging.warning(
                f"Vector shape mismatch: {query_embedding.shape} vs {stored_embedding.shape}"
            )
            return 0.0

        # Calculate cosine similarity
        dot_product = np.dot(query_embedding, stored_embedding)
        query_norm = np.linalg.norm(query_embedding)
        stored_norm = np.linalg.norm(stored_embedding)

        if query_norm == 0 or stored_norm == 0:
            return 0.0

        return float(dot_product / (query_norm * stored_norm))

    except Exception as e:
        logging.error(f"Error calculating vector similarity: {e}")
        return 0.0


# Update the memory search query for both databases:
def get_similar_memories(
    session, query_embedding, agent_id, conversation_id, limit, min_score
):
    """Get similar memories using basic SQL and Python-based similarity calculation"""
    try:
        # Get all potentially relevant memories
        memories = (
            session.query(Memory)
            .filter(
                Memory.agent_id == agent_id,
                or_(
                    Memory.conversation_id == conversation_id,
                    Memory.conversation_id == None,
                ),
            )
            .all()
        )

        # Calculate similarities
        memory_scores = [
            (mem, calculate_vector_similarity(query_embedding, mem.embedding))
            for mem in memories
        ]

        # Filter by minimum score and sort by similarity
        filtered_memories = [
            (mem, score) for mem, score in memory_scores if score >= min_score
        ]
        filtered_memories.sort(key=lambda x: x[1], reverse=True)

        # Return top N results
        return filtered_memories[:limit]

    except Exception as e:
        logging.error(f"Error in memory search: {e}")
        return []


default_roles = [
    {"id": 1, "name": "tenant_admin", "friendly_name": "Tenant Admin"},
    {"id": 2, "name": "company_admin", "friendly_name": "Company Admin"},
    {"id": 3, "name": "user", "friendly_name": "User"},
    {"id": 4, "name": "child", "friendly_name": "Child"},
]

default_extension_categories = [
    {
        "name": "Core Abilities",
        "description": "Essential artificial intelligence abilities like workspace file management, data analysis, note taking, and more",
    },
    {
        "name": "Social & Communication",
        "description": "Connect to social media platforms, messaging apps, and email services",
    },
    {
        "name": "Productivity",
        "description": "Integrate with business tools, email, calendar, project management, and productivity apps",
    },
    {
        "name": "Development & Code",
        "description": "GitHub integration, code analysis, and software development tools",
    },
    {
        "name": "Data & Databases",
        "description": "Connect to databases, analyze data, and manage information",
    },
    {
        "name": "Smart Home & IoT",
        "description": "Control smart home devices, security cameras, and IoT systems",
    },
    {
        "name": "Robotics",
        "description": "Control robots, drones, and autonomous vehicles",
    },
    {
        "name": "Health & Fitness",
        "description": "Track health metrics, fitness data, and wellness information",
    },
    {
        "name": "Finance & Crypto",
        "description": "Manage cryptocurrencies, trading, and financial operations",
    },
    {
        "name": "E-commerce & Shopping",
        "description": "Integrate with online marketplaces and shopping platforms",
    },
    {
        "name": "Entertainment & Media",
        "description": "Create and manipulate media content, games, and entertainment",
    },
]


def migrate_company_table():
    """
    Migration function to add new optional fields to the Company table if they don't exist.
    This should be run before setup_default_roles().

    Note: For new installations, the SQLAlchemy model already includes all columns,
    so this migration will typically be skipped.
    """
    return


def migrate_extension_table():
    """
    Migration function to add category_id field to the Extension table if it doesn't exist.
    """
    if engine is None:
        return

    try:
        with get_db_session() as session:
            # Check if category_id column exists
            if DATABASE_TYPE == "sqlite":
                # For SQLite, check if column exists
                result = session.execute(text("PRAGMA table_info(extension)"))
                columns = [row[1] for row in result.fetchall()]

                if "category_id" not in columns:
                    logging.info(
                        "Adding category_id column to extension table (SQLite)"
                    )
                    session.execute(
                        text("ALTER TABLE extension ADD COLUMN category_id TEXT")
                    )
                    session.commit()
            else:
                # For PostgreSQL, check if column exists
                result = session.execute(
                    text(
                        """
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name = 'extension' AND column_name = 'category_id'
                    """
                    )
                )

                if not result.fetchone():
                    logging.info(
                        "Adding category_id column to extension table (PostgreSQL)"
                    )
                    session.execute(
                        text("ALTER TABLE extension ADD COLUMN category_id UUID")
                    )
                    session.commit()

    except Exception as e:
        logging.debug(f"Extension table migration completed or not needed: {e}")


def migrate_webhook_outgoing_table():
    """
    Migration function to add missing fields to the WebhookOutgoing table if they don't exist.

    Note: For new installations, the SQLAlchemy model already includes all columns,
    so this migration will typically be skipped.
    """
    return


def discover_extension_models():
    """
    Discover and register all extension models
    """
    import importlib
    import glob
    import os

    extension_models = []
    command_files = glob.glob("extensions/*.py")

    for command_file in command_files:
        module_name = os.path.splitext(os.path.basename(command_file))[0]
        try:
            module = importlib.import_module(f"extensions.{module_name}")

            # Check if the module has any classes that inherit from ExtensionDatabaseMixin
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, ExtensionDatabaseMixin):
                    if attr is not ExtensionDatabaseMixin and hasattr(
                        attr, "extension_models"
                    ):
                        extension_models.extend(attr.extension_models)
        except Exception as e:
            logging.debug(
                f"Could not import extension {module_name} for model discovery: {e}"
            )

    return extension_models


def initialize_extension_tables():
    """
    Initialize all extension database tables
    """
    models = discover_extension_models()
    for model in models:
        # Check if table has already been created by ExtensionDatabaseMixin
        if model.__tablename__ not in ExtensionDatabaseMixin._created_tables:
            try:
                model.__table__.create(engine, checkfirst=True)
                ExtensionDatabaseMixin._created_tables.add(model.__tablename__)
            except Exception as e:
                # Check if error is about existing index - this is expected behavior
                if "already exists" in str(e).lower():
                    logging.debug(
                        f"Table/index already exists for {model.__tablename__}: {e}"
                    )
                    ExtensionDatabaseMixin._created_tables.add(model.__tablename__)
                else:
                    logging.error(
                        f"Error creating extension table {model.__tablename__}: {e}"
                    )
        else:
            logging.debug(f"Table {model.__tablename__} already created, skipping")


def setup_default_extension_categories():
    """Setup default extension categories"""
    try:
        with get_db_session() as session:
            for category_data in default_extension_categories:
                existing_category = (
                    session.query(ExtensionCategory)
                    .filter_by(name=category_data["name"])
                    .first()
                )
                if not existing_category:
                    new_category = ExtensionCategory(**category_data)
                    session.add(new_category)
            session.commit()
    except Exception as e:
        logging.error(f"Error setting up default extension categories: {e}")


def migrate_extensions_to_new_categories():
    """Migrate existing extensions to use the new category mapping"""
    try:
        with get_db_session() as session:
            # Mapping from extension names to new categories
            extension_category_mapping = {
                # Core Abilities
                "Ai": "Core Abilities",
                "Essential Abilities": "Core Abilities",
                # Web & Search
                "Web Browsing": "Web & Search",
                "Google Search": "Web & Search",
                # Social & Communication
                "Discord": "Social & Communication",
                "Sendgrid Email": "Social & Communication",
                "Microsoft": "Social & Communication",
                "X": "Social & Communication",
                # Productivity
                "Notes": "Productivity",
                "Automation Helpers": "Productivity",
                "Walmart": "Productivity",
                "Meta Ads": "Productivity",
                "Google": "Productivity",
                # Development & Code
                "Github": "Development & Code",
                "Graphql Server": "Development & Code",
                "Microcontroller Development": "Development & Code",
                # Data & Databases
                "Postgres Database": "Data & Databases",
                "Mysql Database": "Data & Databases",
                "Mssql Database": "Data & Databases",
                # Smart Home & IoT
                "Ring": "Smart Home & IoT",
                "Blink": "Smart Home & IoT",
                "Axis Camera": "Smart Home & IoT",
                "Hikvision": "Smart Home & IoT",
                "Vivotek": "Smart Home & IoT",
                "Roomba": "Smart Home & IoT",
                "Dji Tello": "Smart Home & IoT",
                "Tesla": "Smart Home & IoT",
                "Alexa": "Smart Home & IoT",
                # Health & Fitness
                "Fitbit": "Health & Fitness",
                "Garmin": "Health & Fitness",
                "Oura": "Health & Fitness",
                "Workout Tracker": "Health & Fitness",
                # Finance & Crypto
                "Solana Wallet": "Finance & Crypto",
                "Raydium Integration": "Finance & Crypto",
                "Bags Fm": "Finance & Crypto",
                # E-commerce & Shopping
                "Amazon": "E-commerce & Shopping",
            }

            # Get all extensions and update their categories
            extensions = session.query(Extension).all()
            for extension in extensions:
                if extension.name in extension_category_mapping:
                    new_category_name = extension_category_mapping[extension.name]
                    new_category = (
                        session.query(ExtensionCategory)
                        .filter_by(name=new_category_name)
                        .first()
                    )
                    if new_category:
                        extension.category_id = new_category.id
                        logging.info(
                            f"Updated extension '{extension.name}' to category '{new_category_name}'"
                        )
                    else:
                        logging.warning(
                            f"Category '{new_category_name}' not found for extension '{extension.name}'"
                        )
                else:
                    # Default to Productivity for unmapped extensions
                    default_category = (
                        session.query(ExtensionCategory)
                        .filter_by(name="Productivity")
                        .first()
                    )
                    if default_category:
                        extension.category_id = default_category.id
                        logging.info(
                            f"Updated extension '{extension.name}' to default category 'Productivity'"
                        )

            session.commit()
            logging.info("Successfully migrated extensions to new categories")
    except Exception as e:
        logging.error(f"Error migrating extensions to new categories: {e}")


def setup_default_roles():
    with get_session() as db:
        for role in default_roles:
            existing_role = db.query(UserRole).filter_by(id=role["id"]).first()
            if not existing_role:
                new_role = UserRole(**role)
                db.add(new_role)
        db.commit()


if __name__ == "__main__":
    import uvicorn

    if DATABASE_TYPE != "sqlite":
        logging.info("Connecting to database...")
        while True:
            try:
                connection = engine.connect()
                connection.close()
                break
            except Exception as e:
                logging.error(f"Error connecting to database: {e}")
                time.sleep(5)
    Base.metadata.create_all(engine)
    # Initialize extension tables after core tables
    initialize_extension_tables()
    migrate_company_table()
    migrate_extension_table()
    migrate_webhook_outgoing_table()
    setup_default_extension_categories()
    setup_default_roles()
    seed_data = str(getenv("SEED_DATA")).lower() == "true"
    if seed_data:
        # Import seed data
        from SeedImports import import_all_data

        import_all_data()
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=7437,
        log_level=str(getenv("LOG_LEVEL")).lower(),
        workers=int(getenv("UVICORN_WORKERS")),
        proxy_headers=True,
    )
