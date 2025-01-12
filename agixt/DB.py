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
    func,
)
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.dialects.postgresql import UUID
from cryptography.fernet import Fernet
from Globals import getenv

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
        LOGIN_URI = f"{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"
        DATABASE_URI = f"postgresql://{LOGIN_URI}"
    else:
        DATABASE_URI = f"sqlite:///{DATABASE_NAME}.db"
    engine = create_engine(DATABASE_URI, pool_size=40, max_overflow=-1)
    connection = engine.connect()
    Base = declarative_base()
except Exception as e:
    logging.error(f"Error connecting to database: {e}")
    Base = None
    engine = None


def get_session():
    Session = sessionmaker(bind=engine, autoflush=False)
    session = Session()
    return session


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
        ForeignKey("agent.id"),
        nullable=False,
    )
    conversation_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("conversation.id"),
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
        ForeignKey("extension.id"),
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
        response = ChainStepResponse(content=content, chain_step=self)
        session.add(response)
        session.commit()


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


class Extension(Base):
    __tablename__ = "extension"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True, default="")


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


def setup_default_roles():
    with get_session() as db:
        default_roles = [
            {"id": 1, "name": "tenant_admin", "friendly_name": "Tenant Admin"},
            {"id": 2, "name": "company_admin", "friendly_name": "Company Admin"},
            {"id": 3, "name": "user", "friendly_name": "User"},
        ]
        for role in default_roles:
            existing_role = db.query(UserRole).filter_by(id=role["id"]).first()
            if not existing_role:
                new_role = UserRole(**role)
                db.add(new_role)
        db.commit()


from sqlalchemy import text


def migrate_company_agent_name():
    """
    Migration function to add agent_name column to Company table.
    This should be run before the app starts.
    """
    try:
        session = get_session()
        connection = session.connection()

        # Check if the column exists
        if DATABASE_TYPE != "sqlite":
            exists_query = """
                SELECT EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name='company' AND column_name='agent_name'
                );
            """
        else:
            exists_query = """
                SELECT COUNT(*) 
                FROM pragma_table_info('Company') 
                WHERE name='agent_name';
            """

        result = connection.execute(text(exists_query))
        column_exists = result.scalar()

        if not column_exists:
            default_agent_name = getenv("AGENT_NAME")

            # Add the column with different syntax based on database type
            if DATABASE_TYPE != "sqlite":
                alter_query = f"""
                    ALTER TABLE "Company" 
                    ADD COLUMN agent_name VARCHAR(255) DEFAULT '{default_agent_name}';
                """
            else:
                alter_query = f"""
                    ALTER TABLE Company 
                    ADD COLUMN agent_name TEXT DEFAULT '{default_agent_name}';
                """

            connection.execute(text(alter_query))
            session.commit()
            logging.info("Successfully added agent_name column to Company table")
    except Exception as e:
        logging.error(f"Error during company agent_name migration: {e}")
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    import uvicorn

    if DATABASE_TYPE.lower().startswith("postgres"):
        logging.info("Connecting to database...")
        while True:
            try:
                connection = engine.connect()
                connection.close()
                break
            except Exception as e:
                logging.error(f"Error connecting to database: {e}")
                time.sleep(5)
    # Create any missing tables
    migrate_company_agent_name()
    Base.metadata.create_all(engine)
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
