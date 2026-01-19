import uuid
import time
import logging
import os
import json
from datetime import datetime
from sqlalchemy import (
    create_engine,
    Column,
    Text,
    String,
    Integer,
    ForeignKey,
    DateTime,
    Boolean,
    LargeBinary,
    Index,
    event,
    or_,
    func,
    text,
    UniqueConstraint,
    inspect,
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

    # SQLite requires different settings than PostgreSQL
    if DATABASE_TYPE == "sqlite":
        # SQLite doesn't support connection pooling the same way as PostgreSQL
        # Use NullPool to ensure each request gets a fresh connection
        # This is critical for multi-worker scenarios where different workers
        # need to see the latest database state
        from sqlalchemy.pool import NullPool

        engine = create_engine(
            DATABASE_URI,
            connect_args={
                "check_same_thread": False,
                "timeout": 30,  # Wait up to 30 seconds for locks
            },
            poolclass=NullPool,  # Create new connection for each request, no pooling
            echo=False,
        )

        # Configure SQLite for better concurrency
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            # Use DELETE mode instead of WAL for simpler multi-process consistency
            # WAL mode can cause read/write visibility issues with multiple processes
            cursor.execute("PRAGMA journal_mode=DELETE")
            # Synchronous FULL ensures data is written to disk before continuing
            cursor.execute("PRAGMA synchronous=FULL")
            # Enable foreign keys
            cursor.execute("PRAGMA foreign_keys=ON")
            # Set busy timeout to 30 seconds (in milliseconds)
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

    else:
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
    display_order = Column(
        Integer, default=100
    )  # For UI ordering, lower = higher in list


class Scope(Base):
    """
    Defines granular permissions that can be assigned to roles.
    Scopes follow the pattern: resource:action (e.g., 'agents:read', 'extensions:write')
    """

    __tablename__ = "Scope"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    name = Column(String, nullable=False, unique=True)  # e.g., 'agents:read'
    resource = Column(
        String, nullable=False
    )  # e.g., 'agents', 'extensions', 'conversations'
    action = Column(
        String, nullable=False
    )  # e.g., 'read', 'write', 'delete', 'execute'
    description = Column(String, nullable=True)
    category = Column(
        String, nullable=True
    )  # For grouping in UI: 'Core', 'Extensions', 'Admin', etc.
    is_system = Column(Boolean, default=True)  # System scopes can't be deleted


class CustomRole(Base):
    """
    Custom roles created by company admins with specific scope assignments.
    These extend the default roles with company-specific permissions.
    """

    __tablename__ = "CustomRole"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    company_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("Company.id"),
        nullable=False,
    )
    name = Column(String, nullable=False)  # Internal name (e.g., 'support_agent')
    friendly_name = Column(
        String, nullable=False
    )  # Display name (e.g., 'Support Agent')
    description = Column(String, nullable=True)
    priority = Column(Integer, default=100)  # Lower = more privileged (like role_id)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    company = relationship("Company", backref="custom_roles")
    scopes = relationship(
        "CustomRoleScope", back_populates="custom_role", cascade="all, delete-orphan"
    )


class CustomRoleScope(Base):
    """
    Junction table linking custom roles to their assigned scopes.
    """

    __tablename__ = "CustomRoleScope"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    custom_role_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("CustomRole.id", ondelete="CASCADE"),
        nullable=False,
    )
    scope_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("Scope.id", ondelete="CASCADE"),
        nullable=False,
    )

    custom_role = relationship("CustomRole", back_populates="scopes")
    scope = relationship("Scope")


class DefaultRoleScope(Base):
    """
    Defines which scopes are assigned to default system roles (super_admin, tenant_admin, etc.).
    This allows the system to know what permissions each default role level has.
    """

    __tablename__ = "DefaultRoleScope"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    role_id = Column(Integer, ForeignKey("Role.id"), nullable=False)
    scope_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("Scope.id", ondelete="CASCADE"),
        nullable=False,
    )

    role = relationship("UserRole")
    scope = relationship("Scope")


class UserCustomRole(Base):
    """
    Assigns custom roles to users within a company.
    Users can have multiple custom roles in addition to their base role_id.
    """

    __tablename__ = "UserCustomRole"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    user_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("Company.id", ondelete="CASCADE"),
        nullable=False,
    )
    custom_role_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("CustomRole.id", ondelete="CASCADE"),
        nullable=False,
    )
    assigned_at = Column(DateTime, server_default=func.now())
    assigned_by = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id"),
        nullable=True,
    )

    user = relationship("User", foreign_keys=[user_id])
    company = relationship("Company")
    custom_role = relationship("CustomRole")
    assigner = relationship("User", foreign_keys=[assigned_by])


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
    user_limit = Column(Integer, nullable=True, default=1)
    # Token-based billing fields
    token_balance = Column(Integer, nullable=False, default=0)  # Tokens remaining
    token_balance_usd = Column(Float, nullable=False, default=0.0)  # USD value
    tokens_used_total = Column(Integer, nullable=False, default=0)  # Lifetime usage
    last_low_balance_warning = Column(
        Integer, nullable=True
    )  # Last balance when warning shown
    # Auto top-up subscription fields
    auto_topup_enabled = Column(Boolean, nullable=False, default=False)
    auto_topup_amount_usd = Column(
        Float, nullable=True, default=None
    )  # Monthly top-up amount in USD
    stripe_customer_id = Column(
        String, nullable=True, default=None
    )  # Stripe customer ID for company
    stripe_subscription_id = Column(
        String, nullable=True, default=None
    )  # Active subscription ID
    # Per-app billing tracking
    app_name = Column(
        String, nullable=True, default=None
    )  # The app the company is subscribed to (e.g., "XT Systems", "NurseXT")
    last_subscription_billing_date = Column(
        DateTime, nullable=True, default=None
    )  # Last date subscription was billed
    # Trial credits tracking
    trial_credits_granted = Column(
        Float, nullable=True, default=None
    )  # USD value of trial credits granted
    trial_credits_granted_at = Column(
        DateTime, nullable=True, default=None
    )  # When trial credits were granted
    trial_domain = Column(
        String, nullable=True, default=None
    )  # The email domain that qualified for trial credits
    users = relationship("UserCompany", back_populates="company")

    @classmethod
    def create(cls, session, **kwargs):
        kwargs["encryption_key"] = Fernet.generate_key().decode()
        new_company = cls(**kwargs)
        session.add(new_company)
        session.flush()
        return new_company


class CompanyTokenUsage(Base):
    """Audit trail for token usage by users within a company"""

    __tablename__ = "CompanyTokenUsage"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    company_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("Company.id"),
        nullable=False,
    )
    user_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id"),
        nullable=False,
    )
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    timestamp = Column(DateTime, nullable=False, default=datetime.now)


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
    tos_accepted_at = Column(DateTime, nullable=True)
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


class ResponseCache(Base):
    """
    Database-backed response cache for sharing cached responses across all workers.

    This table stores cached API responses with automatic TTL expiration.
    Using the database instead of in-memory caching allows all uvicorn workers
    to share the same cache, eliminating redundant API calls and database queries.

    The cache is keyed by user_id + cache_key (hash of path + query string).
    """

    __tablename__ = "response_cache"

    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    # User ID for per-user cache isolation
    user_id = Column(String, nullable=False, index=True)
    # Hash of path + query string
    cache_key = Column(String, nullable=False, index=True)
    # Original path (for debugging/monitoring)
    path = Column(String, nullable=False)
    # Cached response body (compressed with zlib for efficiency)
    response_body = Column(LargeBinary, nullable=False)
    # Content type of the response
    content_type = Column(String, default="application/json")
    # HTTP status code
    status_code = Column(Integer, default=200)
    # When this cache entry was created
    created_at = Column(DateTime, server_default=func.now(), index=True)
    # When this entry expires (for efficient cleanup queries)
    expires_at = Column(DateTime, nullable=False, index=True)

    # Composite unique constraint: one cache entry per user+key
    __table_args__ = (
        Index("ix_response_cache_user_key", "user_id", "cache_key", unique=True),
        Index("ix_response_cache_expires", "expires_at"),
    )


class ServerConfig(Base):
    """
    Server-level configuration stored in the database.
    Replaces hardcoded .env values for runtime-configurable settings.
    Sensitive values (API keys, secrets) are encrypted at rest.
    """

    __tablename__ = "server_config"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    # Config key name (e.g., "OPENAI_API_KEY", "GOOGLE_CLIENT_ID")
    name = Column(String, nullable=False, unique=True, index=True)
    # The value (encrypted for sensitive settings)
    value = Column(Text, nullable=True)
    # Category for UI grouping: 'ai_providers', 'oauth', 'app_settings', 'uris', 'storage', 'billing'
    category = Column(String, nullable=False, default="general")
    # Whether this is a sensitive value that should be encrypted and masked in UI
    is_sensitive = Column(Boolean, default=False)
    # Whether this config is required for the server to function
    is_required = Column(Boolean, default=False)
    # Human-readable description for the UI
    description = Column(Text, nullable=True)
    # Data type hint: 'string', 'integer', 'boolean', 'url', 'secret'
    value_type = Column(String, default="string")
    # Default value if not set (for display purposes)
    default_value = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class SystemNotification(Base):
    """
    Server-wide notifications that can be broadcast to all users.
    Only super admins (role_id=0) can create these notifications.
    Used for announcements like server maintenance, feature releases, etc.
    """

    __tablename__ = "system_notification"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    # Notification title (short summary)
    title = Column(String, nullable=False)
    # Full notification message
    message = Column(Text, nullable=False)
    # User who created the notification (must be role_id=0)
    created_by = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id"),
        nullable=False,
    )
    # When the notification was created
    created_at = Column(DateTime, server_default=func.now())
    # When the notification expires (default 60 minutes from creation)
    expires_at = Column(DateTime, nullable=False)
    # Count of users who have received this notification
    notified_count = Column(Integer, default=0)
    # Whether the notification is active (can be manually deactivated)
    is_active = Column(Boolean, default=True)
    # Notification priority/type: 'info', 'warning', 'critical'
    notification_type = Column(String, default="info")

    creator = relationship("User")


class SystemNotificationReceipt(Base):
    """
    Tracks which users have received/acknowledged a system notification.
    Used to prevent duplicate notifications and track delivery stats.
    """

    __tablename__ = "system_notification_receipt"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    # The notification
    notification_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("system_notification.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The user who received it
    user_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # When the user received the notification
    received_at = Column(DateTime, server_default=func.now())
    # Whether the user has dismissed/acknowledged it
    dismissed_at = Column(DateTime, nullable=True)

    notification = relationship("SystemNotification", backref="receipts")
    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("notification_id", "user_id", name="uix_notification_user"),
    )


class ServerExtensionSetting(Base):
    """
    Server-level extension settings that serve as defaults for all companies.
    These are configured by super admins and cascade down:
    Server → Company → User (each level can override the previous).

    Sensitive values (API keys, secrets) are encrypted at rest.
    """

    __tablename__ = "server_extension_setting"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    # Extension name (e.g., "stripe_payments", "openai", "anthropic")
    extension_name = Column(String, nullable=False, index=True)
    # Setting key name (e.g., "STRIPE_API_KEY", "OPENAI_API_KEY")
    setting_key = Column(String, nullable=False)
    # The value (encrypted for sensitive settings)
    setting_value = Column(Text, nullable=True)
    # Whether this is a sensitive value that should be encrypted
    is_sensitive = Column(Boolean, default=False)
    # Human-readable description
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "extension_name", "setting_key", name="uix_server_ext_setting"
        ),
    )


class ServerExtensionCommand(Base):
    """
    Server-level extension command defaults that serve as defaults for all companies.
    These are configured by super admins and cascade down:
    Server → Company → User (each level can override the previous).

    When enabled=True, the command is enabled by default for all new agents.
    """

    __tablename__ = "server_extension_command"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    # Extension name (e.g., "web_search", "file_system")
    extension_name = Column(String, nullable=False, index=True)
    # Command name (e.g., "Search the Web", "Read File")
    command_name = Column(String, nullable=False)
    # Whether this command is enabled by default at server level
    enabled = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "extension_name", "command_name", name="uix_server_ext_command"
        ),
    )


class CompanyExtensionCommand(Base):
    """
    Company-level extension command defaults that override server defaults.
    Configured by company admins, these cascade down to users/agents.
    """

    __tablename__ = "company_extension_command"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    # Company this command belongs to
    company_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("Company.id"),
        nullable=False,
        index=True,
    )
    company = relationship("Company")
    # Extension name (e.g., "web_search", "file_system")
    extension_name = Column(String, nullable=False, index=True)
    # Command name (e.g., "Search the Web", "Read File")
    command_name = Column(String, nullable=False)
    # Whether this command is enabled at company level
    enabled = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "extension_name",
            "command_name",
            name="uix_company_ext_command",
        ),
    )


class CompanyExtensionSetting(Base):
    """
    Company-level extension settings that override server defaults.
    Configured by company admins, these cascade down to users.

    Sensitive values (API keys, secrets) are encrypted at rest.
    """

    __tablename__ = "company_extension_setting"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    # Company this setting belongs to
    company_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("Company.id"),
        nullable=False,
        index=True,
    )
    company = relationship("Company")
    # Extension name (e.g., "stripe_payments", "openai", "anthropic")
    extension_name = Column(String, nullable=False, index=True)
    # Setting key name (e.g., "STRIPE_API_KEY", "OPENAI_API_KEY")
    setting_key = Column(String, nullable=False)
    # The value (encrypted for sensitive settings)
    setting_value = Column(Text, nullable=True)
    # Whether this is a sensitive value that should be encrypted
    is_sensitive = Column(Boolean, default=False)
    # Human-readable description
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "extension_name",
            "setting_key",
            name="uix_company_ext_setting",
        ),
    )


class CompanyStorageSetting(Base):
    """
    Company-level storage settings that override server defaults.
    Allows companies to use their own cloud storage (S3, Azure, B2) for agent workspaces.

    If not configured, the company uses server default storage with retention policy.
    Child companies inherit parent company storage settings unless they define their own.

    Sensitive values (credentials) are encrypted at rest.
    """

    __tablename__ = "company_storage_setting"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    # Company this setting belongs to
    company_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("Company.id"),
        nullable=False,
        unique=True,  # One storage config per company
        index=True,
    )
    company = relationship("Company")
    # Storage backend: s3, azure, b2 (no 'local' option for companies - they use server storage)
    storage_backend = Column(
        String, nullable=False, default="server"
    )  # 'server', 's3', 'azure', 'b2'
    # Container/bucket name
    storage_container = Column(String, nullable=True)
    # AWS S3 / MinIO settings (encrypted)
    aws_access_key_id = Column(Text, nullable=True)
    aws_secret_access_key = Column(Text, nullable=True)
    aws_region = Column(String, nullable=True)
    s3_endpoint = Column(String, nullable=True)
    s3_bucket = Column(String, nullable=True)
    # Azure Blob settings (encrypted)
    azure_storage_account_name = Column(String, nullable=True)
    azure_storage_key = Column(Text, nullable=True)
    # Backblaze B2 settings (encrypted)
    b2_key_id = Column(Text, nullable=True)
    b2_application_key = Column(Text, nullable=True)
    b2_region = Column(String, nullable=True)
    # Metadata
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ============================================================================
# Tiered Prompts and Chains (Server → Company → User)
# ============================================================================
# These tables implement a hierarchical configuration system for prompts and chains:
# - Server level: Global defaults managed by super admins, available to all users
# - Company level: Company-wide templates managed by company admins
# - User level: Personal prompts/chains (existing Prompt and Chain tables)
#
# When a user tries to edit a server or company prompt/chain, a clone is created
# at their level. Users can revert to the parent (server/company) version.
# ============================================================================


class ServerPromptCategory(Base):
    """
    Server-level prompt categories that serve as global defaults.
    Managed by super admins, these are visible to all users.
    """

    __tablename__ = "server_prompt_category"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=False, default="")
    # If True, this category and its prompts are for internal system use only
    # and should not be shown to users in UI
    is_internal = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("name", name="uix_server_prompt_category_name"),)


class ServerPrompt(Base):
    """
    Server-level prompts that serve as global defaults for all companies.
    Managed by super admins, these cascade down: Server → Company → User.
    Internal prompts (like "Think About It") are marked with is_internal=True
    and are available to agents but hidden from user prompt lists.
    """

    __tablename__ = "server_prompt"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    category_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("server_prompt_category.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=False, default="")
    content = Column(Text, nullable=False)
    # If True, this prompt is for internal agent use only (e.g., "Think About It")
    # and should not be shown to users in prompt selection UI
    is_internal = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    category = relationship("ServerPromptCategory", backref="prompts")

    __table_args__ = (
        UniqueConstraint("name", "category_id", name="uix_server_prompt_name_cat"),
    )


class ServerPromptArgument(Base):
    """Arguments extracted from server-level prompts."""

    __tablename__ = "server_prompt_argument"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    prompt_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("server_prompt.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(Text, nullable=False)

    prompt = relationship("ServerPrompt", backref="arguments")


class ServerChain(Base):
    """
    Server-level chains that serve as global workflow templates.
    Managed by super admins, these cascade down: Server → Company → User.
    """

    __tablename__ = "server_chain"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    name = Column(Text, nullable=False, unique=True)
    description = Column(Text, nullable=True, default="")
    # If True, this chain is for internal system use only
    is_internal = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ServerChainStep(Base):
    """Steps for server-level chains."""

    __tablename__ = "server_chain_step"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    chain_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("server_chain.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_number = Column(Integer, nullable=False)
    # "Prompt", "Chain", "Command"
    prompt_type = Column(Text)
    # The target reference - could be prompt name, chain name, or command name
    prompt = Column(Text)
    # Agent name to use for this step (will resolve to user's agent at runtime)
    agent_name = Column(Text, nullable=True)

    chain = relationship("ServerChain", backref="steps")


class ServerChainStepArgument(Base):
    """Arguments for server-level chain steps."""

    __tablename__ = "server_chain_step_argument"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    chain_step_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("server_chain_step.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(Text, nullable=False)
    value = Column(Text, nullable=True)

    chain_step = relationship("ServerChainStep", backref="arguments")


class CompanyPromptCategory(Base):
    """
    Company-level prompt categories that can override server defaults.
    Managed by company admins, these are visible to company users.
    """

    __tablename__ = "company_prompt_category"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    company_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("Company.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=False, default="")
    # Reference to server category if this is an override
    server_category_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("server_prompt_category.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    company = relationship("Company")
    server_category = relationship("ServerPromptCategory")

    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uix_company_prompt_category_name"),
    )


class CompanyPrompt(Base):
    """
    Company-level prompts that override server defaults or are company-specific.
    Managed by company admins, these are visible to company users.
    """

    __tablename__ = "company_prompt"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    company_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("Company.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("company_prompt_category.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=False, default="")
    content = Column(Text, nullable=False)
    # Reference to server prompt if this is an override
    server_prompt_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("server_prompt.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    company = relationship("Company")
    category = relationship("CompanyPromptCategory", backref="prompts")
    server_prompt = relationship("ServerPrompt")

    __table_args__ = (
        UniqueConstraint(
            "company_id", "name", "category_id", name="uix_company_prompt_name_cat"
        ),
    )


class CompanyPromptArgument(Base):
    """Arguments extracted from company-level prompts."""

    __tablename__ = "company_prompt_argument"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    prompt_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("company_prompt.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(Text, nullable=False)

    prompt = relationship("CompanyPrompt", backref="arguments")


class CompanyChain(Base):
    """
    Company-level chains that override server defaults or are company-specific.
    Managed by company admins, these are visible to company users.
    """

    __tablename__ = "company_chain"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    company_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("Company.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True, default="")
    # Reference to server chain if this is an override
    server_chain_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("server_chain.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    company = relationship("Company")
    server_chain = relationship("ServerChain")

    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uix_company_chain_name"),
    )


class CompanyChainStep(Base):
    """Steps for company-level chains."""

    __tablename__ = "company_chain_step"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    chain_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("company_chain.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_number = Column(Integer, nullable=False)
    prompt_type = Column(Text)
    prompt = Column(Text)
    agent_name = Column(Text, nullable=True)

    chain = relationship("CompanyChain", backref="steps")


class CompanyChainStepArgument(Base):
    """Arguments for company-level chain steps."""

    __tablename__ = "company_chain_step_argument"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    chain_step_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("company_chain_step.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(Text, nullable=False)
    value = Column(Text, nullable=True)

    chain_step = relationship("CompanyChainStep", backref="arguments")


class UserPromptOverride(Base):
    """
    Tracks when a user has customized (cloned) a server or company prompt.
    This allows users to revert to the original version.
    """

    __tablename__ = "user_prompt_override"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    user_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The user's customized prompt (in the existing Prompt table)
    prompt_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("prompt.id", ondelete="CASCADE"),
        nullable=False,
    )
    # The source prompt that was cloned - one of these will be set
    server_prompt_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("server_prompt.id", ondelete="SET NULL"),
        nullable=True,
    )
    company_prompt_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("company_prompt.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User")
    prompt = relationship("Prompt")
    server_prompt = relationship("ServerPrompt")
    company_prompt = relationship("CompanyPrompt")

    __table_args__ = (
        UniqueConstraint("user_id", "prompt_id", name="uix_user_prompt_override"),
    )


class UserChainOverride(Base):
    """
    Tracks when a user has customized (cloned) a server or company chain.
    This allows users to revert to the original version.
    """

    __tablename__ = "user_chain_override"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    user_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The user's customized chain (in the existing Chain table)
    chain_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("chain.id", ondelete="CASCADE"),
        nullable=False,
    )
    # The source chain that was cloned - one of these will be set
    server_chain_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("server_chain.id", ondelete="SET NULL"),
        nullable=True,
    )
    company_chain_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("company_chain.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User")
    chain = relationship("Chain")
    server_chain = relationship("ServerChain")
    company_chain = relationship("CompanyChain")

    __table_args__ = (
        UniqueConstraint("user_id", "chain_id", name="uix_user_chain_override"),
    )


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
    pin_order = Column(
        Integer, nullable=True
    )  # NULL = unpinned, integer = pin position
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    user_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id"),
        nullable=True,
    )
    user = relationship("User", backref="conversation")


class ConversationShare(Base):
    __tablename__ = "conversation_share"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    source_conversation_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("conversation.id"),
        nullable=False,
    )
    shared_conversation_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("conversation.id"),
        nullable=False,
    )
    share_type = Column(String, nullable=False)  # 'user' or 'public'
    share_token = Column(String, unique=True, nullable=False)
    shared_by_user_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id"),
        nullable=False,
    )
    shared_with_user_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id"),
        nullable=True,
    )
    include_workspace = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime, nullable=True)

    source_conversation = relationship(
        "Conversation", foreign_keys=[source_conversation_id]
    )
    shared_conversation = relationship(
        "Conversation", foreign_keys=[shared_conversation_id]
    )
    shared_by_user = relationship("User", foreign_keys=[shared_by_user_id])
    shared_with_user = relationship("User", foreign_keys=[shared_with_user_id])


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


class DiscardedContext(Base):
    """
    Stores discarded context items that can be retrieved later if needed.
    When a message/activity is discarded, the original content is stored here
    and a summary replaces it in the context for token optimization.
    """

    __tablename__ = "discarded_context"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    message_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("message.id"),
        nullable=False,
        index=True,
    )
    conversation_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("conversation.id"),
        nullable=False,
        index=True,
    )
    reason = Column(Text, nullable=False)  # Short reason for discarding
    original_content = Column(Text, nullable=False)  # Full original content
    discarded_at = Column(DateTime, server_default=func.now())
    retrieved_at = Column(DateTime, nullable=True)  # Set when retrieved back
    is_active = Column(Boolean, default=True)  # False when retrieved

    message = relationship("Message", foreign_keys=[message_id])
    conversation = relationship("Conversation", foreign_keys=[conversation_id])


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
    # Task type: 'prompt' (default), 'command', or 'deployment'
    task_type = Column(String, default="prompt")
    # For command tasks: the shell command/script to execute
    command_script = Column(Text, nullable=True)
    # For deployment tasks: reference to deployment ID
    deployment_id = Column(String, nullable=True)
    # Target machines for command/deployment tasks (JSON array of machine IDs)
    target_machines = Column(Text, nullable=True)
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


class PersonalAccessToken(Base):
    """
    Personal Access Tokens (PATs) are similar to GitHub's personal access tokens.
    They allow users to create API keys with specific scopes, agent access, and company access.
    The token_hash stores a hashed version of the token for security.
    """

    __tablename__ = "personal_access_token"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    # User who created this token
    user_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Token name for identification (e.g., "CI/CD Pipeline", "Local Development")
    name = Column(String, nullable=False)
    # Token prefix for identification (first 8 chars, like "agixt_abc123")
    token_prefix = Column(String(16), nullable=False, index=True)
    # SHA-256 hash of the full token for validation
    token_hash = Column(String(64), nullable=False, unique=True)
    # JSON array of scope names this token has access to
    # e.g., ["agents:read", "agents:execute", "conversations:write"]
    scopes_json = Column(Text, nullable=False, default="[]")
    # JSON array of agent IDs this token can access (empty = all agents user has access to)
    agents_json = Column(Text, nullable=False, default="[]")
    # JSON array of company IDs this token can access (empty = all companies user has access to)
    companies_json = Column(Text, nullable=False, default="[]")
    # Expiration date (null = never expires)
    expires_at = Column(DateTime, nullable=True)
    # Whether this token has been revoked
    is_revoked = Column(Boolean, default=False, nullable=False)
    # Last time this token was used
    last_used_at = Column(DateTime, nullable=True)
    # Creation timestamp
    created_at = Column(DateTime, server_default=func.now())
    # Update timestamp
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", backref="personal_access_tokens")


class PersonalAccessTokenAgentAccess(Base):
    """
    Junction table for tokens that have access to specific agents.
    If no entries exist for a token, it has access to all agents the user can access.
    """

    __tablename__ = "personal_access_token_agent"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    token_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("personal_access_token.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("agent.id", ondelete="CASCADE"),
        nullable=False,
    )

    token = relationship("PersonalAccessToken", backref="agent_access")
    agent = relationship("Agent")


class PersonalAccessTokenCompanyAccess(Base):
    """
    Junction table for tokens that have access to specific companies.
    If no entries exist for a token, it has access to all companies the user can access.
    """

    __tablename__ = "personal_access_token_company"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    token_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("personal_access_token.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("Company.id", ondelete="CASCADE"),
        nullable=False,
    )

    token = relationship("PersonalAccessToken", backref="company_access")
    company = relationship("Company")


class PaymentTransaction(Base):
    __tablename__ = "payment_transaction"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    reference_code = Column(String, nullable=False, unique=True)
    user_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id"),
        nullable=True,
    )
    company_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("Company.id"),
        nullable=True,
    )
    seat_count = Column(Integer, nullable=False, default=1)
    token_amount = Column(
        Integer, nullable=True
    )  # Number of tokens purchased (for token-based billing)
    payment_method = Column(String, nullable=False)  # stripe, crypto
    currency = Column(String, nullable=False)
    network = Column(String, nullable=True)
    amount_usd = Column(Float, nullable=False)
    amount_currency = Column(Float, nullable=False)
    exchange_rate = Column(Float, nullable=False)
    status = Column(String, nullable=False, default="pending")
    transaction_hash = Column(String, nullable=True, unique=True)
    stripe_payment_intent_id = Column(String, nullable=True, unique=True)
    wallet_address = Column(String, nullable=True)
    memo = Column(String, nullable=True)
    metadata_json = Column(Text, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    # Per-app billing tracking
    app_name = Column(
        String, nullable=True, default=None
    )  # The app this payment is for (e.g., "XT Systems", "NurseXT")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", backref="payment_transactions")
    company = relationship("Company", backref="payment_transactions")


class TrialDomain(Base):
    """
    Tracks email domains that have used trial credits.
    Used to prevent trial abuse by ensuring each business domain only gets trial credits once.
    """

    __tablename__ = "trial_domain"
    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id if DATABASE_TYPE == "sqlite" else uuid.uuid4,
    )
    domain = Column(String, nullable=False, unique=True, index=True)
    company_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("Company.id"),
        nullable=False,
    )
    user_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("user.id"),
        nullable=False,
    )
    credits_granted = Column(Float, nullable=False, default=0.0)  # USD value granted
    created_at = Column(DateTime, server_default=func.now())

    company = relationship("Company", backref="trial_domains")
    user = relationship("User", backref="trial_domains")


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
    # display_order determines UI ordering (lower = higher in list)
    {
        "id": 0,
        "name": "super_admin",
        "friendly_name": "Super Admin",
        "display_order": 0,
    },
    {
        "id": 1,
        "name": "tenant_admin",
        "friendly_name": "Tenant Admin",
        "display_order": 1,
    },
    {
        "id": 2,
        "name": "company_admin",
        "friendly_name": "Company Admin",
        "display_order": 2,
    },
    {"id": 3, "name": "user", "friendly_name": "Power User", "display_order": 3},
    {
        "id": 6,
        "name": "read_only_user",
        "friendly_name": "Read Only User",
        "display_order": 4,
    },
    {"id": 5, "name": "chat_user", "friendly_name": "Chat User", "display_order": 5},
    {"id": 4, "name": "child", "friendly_name": "Child", "display_order": 6},
]


# Keyword mappings for categorizing extension commands into features
EXTENSION_FEATURE_KEYWORDS = {
    # Common PSA/Ticketing features
    "tickets": [
        "ticket",
        "tickets",
        "case",
        "cases",
        "incident",
        "incidents",
        "support",
    ],
    "companies": [
        "company",
        "companies",
        "organization",
        "organizations",
        "client",
        "clients",
        "customer",
        "customers",
    ],
    "contacts": ["contact", "contacts", "person", "people", "member", "members"],
    "devices": [
        "device",
        "devices",
        "configuration",
        "configurations",
        "asset",
        "assets",
        "endpoint",
        "endpoints",
        "machine",
        "machines",
    ],
    "agreements": [
        "agreement",
        "agreements",
        "contract",
        "contracts",
        "subscription",
        "subscriptions",
    ],
    "warranty": ["warranty", "warranties"],
    # GitHub/Version Control features
    "repositories": ["repo", "repos", "repository", "repositories", "codebase"],
    "issues": ["issue", "issues"],
    "pull_requests": ["pull", "pr", "prs", "merge"],
    "commits": ["commit", "commits"],
    "comments": ["comment", "comments"],
    "branches": ["branch", "branches"],
    "files": ["file", "files", "upload", "download"],
    # RMM/Monitoring features
    "alerts": ["alert", "alerts", "alarm", "alarms", "warning", "warnings"],
    "monitoring": ["monitor", "monitoring", "status", "health", "metrics"],
    "scripts": ["script", "scripts", "command", "commands", "execute", "run"],
    "patches": ["patch", "patches", "update", "updates"],
    "backups": ["backup", "backups", "restore", "recovery"],
    # Security features
    "threats": ["threat", "threats", "malware", "virus", "detection", "quarantine"],
    "scans": ["scan", "scans", "scanning"],
    "policies": ["policy", "policies", "rule", "rules"],
    "users": ["user", "users", "account", "accounts"],
    "groups": ["group", "groups"],
    # General CRUD patterns
    "search": ["search", "find", "lookup", "query", "filter", "list"],
    "create": ["create", "add", "new", "insert"],
    "update": ["update", "modify", "edit", "change", "patch"],
    "delete": ["delete", "remove", "destroy"],
}


def get_extension_names():
    """
    Scan all extension directories (core and hub) to get all extension names.
    Returns a list of extension names (derived from Python filenames).
    """
    extension_names = set()

    # Get all extension search paths from ExtensionsHub
    try:
        from ExtensionsHub import ExtensionsHub

        hub = ExtensionsHub()
        search_paths = hub.get_extension_search_paths()
    except Exception as e:
        logging.debug(f"Could not load ExtensionsHub: {e}")
        # Fall back to default extensions directory
        extensions_dir = os.path.join(os.path.dirname(__file__), "extensions")
        search_paths = [extensions_dir] if os.path.exists(extensions_dir) else []

    for ext_dir in search_paths:
        if os.path.exists(ext_dir) and os.path.isdir(ext_dir):
            for filename in os.listdir(ext_dir):
                if filename.endswith(".py") and not filename.startswith("_"):
                    # Convert filename to extension name (e.g., "github.py" -> "github")
                    ext_name = filename[:-3]  # Remove .py
                    extension_names.add(ext_name)

    return sorted(extension_names)


def get_extension_path(extension_name: str) -> str:
    """
    Find the full path to an extension file.
    Returns the path if found, None otherwise.
    """
    # Get all extension search paths from ExtensionsHub
    try:
        from ExtensionsHub import ExtensionsHub

        hub = ExtensionsHub()
        search_paths = hub.get_extension_search_paths()
    except Exception as e:
        logging.debug(f"Could not load ExtensionsHub: {e}")
        # Fall back to default extensions directory
        extensions_dir = os.path.join(os.path.dirname(__file__), "extensions")
        search_paths = [extensions_dir] if os.path.exists(extensions_dir) else []

    for ext_dir in search_paths:
        potential_path = os.path.join(ext_dir, f"{extension_name}.py")
        if os.path.exists(potential_path):
            return potential_path

    return None


def parse_extension_commands(extension_path: str) -> list:
    """
    Parse an extension file and extract command names from self.commands dict.
    Returns a list of command names.
    """
    commands = []
    try:
        with open(extension_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Look for self.commands = { or self.commands = ( patterns
        import re

        # Find the commands dictionary/dict-like structure
        # Pattern matches: self.commands = { ... } or self.commands = ( { ... } )
        commands_pattern = r"self\.commands\s*=\s*[\{\(]([^}]+)[\}\)]"
        match = re.search(commands_pattern, content, re.DOTALL)

        if match:
            commands_block = match.group(1)
            # Extract command names from strings like "Get Companies": self.get_companies,
            command_pattern = r'"([^"]+)":\s*self\.'
            commands = re.findall(command_pattern, commands_block)

    except Exception as e:
        logging.debug(f"Could not parse commands from {extension_path}: {e}")

    return commands


def categorize_command(command_name: str) -> tuple:
    """
    Categorize a command name into a feature and action type.
    Returns (feature, action) tuple.

    Example: "Get Companies" -> ("companies", "read")
             "Create New Ticket" -> ("tickets", "write")
             "Run Script" -> ("scripts", "execute")
    """
    command_lower = command_name.lower()

    # Determine action type from command
    action = "read"  # default
    if any(
        word in command_lower for word in ["create", "add", "new", "insert", "post"]
    ):
        action = "write"
    elif any(
        word in command_lower
        for word in ["update", "modify", "edit", "change", "patch", "set"]
    ):
        action = "write"
    elif any(
        word in command_lower for word in ["delete", "remove", "destroy", "close"]
    ):
        action = "delete"
    elif any(
        word in command_lower
        for word in ["execute", "run", "invoke", "trigger", "send", "push"]
    ):
        action = "execute"
    elif any(
        word in command_lower
        for word in ["get", "list", "find", "search", "fetch", "retrieve", "view"]
    ):
        action = "read"

    # Find the feature category
    for feature, keywords in EXTENSION_FEATURE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in command_lower:
                return (feature, action)

    # Default to "general" if no specific feature matched
    return ("general", action)


def get_extension_features(extension_name: str) -> dict:
    """
    Get all features and their actions for a specific extension.
    Returns a dict of {feature: set(actions)}.
    """
    features = {}

    # Find the extension file
    extension_path = get_extension_path(extension_name)

    if not extension_path:
        return features

    # Parse commands and categorize them
    commands = parse_extension_commands(extension_path)
    for command in commands:
        feature, action = categorize_command(command)
        if feature not in features:
            features[feature] = set()
        features[feature].add(action)

    return features


def generate_extension_scopes():
    """
    Generate per-extension scopes dynamically based on discovered extensions.
    Each extension gets three scopes: read, execute, and configure.
    """
    extension_scopes = []
    extension_names = get_extension_names()

    for ext_name in extension_names:
        # Make the extension name display-friendly
        friendly_name = ext_name.replace("_", " ").title()

        # Base extension scopes (read, execute, configure for the whole extension)
        extension_scopes.append(
            {
                "name": f"ext:{ext_name}:read",
                "resource": f"ext:{ext_name}",
                "action": "read",
                "description": f"View {friendly_name} extension and its configuration",
                "category": "Extensions",
            }
        )

        extension_scopes.append(
            {
                "name": f"ext:{ext_name}:execute",
                "resource": f"ext:{ext_name}",
                "action": "execute",
                "description": f"Execute all {friendly_name} extension commands",
                "category": "Extensions",
            }
        )

        extension_scopes.append(
            {
                "name": f"ext:{ext_name}:configure",
                "resource": f"ext:{ext_name}",
                "action": "configure",
                "description": f"Configure {friendly_name} extension settings",
                "category": "Extensions",
            }
        )

        # Generate deep feature-level scopes by analyzing extension commands
        features = get_extension_features(ext_name)
        for feature, actions in features.items():
            feature_friendly = feature.replace("_", " ").title()

            for action in actions:
                scope_name = f"ext:{ext_name}:{feature}:{action}"

                # Generate description based on action type
                if action == "read":
                    description = f"View {feature_friendly} data in {friendly_name}"
                elif action == "write":
                    description = f"Create/modify {feature_friendly} in {friendly_name}"
                elif action == "delete":
                    description = f"Delete {feature_friendly} in {friendly_name}"
                elif action == "execute":
                    description = (
                        f"Execute {feature_friendly} commands in {friendly_name}"
                    )
                else:
                    description = (
                        f"{action.title()} {feature_friendly} in {friendly_name}"
                    )

                extension_scopes.append(
                    {
                        "name": scope_name,
                        "resource": f"ext:{ext_name}:{feature}",
                        "action": action,
                        "description": description,
                        "category": "Extensions",
                    }
                )

    return extension_scopes


# Default scopes define granular permissions for the system
# Format: resource:action
# Categories help group scopes in the UI for easier management
default_scopes = [
    # Core Agent Scopes
    {
        "name": "agents:read",
        "resource": "agents",
        "action": "read",
        "description": "View agents and their configurations",
        "category": "Agents",
    },
    {
        "name": "agents:write",
        "resource": "agents",
        "action": "write",
        "description": "Create and modify agents",
        "category": "Agents",
    },
    {
        "name": "agents:delete",
        "resource": "agents",
        "action": "delete",
        "description": "Delete agents",
        "category": "Agents",
    },
    {
        "name": "agents:execute",
        "resource": "agents",
        "action": "execute",
        "description": "Run agent prompts and commands",
        "category": "Agents",
    },
    {
        "name": "agents:train",
        "resource": "agents",
        "action": "train",
        "description": "Train agents with new data",
        "category": "Agents",
    },
    # Conversation Scopes
    {
        "name": "conversations:read",
        "resource": "conversations",
        "action": "read",
        "description": "View conversations and messages",
        "category": "Conversations",
    },
    {
        "name": "conversations:write",
        "resource": "conversations",
        "action": "write",
        "description": "Create and send messages",
        "category": "Conversations",
    },
    {
        "name": "conversations:delete",
        "resource": "conversations",
        "action": "delete",
        "description": "Delete conversations",
        "category": "Conversations",
    },
    {
        "name": "conversations:share",
        "resource": "conversations",
        "action": "share",
        "description": "Share conversations with others",
        "category": "Conversations",
    },
    # Extension Scopes
    {
        "name": "extensions:read",
        "resource": "extensions",
        "action": "read",
        "description": "View available extensions",
        "category": "Extensions",
    },
    {
        "name": "extensions:write",
        "resource": "extensions",
        "action": "write",
        "description": "Configure and enable extensions",
        "category": "Extensions",
    },
    {
        "name": "extensions:execute",
        "resource": "extensions",
        "action": "execute",
        "description": "Execute extension commands",
        "category": "Extensions",
    },
    {
        "name": "extensions:install",
        "resource": "extensions",
        "action": "install",
        "description": "Install new extensions from hub",
        "category": "Extensions",
    },
    # Memory/Knowledge Scopes
    {
        "name": "memories:read",
        "resource": "memories",
        "action": "read",
        "description": "View agent memories and knowledge",
        "category": "Knowledge",
    },
    {
        "name": "memories:write",
        "resource": "memories",
        "action": "write",
        "description": "Add memories and knowledge",
        "category": "Knowledge",
    },
    {
        "name": "memories:delete",
        "resource": "memories",
        "action": "delete",
        "description": "Delete memories and knowledge",
        "category": "Knowledge",
    },
    {
        "name": "memories:export",
        "resource": "memories",
        "action": "export",
        "description": "Export memories and knowledge",
        "category": "Knowledge",
    },
    # Chain/Workflow Scopes
    {
        "name": "chains:read",
        "resource": "chains",
        "action": "read",
        "description": "View chains and workflows",
        "category": "Automation",
    },
    {
        "name": "chains:write",
        "resource": "chains",
        "action": "write",
        "description": "Create and modify chains",
        "category": "Automation",
    },
    {
        "name": "chains:delete",
        "resource": "chains",
        "action": "delete",
        "description": "Delete chains",
        "category": "Automation",
    },
    {
        "name": "chains:execute",
        "resource": "chains",
        "action": "execute",
        "description": "Run chains",
        "category": "Automation",
    },
    # Prompt Scopes
    {
        "name": "prompts:read",
        "resource": "prompts",
        "action": "read",
        "description": "View prompts",
        "category": "Prompts",
    },
    {
        "name": "prompts:write",
        "resource": "prompts",
        "action": "write",
        "description": "Create and modify prompts",
        "category": "Prompts",
    },
    {
        "name": "prompts:delete",
        "resource": "prompts",
        "action": "delete",
        "description": "Delete prompts",
        "category": "Prompts",
    },
    {
        "name": "prompts:share",
        "resource": "prompts",
        "action": "share",
        "description": "Share prompts with company members",
        "category": "Prompts",
    },
    # Server-level prompt/chain management (super admin only)
    {
        "name": "server:prompts",
        "resource": "server",
        "action": "prompts",
        "description": "Manage server-level global prompts",
        "category": "Super Admin",
    },
    {
        "name": "server:chains",
        "resource": "server",
        "action": "chains",
        "description": "Manage server-level global chains",
        "category": "Super Admin",
    },
    # Company-level prompt/chain management
    {
        "name": "company:prompts",
        "resource": "company",
        "action": "prompts",
        "description": "Manage company-wide prompts",
        "category": "Administration",
    },
    {
        "name": "company:chains",
        "resource": "company",
        "action": "chains",
        "description": "Manage company-wide chains",
        "category": "Administration",
    },
    {
        "name": "chains:share",
        "resource": "chains",
        "action": "share",
        "description": "Share chains with company members",
        "category": "Automation",
    },
    # Company/Team Management Scopes
    {
        "name": "company:read",
        "resource": "company",
        "action": "read",
        "description": "View company details",
        "category": "Administration",
    },
    {
        "name": "company:write",
        "resource": "company",
        "action": "write",
        "description": "Modify company settings",
        "category": "Administration",
    },
    {
        "name": "company:delete",
        "resource": "company",
        "action": "delete",
        "description": "Delete companies",
        "category": "Administration",
    },
    {
        "name": "company:billing",
        "resource": "company",
        "action": "billing",
        "description": "Manage billing and subscriptions",
        "category": "Administration",
    },
    # User Management Scopes
    {
        "name": "users:read",
        "resource": "users",
        "action": "read",
        "description": "View team members",
        "category": "Administration",
    },
    {
        "name": "users:write",
        "resource": "users",
        "action": "write",
        "description": "Invite and manage team members",
        "category": "Administration",
    },
    {
        "name": "users:delete",
        "resource": "users",
        "action": "delete",
        "description": "Remove team members",
        "category": "Administration",
    },
    {
        "name": "users:roles",
        "resource": "users",
        "action": "roles",
        "description": "Assign and manage user roles",
        "category": "Administration",
    },
    # Role Management Scopes
    {
        "name": "roles:read",
        "resource": "roles",
        "action": "read",
        "description": "View custom roles",
        "category": "Administration",
    },
    {
        "name": "roles:write",
        "resource": "roles",
        "action": "write",
        "description": "Create and modify custom roles",
        "category": "Administration",
    },
    {
        "name": "roles:delete",
        "resource": "roles",
        "action": "delete",
        "description": "Delete custom roles",
        "category": "Administration",
    },
    # Webhook Scopes
    {
        "name": "webhooks:read",
        "resource": "webhooks",
        "action": "read",
        "description": "View webhooks",
        "category": "Integrations",
    },
    {
        "name": "webhooks:write",
        "resource": "webhooks",
        "action": "write",
        "description": "Create and modify webhooks",
        "category": "Integrations",
    },
    {
        "name": "webhooks:delete",
        "resource": "webhooks",
        "action": "delete",
        "description": "Delete webhooks",
        "category": "Integrations",
    },
    # Provider/OAuth Scopes
    {
        "name": "providers:read",
        "resource": "providers",
        "action": "read",
        "description": "View connected providers",
        "category": "Integrations",
    },
    {
        "name": "providers:write",
        "resource": "providers",
        "action": "write",
        "description": "Connect and configure providers",
        "category": "Integrations",
    },
    {
        "name": "providers:delete",
        "resource": "providers",
        "action": "delete",
        "description": "Disconnect providers",
        "category": "Integrations",
    },
    # API Key Scopes
    {
        "name": "apikeys:read",
        "resource": "apikeys",
        "action": "read",
        "description": "View API keys",
        "category": "Security",
    },
    {
        "name": "apikeys:write",
        "resource": "apikeys",
        "action": "write",
        "description": "Create API keys",
        "category": "Security",
    },
    {
        "name": "apikeys:delete",
        "resource": "apikeys",
        "action": "delete",
        "description": "Revoke API keys",
        "category": "Security",
    },
    # Secret Management Scopes
    {
        "name": "secrets:read",
        "resource": "secrets",
        "action": "read",
        "description": "View secrets",
        "category": "Security",
    },
    {
        "name": "secrets:write",
        "resource": "secrets",
        "action": "write",
        "description": "Create and update secrets",
        "category": "Security",
    },
    {
        "name": "secrets:delete",
        "resource": "secrets",
        "action": "delete",
        "description": "Delete secrets",
        "category": "Security",
    },
    # Billing Scopes
    {
        "name": "billing:read",
        "resource": "billing",
        "action": "read",
        "description": "View billing information",
        "category": "Billing",
    },
    {
        "name": "billing:write",
        "resource": "billing",
        "action": "write",
        "description": "Update payment methods and subscriptions",
        "category": "Billing",
    },
    {
        "name": "billing:admin",
        "resource": "billing",
        "action": "admin",
        "description": "Full billing administration access",
        "category": "Billing",
    },
    # Asset Management Scopes
    {
        "name": "assets:read",
        "resource": "assets",
        "action": "read",
        "description": "View assets and files",
        "category": "Assets",
    },
    {
        "name": "assets:write",
        "resource": "assets",
        "action": "write",
        "description": "Upload and modify assets",
        "category": "Assets",
    },
    {
        "name": "assets:delete",
        "resource": "assets",
        "action": "delete",
        "description": "Delete assets",
        "category": "Assets",
    },
    # Ticket/Support Scopes
    {
        "name": "tickets:read",
        "resource": "tickets",
        "action": "read",
        "description": "View support tickets",
        "category": "Support",
    },
    {
        "name": "tickets:write",
        "resource": "tickets",
        "action": "write",
        "description": "Create and respond to tickets",
        "category": "Support",
    },
    {
        "name": "tickets:manage",
        "resource": "tickets",
        "action": "manage",
        "description": "Manage all tickets",
        "category": "Support",
    },
    # Activity Scopes
    {
        "name": "activity:read",
        "resource": "activity",
        "action": "read",
        "description": "View activity logs",
        "category": "Monitoring",
    },
    {
        "name": "activity:export",
        "resource": "activity",
        "action": "export",
        "description": "Export activity logs",
        "category": "Monitoring",
    },
    # UI Feature Scopes
    {
        "name": "ui:settings",
        "resource": "ui",
        "action": "settings",
        "description": "Access settings panel",
        "category": "UI Features",
    },
    {
        "name": "ui:admin_panel",
        "resource": "ui",
        "action": "admin_panel",
        "description": "Access admin sections",
        "category": "UI Features",
    },
    {
        "name": "ui:voice_only_mode",
        "resource": "ui",
        "action": "voice_only_mode",
        "description": "Restricted voice-only interface",
        "category": "UI Features",
    },
    {
        "name": "ui:full_chat",
        "resource": "ui",
        "action": "full_chat",
        "description": "Full chat interface with all features",
        "category": "UI Features",
    },
    {
        "name": "ui:developer_mode",
        "resource": "ui",
        "action": "developer_mode",
        "description": "Toggle developer mode",
        "category": "UI Features",
    },
    # Super Admin Only Scopes
    {
        "name": "server:admin",
        "resource": "server",
        "action": "admin",
        "description": "Full server administration access",
        "category": "Super Admin",
    },
    {
        "name": "companies:manage",
        "resource": "companies",
        "action": "manage",
        "description": "Manage all companies on server",
        "category": "Super Admin",
    },
    {
        "name": "users:impersonate",
        "resource": "users",
        "action": "impersonate",
        "description": "Impersonate other users",
        "category": "Super Admin",
    },
]

# Define which scopes each default role has
# Lower role_id = higher privileges
default_role_scopes = {
    0: ["*"],  # super_admin: all scopes (wildcard)
    1: [  # tenant_admin: full company management
        "agents:*",
        "conversations:*",
        "extensions:*",
        "memories:*",
        "chains:*",
        "prompts:*",
        "company:*",
        "users:*",
        "roles:*",
        "webhooks:*",
        "providers:*",
        "apikeys:*",
        "secrets:*",
        "billing:*",
        "assets:*",
        "tickets:*",
        "activity:*",
        "ui:settings",
        "ui:admin_panel",
        "ui:full_chat",
        "ui:developer_mode",
        "ext:*",  # All extension-specific scopes
    ],
    2: [  # company_admin: company management without some admin features
        "agents:*",
        "conversations:*",
        "extensions:*",
        "memories:*",
        "chains:*",
        "prompts:*",
        "company:read",
        "company:write",
        "company:prompts",  # Manage company-wide prompts
        "company:chains",  # Manage company-wide chains
        "users:read",
        "users:write",
        "roles:read",
        "webhooks:*",
        "providers:*",
        "apikeys:*",
        "secrets:read",
        "secrets:write",
        "billing:read",
        "billing:write",
        "assets:*",
        "tickets:*",
        "activity:read",
        "ui:settings",
        "ui:admin_panel",
        "ui:full_chat",
        "ui:developer_mode",
        "ext:*",  # All extension-specific scopes
    ],
    3: [  # user: standard access
        "agents:read",
        "agents:execute",
        "conversations:*",
        "extensions:read",
        "extensions:execute",
        "memories:read",
        "memories:write",
        "chains:read",
        "chains:execute",
        "prompts:read",
        "apikeys:*",
        "assets:read",
        "assets:write",
        "tickets:read",
        "tickets:write",
        "activity:read",
        "ui:settings",
        "ui:full_chat",
        "ext:*:read",
        "ext:*:write",
        "ext:*:execute",  # Can read, write, and execute all extensions, but not configure
    ],
    4: [  # child: restricted voice-only access
        "agents:execute",
        "conversations:read",
        "conversations:write",
        "ui:voice_only_mode",
        # No extension access for child users
    ],
    5: [  # chat_user: chat only
        "agents:execute",
        "conversations:read",
        "conversations:write",
        "ui:full_chat",
        # Limited extension access - only execute through agent
    ],
    6: [  # read_only_user: read-only access to everything user has
        "agents:read",
        "conversations:read",
        "extensions:read",
        "memories:read",
        "chains:read",
        "prompts:read",
        "assets:read",
        "tickets:read",
        "activity:read",
        "ui:settings",
        "ui:full_chat",
        "ext:*:read",  # Can read all extensions, but not write or execute
    ],
}

default_extension_categories = [
    {
        "name": "AI Provider",
        "description": "AI inference providers for text generation, image generation, text-to-speech, transcription, and other AI capabilities. These extensions provide the underlying AI services used by agents.",
    },
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
    {
        "name": "Remote Monitoring",
        "description": "Remote monitoring and management platforms for IT infrastructure, endpoints, and network devices",
    },
    {
        "name": "PSA & Ticketing",
        "description": "Professional services automation and ticketing systems for service management and business operations",
    },
    {
        "name": "Security & Compliance",
        "description": "Cybersecurity platforms for threat detection, endpoint protection, and compliance management",
    },
    {
        "name": "Documentation & Knowledge",
        "description": "Documentation platforms and knowledge management systems for IT and business information",
    },
    {
        "name": "Cloud Services",
        "description": "Cloud-based productivity and business applications including Microsoft 365, Google Workspace, and more",
    },
    {
        "name": "Backup & Recovery",
        "description": "Data backup, disaster recovery, and business continuity solutions",
    },
    {
        "name": "Security Training",
        "description": "Cybersecurity awareness training and phishing simulation platforms",
    },
    {
        "name": "Endpoint Security",
        "description": "Endpoint detection and response (EDR) and endpoint protection platforms",
    },
]


def migrate_company_table():
    """
    Migration function to add new optional fields to the Company table if they don't exist.
    This should be run before setup_default_roles().

    Note: For new installations, the SQLAlchemy model already includes all columns,
    so this migration will typically be skipped.
    """
    if engine is None:
        return

    try:
        with get_db_session() as session:
            # List of columns to add with their definitions
            columns_to_add = [
                ("status", "BOOLEAN DEFAULT 1"),
                ("address", "TEXT"),
                ("phone_number", "TEXT"),
                ("email", "TEXT"),
                ("website", "TEXT"),
                ("city", "TEXT"),
                ("state", "TEXT"),
                ("zip_code", "TEXT"),
                ("country", "TEXT"),
                ("notes", "TEXT"),
                ("user_limit", "INTEGER DEFAULT 1"),
                # Token-based billing columns
                ("token_balance", "INTEGER DEFAULT 0"),
                ("token_balance_usd", "REAL DEFAULT 0.0"),
                ("tokens_used_total", "INTEGER DEFAULT 0"),
                ("last_low_balance_warning", "INTEGER"),
                # Auto top-up subscription columns
                ("auto_topup_enabled", "BOOLEAN DEFAULT 0"),
                ("auto_topup_amount_usd", "REAL"),
                ("stripe_customer_id", "TEXT"),
                ("stripe_subscription_id", "TEXT"),
                # Per-app billing tracking
                ("app_name", "TEXT"),
                ("last_subscription_billing_date", "TIMESTAMP"),
                # Trial credits tracking
                ("trial_credits_granted", "REAL"),
                ("trial_credits_granted_at", "TIMESTAMP"),
                ("trial_domain", "TEXT"),
            ]

            if DATABASE_TYPE == "sqlite":
                # For SQLite, check existing columns
                result = session.execute(text("PRAGMA table_info(Company)"))
                existing_columns = [row[1] for row in result.fetchall()]

                for column_name, column_def in columns_to_add:
                    if column_name not in existing_columns:
                        session.execute(
                            text(
                                f"ALTER TABLE Company ADD COLUMN {column_name} {column_def}"
                            )
                        )
                        session.commit()
            else:
                # For PostgreSQL, check existing columns
                for column_name, _ in columns_to_add:
                    result = session.execute(
                        text(
                            """
                            SELECT column_name 
                            FROM information_schema.columns 
                            WHERE table_name = 'Company' AND column_name = :column_name
                        """
                        ),
                        {"column_name": column_name},
                    )

                    if not result.fetchone():
                        # Convert SQLite column definition to PostgreSQL
                        if column_name == "status":
                            pg_column_def = "BOOLEAN DEFAULT true"
                        elif column_name == "user_limit":
                            pg_column_def = "INTEGER DEFAULT 1"
                        elif column_name == "token_balance":
                            pg_column_def = "INTEGER DEFAULT 0"
                        elif column_name == "token_balance_usd":
                            pg_column_def = "DOUBLE PRECISION DEFAULT 0.0"
                        elif column_name == "tokens_used_total":
                            pg_column_def = "INTEGER DEFAULT 0"
                        elif column_name == "last_low_balance_warning":
                            pg_column_def = "INTEGER"
                        elif column_name == "auto_topup_enabled":
                            pg_column_def = "BOOLEAN DEFAULT false"
                        elif column_name == "auto_topup_amount_usd":
                            pg_column_def = "DOUBLE PRECISION"
                        elif column_name in (
                            "last_subscription_billing_date",
                            "trial_credits_granted_at",
                        ):
                            pg_column_def = "TIMESTAMP"
                        elif column_name == "trial_credits_granted":
                            pg_column_def = "DOUBLE PRECISION"
                        else:
                            pg_column_def = "TEXT"

                        session.execute(
                            text(
                                f'ALTER TABLE "Company" ADD COLUMN {column_name} {pg_column_def}'
                            )
                        )
                        session.commit()

    except Exception as e:
        logging.debug(f"Company table migration completed or not needed: {e}")


def migrate_payment_transaction_table():
    """
    Migration function to add token_amount and app_name columns to payment_transaction table.
    This supports the new token-based billing system and per-app billing tracking.
    """
    if engine is None:
        return

    try:
        with get_db_session() as session:
            columns_to_add = [
                ("token_amount", "INTEGER"),
                ("app_name", "TEXT"),
            ]

            if DATABASE_TYPE == "sqlite":
                # For SQLite, check if column exists
                result = session.execute(text("PRAGMA table_info(payment_transaction)"))
                existing_columns = [row[1] for row in result.fetchall()]

                for column_name, column_def in columns_to_add:
                    if column_name not in existing_columns:
                        session.execute(
                            text(
                                f"ALTER TABLE payment_transaction ADD COLUMN {column_name} {column_def}"
                            )
                        )
                        session.commit()
            else:
                # For PostgreSQL, check if column exists
                for column_name, column_def in columns_to_add:
                    result = session.execute(
                        text(
                            """
                            SELECT column_name 
                            FROM information_schema.columns 
                            WHERE table_name = 'payment_transaction' AND column_name = :column_name
                        """
                        ),
                        {"column_name": column_name},
                    )

                    if not result.fetchone():
                        session.execute(
                            text(
                                f"ALTER TABLE payment_transaction ADD COLUMN {column_name} {column_def}"
                            )
                        )
                        session.commit()

    except Exception as e:
        logging.debug(
            f"payment_transaction table migration completed or not needed: {e}"
        )


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
    import sys

    extension_models = []

    # Collect all extension directories to search
    extensions_dirs = []

    # Default extensions directory
    default_ext_dir = os.path.join(os.path.dirname(__file__), "extensions")
    if os.path.exists(default_ext_dir):
        extensions_dirs.append(default_ext_dir)

    # Also check EXTENSIONS_HUB for local paths
    hub_urls = os.environ.get("EXTENSIONS_HUB", "")
    if hub_urls:
        for source in hub_urls.split(","):
            source = source.strip()
            if source and not source.startswith("http"):
                # It's a local path
                abs_path = os.path.abspath(os.path.expanduser(source))
                if os.path.exists(abs_path) and os.path.isdir(abs_path):
                    extensions_dirs.append(abs_path)
                    # Make sure it's in sys.path
                    if abs_path not in sys.path:
                        sys.path.insert(0, abs_path)

    for extensions_dir in extensions_dirs:
        command_files = glob.glob(os.path.join(extensions_dir, "*.py"))

        for command_file in command_files:
            module_name = os.path.splitext(os.path.basename(command_file))[0]
            try:
                # Try to import from the directory
                if extensions_dir == default_ext_dir:
                    module = importlib.import_module(f"extensions.{module_name}")
                else:
                    module = importlib.import_module(module_name)

                # Check if the module has any classes that inherit from ExtensionDatabaseMixin
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if isinstance(attr, type) and issubclass(
                        attr, ExtensionDatabaseMixin
                    ):
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
    # First, ensure all tables in Base.metadata are created (includes association tables)
    try:
        Base.metadata.create_all(engine, checkfirst=True)
    except Exception as e:
        logging.debug(f"Error in create_all for extension tables: {e}")

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
    """Migrate existing extensions to use their defined categories"""
    import importlib
    import sys
    import os

    try:
        with get_db_session() as session:
            # Get all extensions from the database
            extensions = session.query(Extension).all()
            for extension in extensions:
                # Special case for Custom Automation
                if extension.name == "Custom Automation":
                    core_abilities_category = (
                        session.query(ExtensionCategory)
                        .filter_by(name="Core Abilities")
                        .first()
                    )
                    if core_abilities_category:
                        extension.category_id = core_abilities_category.id
                    continue

                # Try to find and load the extension module to get its category
                category_name = None

                # Convert extension name to module name
                module_name = extension.name.lower().replace(" ", "_").replace("-", "_")
                extension_path = f"extensions.{module_name}"

                logging.debug(f"Trying to import: {extension_path}")

                try:
                    module = importlib.import_module(extension_path)
                    logging.debug(f"Successfully imported: {extension_path}")

                    # Find the extension class - it could have various naming patterns
                    possible_class_names = [
                        extension.name.replace(" ", "").replace(
                            "-", ""
                        ),  # Remove spaces/hyphens
                        extension.name.replace(" ", "_").replace(
                            "-", "_"
                        ),  # Replace with underscores
                        module_name,  # Same as module name
                        module_name.title().replace(
                            "_", ""
                        ),  # Title case without underscores
                    ]

                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if isinstance(attr, type) and hasattr(attr, "CATEGORY"):
                            # Check if this class name matches any of our possible patterns
                            attr_name_lower = attr_name.lower()
                            for possible_name in possible_class_names:
                                if attr_name_lower == possible_name.lower():
                                    category_name = attr.CATEGORY
                                    break

                            if category_name:
                                break

                    if not category_name:
                        # If we didn't find a matching class, try the first class with CATEGORY
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if isinstance(attr, type) and hasattr(attr, "CATEGORY"):
                                category_name = attr.CATEGORY
                                break

                except (ImportError, AttributeError) as e:
                    pass

                # If we found a category, update the extension
                if category_name:
                    target_category = (
                        session.query(ExtensionCategory)
                        .filter_by(name=category_name)
                        .first()
                    )
                    if target_category:
                        extension.category_id = target_category.id
                    else:
                        # Default to Productivity if category doesn't exist
                        default_category = (
                            session.query(ExtensionCategory)
                            .filter_by(name="Productivity")
                            .first()
                        )
                        if default_category:
                            extension.category_id = default_category.id
                else:
                    # If we couldn't determine the category, default to Productivity
                    default_category = (
                        session.query(ExtensionCategory)
                        .filter_by(name="Productivity")
                        .first()
                    )
                    if default_category:
                        extension.category_id = default_category.id

            session.commit()
    except Exception as e:
        logging.error(f"Error migrating extensions to new categories: {e}")
        import traceback

        logging.error(traceback.format_exc())


def migrate_user_table():
    """
    Migration function to add new optional fields to the User table if they don't exist.
    """
    if engine is None:
        return

    try:
        with get_db_session() as session:
            columns_to_add = [
                ("tos_accepted_at", "TIMESTAMP"),
            ]

            if DATABASE_TYPE == "sqlite":
                result = session.execute(text("PRAGMA table_info(user)"))
                existing_columns = [row[1] for row in result.fetchall()]

                for column_name, column_def in columns_to_add:
                    if column_name not in existing_columns:
                        session.execute(
                            text(
                                f"ALTER TABLE user ADD COLUMN {column_name} {column_def}"
                            )
                        )
                        session.commit()
            else:
                # PostgreSQL
                for column_name, column_def in columns_to_add:
                    result = session.execute(
                        text(
                            """
                            SELECT column_name FROM information_schema.columns 
                            WHERE table_name = 'user' AND column_name = :column_name
                            """
                        ),
                        {"column_name": column_name},
                    )
                    if not result.fetchone():
                        session.execute(
                            text(
                                f'ALTER TABLE "user" ADD COLUMN {column_name} {column_def}'
                            )
                        )
                        session.commit()
    except Exception as e:
        logging.error(f"Error migrating user table: {e}")


def migrate_conversation_table():
    """
    Migration function to add new optional fields to the Conversation table if they don't exist.
    Adds pin_order column for persistent conversation pinning.
    """
    if engine is None:
        return

    try:
        with get_db_session() as session:
            columns_to_add = [
                ("pin_order", "INTEGER"),
            ]

            if DATABASE_TYPE == "sqlite":
                result = session.execute(text("PRAGMA table_info(conversation)"))
                existing_columns = [row[1] for row in result.fetchall()]

                for column_name, column_def in columns_to_add:
                    if column_name not in existing_columns:
                        session.execute(
                            text(
                                f"ALTER TABLE conversation ADD COLUMN {column_name} {column_def}"
                            )
                        )
                        session.commit()
            else:
                # PostgreSQL
                for column_name, column_def in columns_to_add:
                    result = session.execute(
                        text(
                            """
                            SELECT column_name FROM information_schema.columns 
                            WHERE table_name = 'conversation' AND column_name = :column_name
                            """
                        ),
                        {"column_name": column_name},
                    )
                    if not result.fetchone():
                        session.execute(
                            text(
                                f"ALTER TABLE conversation ADD COLUMN {column_name} {column_def}"
                            )
                        )
                        session.commit()
    except Exception as e:
        logging.error(f"Error migrating conversation table: {e}")


def migrate_discarded_context_table():
    """
    Migration function to create the discarded_context table if it doesn't exist.
    This table stores discarded context items for token optimization with the ability
    to retrieve them later if needed.
    """
    if engine is None:
        return

    try:
        with get_db_session() as session:
            if DATABASE_TYPE == "sqlite":
                # Check if table exists
                result = session.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='discarded_context'"
                    )
                )
                if not result.fetchone():
                    session.execute(
                        text(
                            """
                            CREATE TABLE discarded_context (
                                id TEXT PRIMARY KEY,
                                message_id TEXT NOT NULL,
                                conversation_id TEXT NOT NULL,
                                reason TEXT NOT NULL,
                                original_content TEXT NOT NULL,
                                discarded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                retrieved_at TIMESTAMP,
                                is_active BOOLEAN DEFAULT 1,
                                FOREIGN KEY (message_id) REFERENCES message(id),
                                FOREIGN KEY (conversation_id) REFERENCES conversation(id)
                            )
                            """
                        )
                    )
                    # Create indexes
                    session.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS idx_discarded_context_message_id ON discarded_context(message_id)"
                        )
                    )
                    session.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS idx_discarded_context_conversation_id ON discarded_context(conversation_id)"
                        )
                    )
                    session.commit()
                    logging.info("Created discarded_context table")
            else:
                # PostgreSQL
                result = session.execute(
                    text(
                        """
                        SELECT table_name FROM information_schema.tables 
                        WHERE table_name = 'discarded_context'
                        """
                    )
                )
                if not result.fetchone():
                    session.execute(
                        text(
                            """
                            CREATE TABLE discarded_context (
                                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                                message_id UUID NOT NULL REFERENCES message(id),
                                conversation_id UUID NOT NULL REFERENCES conversation(id),
                                reason TEXT NOT NULL,
                                original_content TEXT NOT NULL,
                                discarded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                retrieved_at TIMESTAMP,
                                is_active BOOLEAN DEFAULT TRUE
                            )
                            """
                        )
                    )
                    session.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS idx_discarded_context_message_id ON discarded_context(message_id)"
                        )
                    )
                    session.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS idx_discarded_context_conversation_id ON discarded_context(conversation_id)"
                        )
                    )
                    session.commit()
                    logging.info("Created discarded_context table")
    except Exception as e:
        logging.error(f"Error creating discarded_context table: {e}")


def migrate_cleanup_duplicate_wallet_settings():
    """
    Migration function to clean up duplicate Solana wallet settings per agent.
    Keeps only one setting per agent per wallet setting type, preferring ones with values.
    """
    if engine is None:
        return

    try:
        with get_db_session() as session:
            wallet_setting_names = [
                "SOLANA_WALLET_ADDRESS",
                "SOLANA_WALLET_API_KEY",
                "SOLANA_WALLET_PASSPHRASE_API_KEY",
            ]

            total_deleted = 0

            for setting_name in wallet_setting_names:
                # Find all agent_ids that have duplicates for this setting
                if DATABASE_TYPE == "sqlite":
                    duplicates_query = text(
                        """
                        SELECT agent_id, COUNT(*) as cnt
                        FROM agent_setting 
                        WHERE name = :setting_name
                        GROUP BY agent_id
                        HAVING COUNT(*) > 1
                    """
                    )
                else:
                    duplicates_query = text(
                        """
                        SELECT agent_id, COUNT(*) as cnt
                        FROM agent_setting 
                        WHERE name = :setting_name
                        GROUP BY agent_id
                        HAVING COUNT(*) > 1
                    """
                    )

                result = session.execute(
                    duplicates_query, {"setting_name": setting_name}
                )
                agents_with_duplicates = [row[0] for row in result.fetchall()]

                for agent_id in agents_with_duplicates:
                    # Get all settings for this agent and setting name, ordered to prefer ones with values
                    settings = (
                        session.query(AgentSetting)
                        .filter(
                            AgentSetting.agent_id == agent_id,
                            AgentSetting.name == setting_name,
                        )
                        .all()
                    )

                    if len(settings) <= 1:
                        continue

                    # Find the keeper - prefer one with a non-empty value
                    keeper = None
                    for setting in settings:
                        if setting.value:
                            keeper = setting
                            break

                    # If no setting has a value, keep the first one
                    if keeper is None:
                        keeper = settings[0]

                    # Delete all duplicates except the keeper
                    for setting in settings:
                        if setting.id != keeper.id:
                            session.delete(setting)
                            total_deleted += 1

            session.commit()
            if total_deleted > 0:
                logging.info(f"Cleaned up {total_deleted} duplicate wallet settings")

    except Exception as e:
        logging.error(f"Error cleaning up duplicate wallet settings: {e}")


def migrate_extension_settings_tables():
    """
    Migration function to create the server_extension_setting and company_extension_setting
    tables if they don't exist. These tables store hierarchical extension settings that
    cascade: Server → Company → User.
    """
    if engine is None:
        return

    try:
        with get_db_session() as session:
            if DATABASE_TYPE == "sqlite":
                # Check if server_extension_setting table exists
                result = session.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='server_extension_setting'"
                    )
                )
                if not result.fetchone():
                    session.execute(
                        text(
                            """
                            CREATE TABLE server_extension_setting (
                                id TEXT PRIMARY KEY,
                                extension_name TEXT NOT NULL,
                                setting_key TEXT NOT NULL,
                                setting_value TEXT,
                                is_sensitive BOOLEAN DEFAULT 0,
                                description TEXT,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                UNIQUE(extension_name, setting_key)
                            )
                            """
                        )
                    )
                    session.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS idx_server_ext_setting_name ON server_extension_setting(extension_name)"
                        )
                    )
                    session.commit()
                    logging.info("Created server_extension_setting table")

                # Check if company_extension_setting table exists
                result = session.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='company_extension_setting'"
                    )
                )
                if not result.fetchone():
                    session.execute(
                        text(
                            """
                            CREATE TABLE company_extension_setting (
                                id TEXT PRIMARY KEY,
                                company_id TEXT NOT NULL,
                                extension_name TEXT NOT NULL,
                                setting_key TEXT NOT NULL,
                                setting_value TEXT,
                                is_sensitive BOOLEAN DEFAULT 0,
                                description TEXT,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                FOREIGN KEY (company_id) REFERENCES company(id),
                                UNIQUE(company_id, extension_name, setting_key)
                            )
                            """
                        )
                    )
                    session.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS idx_company_ext_setting_company ON company_extension_setting(company_id)"
                        )
                    )
                    session.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS idx_company_ext_setting_name ON company_extension_setting(extension_name)"
                        )
                    )
                    session.commit()
                    logging.info("Created company_extension_setting table")

                # Check if server_extension_command table exists
                result = session.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='server_extension_command'"
                    )
                )
                if not result.fetchone():
                    session.execute(
                        text(
                            """
                            CREATE TABLE server_extension_command (
                                id TEXT PRIMARY KEY,
                                extension_name TEXT NOT NULL,
                                command_name TEXT NOT NULL,
                                enabled BOOLEAN DEFAULT 0,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                UNIQUE(extension_name, command_name)
                            )
                            """
                        )
                    )
                    session.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS idx_server_ext_command_name ON server_extension_command(extension_name)"
                        )
                    )
                    session.commit()
                    logging.info("Created server_extension_command table")

                # Check if company_extension_command table exists
                result = session.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='company_extension_command'"
                    )
                )
                if not result.fetchone():
                    session.execute(
                        text(
                            """
                            CREATE TABLE company_extension_command (
                                id TEXT PRIMARY KEY,
                                company_id TEXT NOT NULL,
                                extension_name TEXT NOT NULL,
                                command_name TEXT NOT NULL,
                                enabled BOOLEAN DEFAULT 0,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                FOREIGN KEY (company_id) REFERENCES company(id),
                                UNIQUE(company_id, extension_name, command_name)
                            )
                            """
                        )
                    )
                    session.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS idx_company_ext_command_company ON company_extension_command(company_id)"
                        )
                    )
                    session.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS idx_company_ext_command_name ON company_extension_command(extension_name)"
                        )
                    )
                    session.commit()
                    logging.info("Created company_extension_command table")
            else:
                # PostgreSQL
                result = session.execute(
                    text(
                        """
                        SELECT table_name FROM information_schema.tables 
                        WHERE table_name = 'server_extension_setting'
                        """
                    )
                )
                if not result.fetchone():
                    session.execute(
                        text(
                            """
                            CREATE TABLE server_extension_setting (
                                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                                extension_name TEXT NOT NULL,
                                setting_key TEXT NOT NULL,
                                setting_value TEXT,
                                is_sensitive BOOLEAN DEFAULT FALSE,
                                description TEXT,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                CONSTRAINT uix_server_ext_setting UNIQUE(extension_name, setting_key)
                            )
                            """
                        )
                    )
                    session.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS idx_server_ext_setting_name ON server_extension_setting(extension_name)"
                        )
                    )
                    session.commit()
                    logging.info("Created server_extension_setting table")

                result = session.execute(
                    text(
                        """
                        SELECT table_name FROM information_schema.tables 
                        WHERE table_name = 'company_extension_setting'
                        """
                    )
                )
                if not result.fetchone():
                    session.execute(
                        text(
                            """
                            CREATE TABLE company_extension_setting (
                                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                                company_id UUID NOT NULL REFERENCES company(id),
                                extension_name TEXT NOT NULL,
                                setting_key TEXT NOT NULL,
                                setting_value TEXT,
                                is_sensitive BOOLEAN DEFAULT FALSE,
                                description TEXT,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                CONSTRAINT uix_company_ext_setting UNIQUE(company_id, extension_name, setting_key)
                            )
                            """
                        )
                    )
                    session.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS idx_company_ext_setting_company ON company_extension_setting(company_id)"
                        )
                    )
                    session.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS idx_company_ext_setting_name ON company_extension_setting(extension_name)"
                        )
                    )
                    session.commit()
                    logging.info("Created company_extension_setting table")

                # Check if server_extension_command table exists
                result = session.execute(
                    text(
                        """
                        SELECT table_name FROM information_schema.tables 
                        WHERE table_name = 'server_extension_command'
                        """
                    )
                )
                if not result.fetchone():
                    session.execute(
                        text(
                            """
                            CREATE TABLE server_extension_command (
                                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                                extension_name TEXT NOT NULL,
                                command_name TEXT NOT NULL,
                                enabled BOOLEAN DEFAULT FALSE,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                CONSTRAINT uix_server_ext_command UNIQUE(extension_name, command_name)
                            )
                            """
                        )
                    )
                    session.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS idx_server_ext_command_name ON server_extension_command(extension_name)"
                        )
                    )
                    session.commit()
                    logging.info("Created server_extension_command table")

                # Check if company_extension_command table exists
                result = session.execute(
                    text(
                        """
                        SELECT table_name FROM information_schema.tables 
                        WHERE table_name = 'company_extension_command'
                        """
                    )
                )
                if not result.fetchone():
                    session.execute(
                        text(
                            """
                            CREATE TABLE company_extension_command (
                                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                                company_id UUID NOT NULL REFERENCES company(id),
                                extension_name TEXT NOT NULL,
                                command_name TEXT NOT NULL,
                                enabled BOOLEAN DEFAULT FALSE,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                CONSTRAINT uix_company_ext_command UNIQUE(company_id, extension_name, command_name)
                            )
                            """
                        )
                    )
                    session.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS idx_company_ext_command_company ON company_extension_command(company_id)"
                        )
                    )
                    session.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS idx_company_ext_command_name ON company_extension_command(extension_name)"
                        )
                    )
                    session.commit()
                    logging.info("Created company_extension_command table")
    except Exception as e:
        logging.error(f"Error creating extension settings tables: {e}")


def migrate_server_config_categories():
    """
    Migration function to update server config categories from definitions.
    This ensures that if category definitions are changed (e.g., splitting 'storage'
    into 'storage_aws', 'storage_azure', 'storage_b2'), existing database records
    are updated to match the new structure.
    """
    if engine is None:
        return

    try:
        with get_db_session() as session:
            # Build a map of config name -> category from definitions
            config_category_map = {
                d["name"]: d["category"] for d in SERVER_CONFIG_DEFINITIONS
            }

            # Get all server configs
            configs = session.query(ServerConfig).all()
            updated_count = 0

            for config in configs:
                expected_category = config_category_map.get(config.name)
                if expected_category and config.category != expected_category:
                    old_category = config.category
                    config.category = expected_category
                    updated_count += 1
                    logging.debug(
                        f"Updated server config '{config.name}' category: {old_category} -> {expected_category}"
                    )

            if updated_count > 0:
                session.commit()
                logging.info(
                    f"Updated {updated_count} server config categories to match definitions"
                )

    except Exception as e:
        logging.error(f"Error migrating server config categories: {e}")


def migrate_company_storage_settings_table():
    """
    Migration function to create the company_storage_setting table.
    This allows companies to configure their own cloud storage for agent workspaces.
    """
    if engine is None:
        return

    try:
        inspector = inspect(engine)

        # Check if table exists
        if "company_storage_setting" not in inspector.get_table_names():
            CompanyStorageSetting.__table__.create(engine)
            logging.info("Created company_storage_setting table")
        else:
            # Table exists, check for missing columns
            existing_columns = {
                col["name"] for col in inspector.get_columns("company_storage_setting")
            }
            expected_columns = {
                "id",
                "company_id",
                "storage_backend",
                "storage_container",
                "aws_access_key_id",
                "aws_secret_access_key",
                "aws_region",
                "s3_endpoint",
                "s3_bucket",
                "azure_storage_account_name",
                "azure_storage_key",
                "b2_key_id",
                "b2_application_key",
                "b2_region",
                "created_at",
                "updated_at",
            }
            missing_columns = expected_columns - existing_columns

            if missing_columns:
                with engine.begin() as connection:
                    for col_name in missing_columns:
                        col = getattr(CompanyStorageSetting, col_name, None)
                        if col is not None:
                            col_type = col.type.compile(engine.dialect)
                            default = "NULL"
                            connection.execute(
                                text(
                                    f"ALTER TABLE company_storage_setting ADD COLUMN {col_name} {col_type} DEFAULT {default}"
                                )
                            )
                            logging.info(
                                f"Added column {col_name} to company_storage_setting table"
                            )
    except Exception as e:
        logging.error(f"Error migrating company_storage_setting table: {e}")


def migrate_role_table():
    """
    Migration function to add new columns to the Role table and ensure
    all default roles exist with correct data.
    """
    if engine is None:
        return

    try:
        with get_db_session() as session:
            columns_to_add = [
                ("display_order", "INTEGER DEFAULT 100"),
            ]

            if DATABASE_TYPE == "sqlite":
                result = session.execute(text('PRAGMA table_info("Role")'))
                existing_columns = [row[1] for row in result.fetchall()]

                for column_name, column_def in columns_to_add:
                    if column_name not in existing_columns:
                        session.execute(
                            text(
                                f'ALTER TABLE "Role" ADD COLUMN {column_name} {column_def}'
                            )
                        )
                        session.commit()
                        logging.info(f"Added column {column_name} to Role table")
            else:
                # PostgreSQL
                for column_name, column_def in columns_to_add:
                    result = session.execute(
                        text(
                            """
                            SELECT column_name FROM information_schema.columns 
                            WHERE table_name = 'Role' AND column_name = :column_name
                            """
                        ),
                        {"column_name": column_name},
                    )
                    if not result.fetchone():
                        session.execute(
                            text(
                                f'ALTER TABLE "Role" ADD COLUMN {column_name} {column_def}'
                            )
                        )
                        session.commit()
                        logging.info(f"Added column {column_name} to Role table")
    except Exception as e:
        logging.error(f"Error migrating Role table: {e}")


def setup_default_roles():
    """
    Set up default system roles. Creates new roles if they don't exist,
    and updates existing roles with any new fields (like display_order).
    """
    with get_session() as db:
        for role in default_roles:
            existing_role = db.query(UserRole).filter_by(id=role["id"]).first()
            if not existing_role:
                new_role = UserRole(**role)
                db.add(new_role)
                logging.info(f"Created default role: {role['name']} (id={role['id']})")
            else:
                # Update existing role with any new fields
                updated = False
                if existing_role.display_order != role.get("display_order"):
                    existing_role.display_order = role.get("display_order", 100)
                    updated = True
                if existing_role.friendly_name != role.get("friendly_name"):
                    existing_role.friendly_name = role.get("friendly_name")
                    updated = True
                if updated:
                    logging.info(
                        f"Updated default role: {role['name']} (id={role['id']})"
                    )
        db.commit()


def setup_default_scopes():
    """
    Set up the default scopes in the database.
    Scopes define granular permissions that can be assigned to roles.
    Also generates per-extension scopes dynamically.
    """
    # Combine static default scopes with dynamically generated extension scopes
    extension_scopes = generate_extension_scopes()
    all_scopes = default_scopes + extension_scopes

    with get_session() as db:
        for scope_data in all_scopes:
            existing_scope = db.query(Scope).filter_by(name=scope_data["name"]).first()
            if not existing_scope:
                new_scope = Scope(
                    name=scope_data["name"],
                    resource=scope_data["resource"],
                    action=scope_data["action"],
                    description=scope_data.get("description"),
                    category=scope_data.get("category"),
                    is_system=True,
                )
                db.add(new_scope)
        db.commit()
        logging.info(
            f"Set up {len(default_scopes)} default scopes + {len(extension_scopes)} extension scopes"
        )


def setup_default_role_scopes():
    """
    Set up the mapping between default roles and their scopes.
    This defines what permissions each default role level has.
    """
    with get_session() as db:
        # Get all scopes for pattern matching
        all_scopes = db.query(Scope).all()
        scope_map = {s.name: s for s in all_scopes}

        for role_id, scope_patterns in default_role_scopes.items():
            # Get the role
            role = db.query(UserRole).filter_by(id=role_id).first()
            if not role:
                continue

            # Expand wildcard patterns
            scopes_to_assign = set()
            for pattern in scope_patterns:
                if pattern == "*":
                    # All scopes
                    scopes_to_assign.update(scope_map.keys())
                elif pattern == "ext:*":
                    # All extension scopes
                    for scope_name in scope_map.keys():
                        if scope_name.startswith("ext:"):
                            scopes_to_assign.add(scope_name)
                elif pattern.startswith("ext:*:"):
                    # Action wildcard for all extensions (e.g., "ext:*:read")
                    action = pattern.split(":")[-1]
                    for scope_name in scope_map.keys():
                        if scope_name.startswith("ext:") and scope_name.endswith(
                            f":{action}"
                        ):
                            scopes_to_assign.add(scope_name)
                elif pattern.endswith(":*"):
                    # Resource wildcard (e.g., "agents:*", "ext:github:*")
                    resource = pattern[:-2]
                    for scope_name in scope_map.keys():
                        if scope_name.startswith(f"{resource}:"):
                            scopes_to_assign.add(scope_name)
                else:
                    # Exact match
                    if pattern in scope_map:
                        scopes_to_assign.add(pattern)

            # Create DefaultRoleScope entries
            for scope_name in scopes_to_assign:
                scope = scope_map.get(scope_name)
                if not scope:
                    continue

                existing = (
                    db.query(DefaultRoleScope)
                    .filter_by(role_id=role_id, scope_id=scope.id)
                    .first()
                )
                if not existing:
                    role_scope = DefaultRoleScope(
                        role_id=role_id,
                        scope_id=scope.id,
                    )
                    db.add(role_scope)

        db.commit()
        logging.info("Set up default role scope mappings")


def reseed_extension_scopes():
    """
    Re-seed extension scopes when new extensions are added (e.g., via hot-reload).
    This function:
    1. Creates any missing extension scopes in the Scope table
    2. Assigns new scopes to roles based on default_role_scopes patterns

    Returns:
        Dict with counts of scopes and role assignments created
    """
    results = {
        "scopes_created": 0,
        "role_assignments_created": 0,
        "errors": [],
    }

    try:
        # Generate all extension scopes that should exist
        extension_scopes = generate_extension_scopes()

        with get_session() as db:
            # Step 1: Create any missing scopes
            existing_scope_names = {s.name for s in db.query(Scope.name).all()}

            for scope_data in extension_scopes:
                if scope_data["name"] not in existing_scope_names:
                    new_scope = Scope(
                        name=scope_data["name"],
                        resource=scope_data["resource"],
                        action=scope_data["action"],
                        description=scope_data.get("description"),
                        category=scope_data.get("category"),
                        is_system=True,
                    )
                    db.add(new_scope)
                    results["scopes_created"] += 1

            db.commit()

            # Step 2: Get all scopes (including newly created ones)
            all_scopes = db.query(Scope).all()
            scope_map = {s.name: s for s in all_scopes}

            # Step 3: Assign new extension scopes to roles based on patterns
            for role_id, scope_patterns in default_role_scopes.items():
                # Get the role
                role = db.query(UserRole).filter_by(id=role_id).first()
                if not role:
                    continue

                # Get existing scope assignments for this role
                existing_assignments = {
                    rs.scope_id
                    for rs in db.query(DefaultRoleScope)
                    .filter_by(role_id=role_id)
                    .all()
                }

                # Expand wildcard patterns
                scopes_to_assign = set()
                for pattern in scope_patterns:
                    if pattern == "*":
                        # All scopes
                        scopes_to_assign.update(scope_map.keys())
                    elif pattern == "ext:*":
                        # All extension scopes
                        for scope_name in scope_map.keys():
                            if scope_name.startswith("ext:"):
                                scopes_to_assign.add(scope_name)
                    elif pattern.startswith("ext:*:"):
                        # Action wildcard for all extensions (e.g., "ext:*:read")
                        action = pattern.split(":")[-1]
                        for scope_name in scope_map.keys():
                            if scope_name.startswith("ext:") and scope_name.endswith(
                                f":{action}"
                            ):
                                scopes_to_assign.add(scope_name)
                    elif pattern.endswith(":*"):
                        # Resource wildcard (e.g., "agents:*", "ext:github:*")
                        resource = pattern[:-2]
                        for scope_name in scope_map.keys():
                            if scope_name.startswith(f"{resource}:"):
                                scopes_to_assign.add(scope_name)
                    else:
                        # Exact match
                        if pattern in scope_map:
                            scopes_to_assign.add(pattern)

                # Create missing DefaultRoleScope entries
                for scope_name in scopes_to_assign:
                    scope = scope_map.get(scope_name)
                    if not scope:
                        continue

                    if scope.id not in existing_assignments:
                        role_scope = DefaultRoleScope(
                            role_id=role_id,
                            scope_id=scope.id,
                        )
                        db.add(role_scope)
                        results["role_assignments_created"] += 1

            db.commit()

        logging.info(
            f"Reseeded extension scopes: {results['scopes_created']} scopes created, "
            f"{results['role_assignments_created']} role assignments created"
        )

    except Exception as e:
        results["errors"].append(str(e))
        logging.error(f"Error reseeding extension scopes: {e}")

    return results


def migrate_response_cache_table():
    """
    Migration function to create the response_cache table for shared caching across workers.
    This table stores cached API responses with automatic TTL expiration.
    """
    if engine is None:
        return

    try:
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        if "response_cache" not in existing_tables:
            ResponseCache.__table__.create(engine)
            logging.info("Created response_cache table")
        else:
            logging.debug("response_cache table already exists")

    except Exception as e:
        logging.error(f"Error migrating response_cache table: {e}")


def cleanup_expired_cache():
    """
    Remove expired cache entries from the database.
    Should be called periodically (e.g., on startup, or via scheduled task).
    """
    if engine is None:
        return 0

    try:
        with get_db_session() as session:
            from datetime import datetime

            result = session.execute(
                text("DELETE FROM response_cache WHERE expires_at < :now"),
                {"now": datetime.utcnow()},
            )
            deleted_count = result.rowcount
            session.commit()

            if deleted_count > 0:
                logging.info(f"Cleaned up {deleted_count} expired cache entries")

            return deleted_count
    except Exception as e:
        logging.warning(f"Error cleaning up expired cache: {e}")
        return 0


def migrate_task_item_table():
    """
    Migration function to add task_type, command_script, deployment_id, and target_machines
    columns to the task_item table. These support the new scheduled task types:
    - 'prompt' (default): AI agent prompt execution
    - 'command': Shell command/script execution on machines
    - 'deployment': Deployment library script execution on machines
    """
    if engine is None:
        return

    try:
        with get_db_session() as session:
            columns_to_add = [
                ("task_type", "TEXT", "'prompt'"),  # Default to 'prompt'
                ("command_script", "TEXT", None),
                ("deployment_id", "TEXT", None),
                ("target_machines", "TEXT", None),  # JSON array of machine IDs
            ]

            if DATABASE_TYPE == "sqlite":
                # For SQLite, check if column exists
                result = session.execute(text("PRAGMA table_info(task_item)"))
                existing_columns = [row[1] for row in result.fetchall()]

                for column_name, column_def, default_value in columns_to_add:
                    if column_name not in existing_columns:
                        if default_value:
                            session.execute(
                                text(
                                    f"ALTER TABLE task_item ADD COLUMN {column_name} {column_def} DEFAULT {default_value}"
                                )
                            )
                        else:
                            session.execute(
                                text(
                                    f"ALTER TABLE task_item ADD COLUMN {column_name} {column_def}"
                                )
                            )
                        session.commit()
                        logging.info(f"Added column {column_name} to task_item table")
            else:
                # For PostgreSQL, check if column exists
                for column_name, column_def, default_value in columns_to_add:
                    result = session.execute(
                        text(
                            """
                            SELECT column_name 
                            FROM information_schema.columns 
                            WHERE table_name = 'task_item' AND column_name = :column_name
                        """
                        ),
                        {"column_name": column_name},
                    )

                    if not result.fetchone():
                        if default_value:
                            session.execute(
                                text(
                                    f"ALTER TABLE task_item ADD COLUMN {column_name} {column_def} DEFAULT {default_value}"
                                )
                            )
                        else:
                            session.execute(
                                text(
                                    f"ALTER TABLE task_item ADD COLUMN {column_name} {column_def}"
                                )
                            )
                        session.commit()
                        logging.info(f"Added column {column_name} to task_item table")

            logging.info("Task item table migration complete")

    except Exception as e:
        logging.error(f"Error migrating task item table: {e}")


def migrate_tiered_prompts_chains_tables():
    """
    Migration function to create the tiered prompts and chains tables.
    These tables implement a hierarchical configuration system:
    Server → Company → User (each level can override the previous).

    Tables created:
    - server_prompt_category, server_prompt, server_prompt_argument
    - server_chain, server_chain_step, server_chain_step_argument
    - company_prompt_category, company_prompt, company_prompt_argument
    - company_chain, company_chain_step, company_chain_step_argument
    - user_prompt_override, user_chain_override (for tracking customizations)
    """
    if engine is None:
        return

    tables_to_create = [
        ServerPromptCategory,
        ServerPrompt,
        ServerPromptArgument,
        ServerChain,
        ServerChainStep,
        ServerChainStepArgument,
        CompanyPromptCategory,
        CompanyPrompt,
        CompanyPromptArgument,
        CompanyChain,
        CompanyChainStep,
        CompanyChainStepArgument,
        UserPromptOverride,
        UserChainOverride,
    ]

    try:
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        for table_class in tables_to_create:
            table_name = table_class.__tablename__
            if table_name not in existing_tables:
                try:
                    table_class.__table__.create(engine)
                    logging.info(f"Created table: {table_name}")
                except Exception as table_error:
                    logging.warning(
                        f"Could not create table {table_name}: {table_error}"
                    )
            else:
                logging.debug(f"Table {table_name} already exists")

        logging.info("Tiered prompts and chains tables migration complete")

    except Exception as e:
        logging.error(f"Error migrating tiered prompts and chains tables: {e}")


# Server configuration definitions
# These define all configurable settings and their metadata
SERVER_CONFIG_DEFINITIONS = [
    # ========================================
    # App Settings (includes URIs and general app config)
    # ========================================
    {
        "name": "APP_NAME",
        "category": "app_settings",
        "description": "Application name displayed in the UI",
        "value_type": "string",
        "default_value": "AGiXT",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "APP_DESCRIPTION",
        "category": "app_settings",
        "description": "Application description for SEO and UI",
        "value_type": "string",
        "default_value": "AGiXT is an advanced artificial intelligence agent orchestration platform.",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "AGIXT_FOOTER_MESSAGE",
        "category": "app_settings",
        "description": "Footer message displayed in the UI",
        "value_type": "string",
        "default_value": "AGiXT 2025",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "AGIXT_URI",
        "category": "app_settings",
        "description": "Backend API server URI (internal)",
        "value_type": "url",
        "default_value": "http://localhost:7437",
        "is_sensitive": False,
        "is_required": True,
    },
    {
        "name": "APP_URI",
        "category": "app_settings",
        "description": "Frontend application URI (public facing)",
        "value_type": "url",
        "default_value": "http://localhost:3437",
        "is_sensitive": False,
        "is_required": True,
    },
    {
        "name": "AGIXT_SERVER",
        "category": "app_settings",
        "description": "Backend server URL for frontend to connect to",
        "value_type": "url",
        "default_value": "http://localhost:7437",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "REGISTRATION_DISABLED",
        "category": "app_settings",
        "description": "Disable new user registration",
        "value_type": "boolean",
        "default_value": "false",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "ALLOW_EMAIL_SIGN_IN",
        "category": "app_settings",
        "description": "Allow users to sign in with email magic links",
        "value_type": "boolean",
        "default_value": "true",
        "is_sensitive": False,
        "is_required": False,
    },
    # ========================================
    # AI Provider Settings
    # ========================================
    # OpenAI
    {
        "name": "OPENAI_API_KEY",
        "category": "ai_providers",
        "description": "OpenAI API Key for GPT models. Get at https://platform.openai.com/api-keys",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    {
        "name": "OPENAI_MODEL",
        "category": "ai_providers",
        "description": "Default OpenAI model to use",
        "value_type": "string",
        "default_value": "chatgpt-4o-latest",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "OPENAI_MAX_TOKENS",
        "category": "ai_providers",
        "description": "Maximum tokens for OpenAI responses",
        "value_type": "integer",
        "default_value": "128000",
        "is_sensitive": False,
        "is_required": False,
    },
    # Anthropic
    {
        "name": "ANTHROPIC_API_KEY",
        "category": "ai_providers",
        "description": "Anthropic API Key for Claude models. Get at https://console.anthropic.com/",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    {
        "name": "ANTHROPIC_MODEL",
        "category": "ai_providers",
        "description": "Default Anthropic model to use",
        "value_type": "string",
        "default_value": "claude-sonnet-4-20250514",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "ANTHROPIC_MAX_TOKENS",
        "category": "ai_providers",
        "description": "Maximum tokens for Anthropic responses",
        "value_type": "integer",
        "default_value": "140000",
        "is_sensitive": False,
        "is_required": False,
    },
    # Google Gemini
    {
        "name": "GOOGLE_API_KEY",
        "category": "ai_providers",
        "description": "Google AI API Key for Gemini models. Get at https://aistudio.google.com/apikey",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    {
        "name": "GOOGLE_MODEL",
        "category": "ai_providers",
        "description": "Default Google Gemini model to use",
        "value_type": "string",
        "default_value": "gemini-2.0-flash-exp",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "GOOGLE_MAX_TOKENS",
        "category": "ai_providers",
        "description": "Maximum tokens for Google Gemini responses",
        "value_type": "integer",
        "default_value": "1048000",
        "is_sensitive": False,
        "is_required": False,
    },
    # xAI (Grok)
    {
        "name": "XAI_API_KEY",
        "category": "ai_providers",
        "description": "xAI API Key for Grok models. Get at https://console.x.ai/",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    {
        "name": "XAI_MODEL",
        "category": "ai_providers",
        "description": "Default xAI Grok model to use",
        "value_type": "string",
        "default_value": "grok-beta",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "XAI_MAX_TOKENS",
        "category": "ai_providers",
        "description": "Maximum tokens for xAI responses",
        "value_type": "integer",
        "default_value": "120000",
        "is_sensitive": False,
        "is_required": False,
    },
    # DeepSeek
    {
        "name": "DEEPSEEK_API_KEY",
        "category": "ai_providers",
        "description": "DeepSeek API Key. Get at https://platform.deepseek.com/",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    {
        "name": "DEEPSEEK_MODEL",
        "category": "ai_providers",
        "description": "Default DeepSeek model to use",
        "value_type": "string",
        "default_value": "deepseek-chat",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "DEEPSEEK_MAX_TOKENS",
        "category": "ai_providers",
        "description": "Maximum tokens for DeepSeek responses",
        "value_type": "integer",
        "default_value": "60000",
        "is_sensitive": False,
        "is_required": False,
    },
    # Azure OpenAI
    {
        "name": "AZURE_API_KEY",
        "category": "ai_providers",
        "description": "Azure OpenAI API Key",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    {
        "name": "AZURE_OPENAI_ENDPOINT",
        "category": "ai_providers",
        "description": "Azure OpenAI endpoint URL",
        "value_type": "url",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "AZURE_MODEL",
        "category": "ai_providers",
        "description": "Default Azure OpenAI model/deployment name",
        "value_type": "string",
        "default_value": "gpt-4o",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "AZURE_MAX_TOKENS",
        "category": "ai_providers",
        "description": "Maximum tokens for Azure OpenAI responses",
        "value_type": "integer",
        "default_value": "100000",
        "is_sensitive": False,
        "is_required": False,
    },
    # OpenRouter
    {
        "name": "OPENROUTER_API_KEY",
        "category": "ai_providers",
        "description": "OpenRouter API Key for multi-model access. Get at https://openrouter.ai/keys",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    {
        "name": "OPENROUTER_MODEL",
        "category": "ai_providers",
        "description": "Default OpenRouter model to use",
        "value_type": "string",
        "default_value": "openai/gpt-4o",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "OPENROUTER_MAX_TOKENS",
        "category": "ai_providers",
        "description": "Maximum tokens for OpenRouter responses",
        "value_type": "integer",
        "default_value": "16384",
        "is_sensitive": False,
        "is_required": False,
    },
    # DeepInfra
    {
        "name": "DEEPINFRA_API_KEY",
        "category": "ai_providers",
        "description": "DeepInfra API Key. Get at https://deepinfra.com",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    {
        "name": "DEEPINFRA_MODEL",
        "category": "ai_providers",
        "description": "Default DeepInfra model to use",
        "value_type": "string",
        "default_value": "Qwen/Qwen3-235B-A22B-Instruct-2507",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "DEEPINFRA_MAX_TOKENS",
        "category": "ai_providers",
        "description": "Maximum tokens for DeepInfra responses",
        "value_type": "integer",
        "default_value": "128000",
        "is_sensitive": False,
        "is_required": False,
    },
    # Chutes.ai
    {
        "name": "CHUTES_API_KEY",
        "category": "ai_providers",
        "description": "Chutes.ai API Key. Get at https://chutes.ai/app",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    {
        "name": "CHUTES_MODEL",
        "category": "ai_providers",
        "description": "Default Chutes.ai model to use",
        "value_type": "string",
        "default_value": "Qwen/Qwen3-235B-A22B-Instruct-2507",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "CHUTES_MAX_TOKENS",
        "category": "ai_providers",
        "description": "Maximum tokens for Chutes.ai responses",
        "value_type": "integer",
        "default_value": "128000",
        "is_sensitive": False,
        "is_required": False,
    },
    # Hugging Face
    {
        "name": "HUGGINGFACE_API_KEY",
        "category": "ai_providers",
        "description": "Hugging Face API Key. Get at https://huggingface.co/settings/tokens",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    {
        "name": "HUGGINGFACE_MODEL",
        "category": "ai_providers",
        "description": "Default Hugging Face model to use",
        "value_type": "string",
        "default_value": "HuggingFaceH4/zephyr-7b-beta",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "HUGGINGFACE_MAX_TOKENS",
        "category": "ai_providers",
        "description": "Maximum tokens for Hugging Face responses",
        "value_type": "integer",
        "default_value": "1024",
        "is_sensitive": False,
        "is_required": False,
    },
    # ElevenLabs (TTS)
    {
        "name": "ELEVENLABS_API_KEY",
        "category": "ai_providers",
        "description": "ElevenLabs API Key for text-to-speech. Get at https://elevenlabs.io",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    {
        "name": "ELEVENLABS_VOICE",
        "category": "ai_providers",
        "description": "Default ElevenLabs voice ID",
        "value_type": "string",
        "default_value": "ErXwobaYiN019PkySvjV",
        "is_sensitive": False,
        "is_required": False,
    },
    # ezLocalai (Local AI)
    {
        "name": "EZLOCALAI_URI",
        "category": "ai_providers",
        "description": "ezLocalai server URI for local AI inference",
        "value_type": "url",
        "default_value": "http://localhost:8091/v1/",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "EZLOCALAI_API_KEY",
        "category": "ai_providers",
        "description": "ezLocalai API Key (if required)",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    {
        "name": "EZLOCALAI_VOICE",
        "category": "ai_providers",
        "description": "Default voice for ezLocalai TTS",
        "value_type": "string",
        "default_value": "DukeNukem",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "EZLOCALAI_MAX_TOKENS",
        "category": "ai_providers",
        "description": "Maximum tokens for ezLocalai responses",
        "value_type": "integer",
        "default_value": "16000",
        "is_sensitive": False,
        "is_required": False,
    },
    # General AI Settings
    {
        "name": "SMARTEST_PROVIDER",
        "category": "ai_providers",
        "description": "The AI provider to use for complex reasoning tasks",
        "value_type": "string",
        "default_value": "anthropic",
        "is_sensitive": False,
        "is_required": False,
    },
    # ========================================
    # OAuth Providers
    # ========================================
    # Google OAuth
    {
        "name": "GOOGLE_CLIENT_ID",
        "category": "oauth",
        "description": "Google OAuth Client ID",
        "value_type": "string",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "GOOGLE_CLIENT_SECRET",
        "category": "oauth",
        "description": "Google OAuth Client Secret",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    # Microsoft OAuth
    {
        "name": "MICROSOFT_CLIENT_ID",
        "category": "oauth",
        "description": "Microsoft OAuth Client ID",
        "value_type": "string",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "MICROSOFT_CLIENT_SECRET",
        "category": "oauth",
        "description": "Microsoft OAuth Client Secret",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    {
        "name": "MICROSOFT_TENANT_ID",
        "category": "oauth",
        "description": "Microsoft Tenant ID (required for app-only email sending, use 'common' for multi-tenant apps)",
        "value_type": "string",
        "default_value": "common",
        "is_sensitive": False,
        "is_required": False,
    },
    # GitHub OAuth
    {
        "name": "GITHUB_CLIENT_ID",
        "category": "oauth",
        "description": "GitHub OAuth Client ID",
        "value_type": "string",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "GITHUB_CLIENT_SECRET",
        "category": "oauth",
        "description": "GitHub OAuth Client Secret",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    # OAuth - Discord
    {
        "name": "DISCORD_CLIENT_ID",
        "category": "oauth",
        "description": "Discord OAuth Client ID",
        "value_type": "string",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "DISCORD_CLIENT_SECRET",
        "category": "oauth",
        "description": "Discord OAuth Client Secret",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    # OAuth - X (Twitter)
    {
        "name": "X_CLIENT_ID",
        "category": "oauth",
        "description": "X (Twitter) OAuth Client ID",
        "value_type": "string",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "X_CLIENT_SECRET",
        "category": "oauth",
        "description": "X (Twitter) OAuth Client Secret",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    # OAuth - Tesla
    {
        "name": "TESLA_CLIENT_ID",
        "category": "oauth",
        "description": "Tesla OAuth Client ID",
        "value_type": "string",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "TESLA_CLIENT_SECRET",
        "category": "oauth",
        "description": "Tesla OAuth Client Secret",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    # OAuth - Amazon/Alexa
    {
        "name": "ALEXA_CLIENT_ID",
        "category": "oauth",
        "description": "Amazon Alexa OAuth Client ID",
        "value_type": "string",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "ALEXA_CLIENT_SECRET",
        "category": "oauth",
        "description": "Amazon Alexa OAuth Client Secret",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    # OAuth - Fitbit
    {
        "name": "FITBIT_CLIENT_ID",
        "category": "oauth",
        "description": "Fitbit OAuth Client ID",
        "value_type": "string",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "FITBIT_CLIENT_SECRET",
        "category": "oauth",
        "description": "Fitbit OAuth Client Secret",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    # OAuth - Garmin
    {
        "name": "GARMIN_CLIENT_ID",
        "category": "oauth",
        "description": "Garmin OAuth Client ID",
        "value_type": "string",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "GARMIN_CLIENT_SECRET",
        "category": "oauth",
        "description": "Garmin OAuth Client Secret",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    # OAuth - Meta/Facebook
    {
        "name": "META_APP_ID",
        "category": "oauth",
        "description": "Meta (Facebook) App ID",
        "value_type": "string",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "META_APP_SECRET",
        "category": "oauth",
        "description": "Meta (Facebook) App Secret",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    {
        "name": "META_BUSINESS_ID",
        "category": "oauth",
        "description": "Meta Business ID for WhatsApp integration",
        "value_type": "string",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    # OAuth - Walmart
    {
        "name": "WALMART_CLIENT_ID",
        "category": "oauth",
        "description": "Walmart Marketplace Client ID",
        "value_type": "string",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "WALMART_CLIENT_SECRET",
        "category": "oauth",
        "description": "Walmart Marketplace Client Secret",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    {
        "name": "WALMART_MARKETPLACE_ID",
        "category": "oauth",
        "description": "Walmart Marketplace ID",
        "value_type": "string",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    # AWS Settings
    {
        "name": "AWS_CLIENT_ID",
        "category": "oauth",
        "description": "AWS Cognito Client ID",
        "value_type": "string",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "AWS_CLIENT_SECRET",
        "category": "oauth",
        "description": "AWS Cognito Client Secret",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    {
        "name": "AWS_REGION",
        "category": "oauth",
        "description": "AWS Region for Cognito",
        "value_type": "string",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "AWS_USER_POOL_ID",
        "category": "oauth",
        "description": "AWS Cognito User Pool ID",
        "value_type": "string",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    # ========================================
    # Storage - General
    # ========================================
    {
        "name": "WORKSPACE_RETENTION_DAYS",
        "category": "storage",
        "description": "Number of days to retain inactive workspaces before cleanup (0 = never delete)",
        "value_type": "integer",
        "default_value": "5",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "STORAGE_BACKEND",
        "category": "storage",
        "description": "Storage backend type: s3, azure, b2, or local",
        "value_type": "string",
        "default_value": "s3",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "STORAGE_CONTAINER",
        "category": "storage",
        "description": "Storage container/bucket name",
        "value_type": "string",
        "default_value": "agixt-workspace",
        "is_sensitive": False,
        "is_required": False,
    },
    # ========================================
    # Storage - AWS S3 / MinIO
    # ========================================
    {
        "name": "S3_BUCKET",
        "category": "storage_aws",
        "description": "S3 bucket name",
        "value_type": "string",
        "default_value": "agixt-workspace",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "S3_ENDPOINT",
        "category": "storage_aws",
        "description": "S3 endpoint URL (for MinIO or compatible)",
        "value_type": "url",
        "default_value": "http://minio:9000",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "AWS_ACCESS_KEY_ID",
        "category": "storage_aws",
        "description": "AWS Access Key ID for S3",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    {
        "name": "AWS_SECRET_ACCESS_KEY",
        "category": "storage_aws",
        "description": "AWS Secret Access Key for S3",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    {
        "name": "AWS_STORAGE_REGION",
        "category": "storage_aws",
        "description": "AWS Region for S3 storage",
        "value_type": "string",
        "default_value": "us-east-1",
        "is_sensitive": False,
        "is_required": False,
    },
    # ========================================
    # Storage - Azure Blob
    # ========================================
    {
        "name": "AZURE_STORAGE_ACCOUNT_NAME",
        "category": "storage_azure",
        "description": "Azure Storage Account Name",
        "value_type": "string",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "AZURE_STORAGE_KEY",
        "category": "storage_azure",
        "description": "Azure Storage Account Key",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    # ========================================
    # Storage - Backblaze B2
    # ========================================
    {
        "name": "B2_KEY_ID",
        "category": "storage_b2",
        "description": "Backblaze B2 Key ID",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    {
        "name": "B2_APPLICATION_KEY",
        "category": "storage_b2",
        "description": "Backblaze B2 Application Key",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    {
        "name": "B2_REGION",
        "category": "storage_b2",
        "description": "Backblaze B2 Region",
        "value_type": "string",
        "default_value": "us-west-002",
        "is_sensitive": False,
        "is_required": False,
    },
    # ========================================
    # Billing Settings
    # ========================================
    {
        "name": "STRIPE_API_KEY",
        "category": "billing",
        "description": "Stripe secret API key (starts with sk_). Get at https://dashboard.stripe.com/apikeys",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    {
        "name": "STRIPE_PUBLISHABLE_KEY",
        "category": "billing",
        "description": "Stripe publishable API key (starts with pk_). Get at https://dashboard.stripe.com/apikeys",
        "value_type": "string",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "STRIPE_WEBHOOK_SECRET",
        "category": "billing",
        "description": "Stripe webhook signing secret for verifying webhook events",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    {
        "name": "TOKEN_PRICE_PER_MILLION_USD",
        "category": "billing",
        "description": "Price per million tokens in USD (0 for free, billing disabled)",
        "value_type": "string",
        "default_value": "0.00",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "BILLING_PAUSED",
        "category": "billing",
        "description": "Temporarily pause billing (sets effective price to 0 until toggled back)",
        "value_type": "boolean",
        "default_value": "false",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "MIN_TOKEN_TOPUP_USD",
        "category": "billing",
        "description": "Minimum token top-up amount in USD",
        "value_type": "string",
        "default_value": "10.00",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "LOW_BALANCE_WARNING_THRESHOLD",
        "category": "billing",
        "description": "Token balance at which to warn users",
        "value_type": "integer",
        "default_value": "10000000",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "PAYMENT_WALLET_ADDRESS",
        "category": "billing",
        "description": "Solana wallet address for crypto payments",
        "value_type": "string",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "PAYMENT_SOLANA_RPC_URL",
        "category": "billing",
        "description": "Solana RPC URL for payment verification",
        "value_type": "url",
        "default_value": "https://api.mainnet-beta.solana.com",
        "is_sensitive": False,
        "is_required": False,
    },
    # ========================================
    # Email Settings
    # ========================================
    {
        "name": "EMAIL_VERIFICATION_ENABLED",
        "category": "email",
        "description": "Enable email verification for new users. When enabled, users will receive a verification email and must verify their email address. Requires a configured email provider.",
        "value_type": "boolean",
        "default_value": "false",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "EMAIL_PROVIDER",
        "category": "email",
        "description": "Email provider to use for sending emails (magic links, invitations). Options: auto, sendgrid, mailgun, microsoft, google. 'auto' will use the first configured provider found.",
        "value_type": "string",
        "default_value": "auto",
        "is_sensitive": False,
        "is_required": False,
    },
    # SendGrid
    {
        "name": "SENDGRID_API_KEY",
        "category": "email",
        "description": "SendGrid API key for sending emails. Get at https://app.sendgrid.com/settings/api_keys",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    {
        "name": "SENDGRID_FROM_EMAIL",
        "category": "email",
        "description": "Sender email address for SendGrid (must be verified in SendGrid)",
        "value_type": "string",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    # Mailgun
    {
        "name": "MAILGUN_API_KEY",
        "category": "email",
        "description": "Mailgun API key for sending emails. Get at https://app.mailgun.com/app/account/security/api_keys",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    {
        "name": "MAILGUN_DOMAIN",
        "category": "email",
        "description": "Mailgun domain for sending emails (e.g., mg.yourdomain.com)",
        "value_type": "string",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "MAILGUN_FROM_EMAIL",
        "category": "email",
        "description": "Sender email address for Mailgun emails",
        "value_type": "string",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    # Microsoft Graph API Email (uses OAuth credentials from oauth category)
    {
        "name": "MICROSOFT_EMAIL_ADDRESS",
        "category": "email",
        "description": "Microsoft 365 email address to send from (requires MICROSOFT_CLIENT_ID and MICROSOFT_CLIENT_SECRET in OAuth settings, plus Mail.Send permission)",
        "value_type": "string",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    # Google Gmail API Email (uses OAuth credentials from oauth category)
    {
        "name": "GOOGLE_EMAIL_ADDRESS",
        "category": "email",
        "description": "Gmail address to send from (requires GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in OAuth settings, plus Gmail API enabled)",
        "value_type": "string",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    # ========================================
    # Extensions Hub
    # ========================================
    {
        "name": "EXTENSIONS_HUB",
        "category": "extensions",
        "description": "GitHub repository URL for extensions hub (e.g., owner/repo)",
        "value_type": "string",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "EXTENSIONS_HUB_TOKEN",
        "category": "extensions",
        "description": "GitHub token for private extensions hub access",
        "value_type": "secret",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    # Notifications - moved to app_settings since there's only one
    {
        "name": "DISCORD_WEBHOOK",
        "category": "app_settings",
        "description": "Discord webhook URL for notifications",
        "value_type": "url",
        "default_value": "",
        "is_sensitive": True,
        "is_required": False,
    },
    # Default Agent Settings
    {
        "name": "AGENT_NAME",
        "category": "agent_defaults",
        "description": "Default agent name for new users",
        "value_type": "string",
        "default_value": "XT",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "AGENT_PERSONA",
        "category": "agent_defaults",
        "description": "Default persona for the agent",
        "value_type": "string",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "TRAINING_URLS",
        "category": "agent_defaults",
        "description": "Comma-separated list of URLs for agent training",
        "value_type": "string",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "ENABLED_COMMANDS",
        "category": "agent_defaults",
        "description": "Comma-separated list of enabled agent commands",
        "value_type": "string",
        "default_value": "",
        "is_sensitive": False,
        "is_required": False,
    },
    # Frontend Feature Flags
    {
        "name": "AGIXT_FILE_UPLOAD_ENABLED",
        "category": "features",
        "description": "Enable file upload in chat",
        "value_type": "boolean",
        "default_value": "true",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "AGIXT_VOICE_INPUT_ENABLED",
        "category": "features",
        "description": "Enable voice input in chat",
        "value_type": "boolean",
        "default_value": "true",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "AGIXT_RLHF",
        "category": "features",
        "description": "Enable RLHF feedback buttons",
        "value_type": "boolean",
        "default_value": "true",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "AGIXT_ALLOW_MESSAGE_EDITING",
        "category": "features",
        "description": "Allow users to edit their messages",
        "value_type": "boolean",
        "default_value": "true",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "AGIXT_ALLOW_MESSAGE_DELETION",
        "category": "features",
        "description": "Allow users to delete their messages",
        "value_type": "boolean",
        "default_value": "true",
        "is_sensitive": False,
        "is_required": False,
    },
    {
        "name": "AGIXT_SHOW_OVERRIDE_SWITCHES",
        "category": "features",
        "description": "Comma-separated list of override switches to show",
        "value_type": "string",
        "default_value": "tts,websearch,analyze-user-input",
        "is_sensitive": False,
        "is_required": False,
    },
]


def get_server_config_encryption_key():
    """
    Get or generate a server-wide encryption key for sensitive config values.
    This is stored in the filesystem as it's needed before the database is accessible.
    """
    key_file = os.path.join(os.path.dirname(__file__), ".server_config_key")
    if os.path.exists(key_file):
        with open(key_file, "rb") as f:
            return f.read()
    else:
        key = Fernet.generate_key()
        with open(key_file, "wb") as f:
            f.write(key)
        return key


def encrypt_config_value(value: str) -> str:
    """Encrypt a sensitive configuration value."""
    if not value:
        return ""
    key = get_server_config_encryption_key()
    f = Fernet(key)
    return f.encrypt(value.encode()).decode()


def decrypt_config_value(encrypted_value: str) -> str:
    """Decrypt a sensitive configuration value."""
    if not encrypted_value:
        return ""
    try:
        key = get_server_config_encryption_key()
        f = Fernet(key)
        return f.decrypt(encrypted_value.encode()).decode()
    except Exception:
        # If decryption fails, return empty string (value may not be encrypted)
        return encrypted_value


def get_server_config(name: str, default: str = None) -> str:
    """
    Get a server configuration value from the database.
    Decrypts sensitive values automatically.

    Args:
        name: The configuration key name
        default: Default value if not found in database

    Returns:
        The configuration value, or default if not found
    """
    try:
        with get_session() as db:
            config = db.query(ServerConfig).filter_by(name=name).first()
            if config and config.value:
                if config.is_sensitive:
                    return decrypt_config_value(config.value)
                return config.value
    except Exception as e:
        logging.debug(f"Could not get server config {name}: {e}")
    return default


def set_server_config(name: str, value: str, category: str = None) -> bool:
    """
    Set a server configuration value in the database.
    Encrypts sensitive values automatically.

    Args:
        name: The configuration key name
        value: The value to set
        category: Optional category override

    Returns:
        True if successful, False otherwise
    """
    try:
        with get_session() as db:
            config = db.query(ServerConfig).filter_by(name=name).first()
            if config:
                # Check if this is a sensitive value
                if config.is_sensitive and value:
                    config.value = encrypt_config_value(value)
                else:
                    config.value = value
                if category:
                    config.category = category
            else:
                # Find definition to get metadata
                definition = next(
                    (d for d in SERVER_CONFIG_DEFINITIONS if d["name"] == name), None
                )
                is_sensitive = (
                    definition.get("is_sensitive", False) if definition else False
                )

                new_config = ServerConfig(
                    name=name,
                    value=(
                        encrypt_config_value(value) if is_sensitive and value else value
                    ),
                    category=category
                    or (
                        definition.get("category", "general")
                        if definition
                        else "general"
                    ),
                    is_sensitive=is_sensitive,
                    is_required=(
                        definition.get("is_required", False) if definition else False
                    ),
                    description=definition.get("description") if definition else None,
                    value_type=(
                        definition.get("value_type", "string")
                        if definition
                        else "string"
                    ),
                    default_value=(
                        definition.get("default_value") if definition else None
                    ),
                )
                db.add(new_config)
            db.commit()
            return True
    except Exception as e:
        logging.error(f"Could not set server config {name}: {e}")
        return False


def seed_server_config_from_env():
    """
    Seed server configuration from environment variables.
    Creates new entries that don't exist in the database.
    Also updates existing entries that have empty values if an env value is available.

    Billing-related configs (TOKEN_PRICE_PER_MILLION_USD, BILLING_PAUSED) are always
    synced from environment variables to allow docker-compose control over billing.
    """
    logging.info("Seeding server configuration from environment variables...")
    seeded_count = 0
    updated_count = 0

    # These billing configs should ALWAYS sync from env to allow docker-compose control
    # This lets operators disable billing by setting TOKEN_PRICE_PER_MILLION_USD=0
    env_override_configs = {
        "TOKEN_PRICE_PER_MILLION_USD",
        "BILLING_PAUSED",
    }

    with get_session() as db:
        for definition in SERVER_CONFIG_DEFINITIONS:
            name = definition["name"]
            is_sensitive = definition.get("is_sensitive", False)

            # Get value from environment
            env_value = os.getenv(name, "")

            # Check if already exists in database
            existing = db.query(ServerConfig).filter_by(name=name).first()

            if not existing:
                # Create config entry with definition metadata
                new_config = ServerConfig(
                    name=name,
                    value=(
                        encrypt_config_value(env_value)
                        if is_sensitive and env_value
                        else env_value
                    ),
                    category=definition.get("category", "general"),
                    is_sensitive=is_sensitive,
                    is_required=definition.get("is_required", False),
                    description=definition.get("description"),
                    value_type=definition.get("value_type", "string"),
                    default_value=definition.get("default_value"),
                )
                db.add(new_config)
                seeded_count += 1
            elif name in env_override_configs and env_value:
                # Always sync billing-related configs from env if env value is set
                # This allows docker-compose to control billing (e.g., set price to 0)
                new_value = (
                    encrypt_config_value(env_value) if is_sensitive else env_value
                )
                if existing.value != new_value:
                    existing.value = new_value
                    updated_count += 1
                    logging.info(f"Synced {name} from environment variable")
            elif env_value and not existing.value:
                # Update existing entry with empty value if env has a value
                # This handles the case where token was added after initial setup
                existing.value = (
                    encrypt_config_value(env_value) if is_sensitive else env_value
                )
                updated_count += 1

        db.commit()

    logging.info(
        f"Seeded {seeded_count} new server config values, updated {updated_count} empty values from environment"
    )

    # Load the config cache after seeding
    try:
        from Globals import load_server_config_cache

        load_server_config_cache()
    except Exception as e:
        logging.debug(f"Could not load server config cache: {e}")


def seed_server_prompts():
    """
    Seed server-level prompts from the prompts folder.
    These prompts serve as the global defaults that can be inherited by companies and users.
    Server prompts are the base level in the tiered hierarchy:
    Server → Company → User

    This function should be called during startup after the tiered tables are created.
    """
    prompts_dir = os.path.join(os.path.dirname(__file__), "prompts")
    if not os.path.exists(prompts_dir):
        logging.warning(
            f"Prompts directory not found at {prompts_dir}, skipping server prompt seeding"
        )
        return

    seeded_count = 0
    updated_count = 0

    with get_session() as db:
        # Ensure default server category exists
        default_category = (
            db.query(ServerPromptCategory).filter_by(name="Default").first()
        )
        if not default_category:
            default_category = ServerPromptCategory(
                name="Default", description="Default category for server prompts"
            )
            db.add(default_category)
            db.commit()

        for root, dirs, files in os.walk(prompts_dir):
            for file in files:
                if not file.endswith((".txt", ".md", ".prompt")):
                    continue

                # Determine category from folder structure
                if root != prompts_dir:
                    category_name = os.path.basename(root)
                    category = (
                        db.query(ServerPromptCategory)
                        .filter_by(name=category_name)
                        .first()
                    )
                    if not category:
                        category = ServerPromptCategory(
                            name=category_name, description=f"{category_name} category"
                        )
                        db.add(category)
                        db.commit()
                else:
                    category = default_category

                prompt_name = os.path.splitext(file)[0]
                file_path = os.path.join(root, file)

                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        prompt_content = f.read()
                except Exception as e:
                    logging.warning(f"Could not read prompt file {file_path}: {e}")
                    continue

                # Check if server prompt already exists
                existing_prompt = (
                    db.query(ServerPrompt)
                    .filter_by(name=prompt_name, category_id=category.id)
                    .first()
                )

                if existing_prompt:
                    # Update content if changed
                    if existing_prompt.content != prompt_content:
                        existing_prompt.content = prompt_content
                        updated_count += 1
                else:
                    # Create new server prompt
                    server_prompt = ServerPrompt(
                        name=prompt_name,
                        description=f"Server-level prompt: {prompt_name}",
                        content=prompt_content,
                        category_id=category.id,
                    )
                    db.add(server_prompt)
                    db.commit()

                    # Extract and add prompt arguments
                    prompt_args = []
                    for word in prompt_content.split():
                        if word.startswith("{") and word.endswith("}"):
                            arg_name = word[1:-1]
                            if arg_name not in prompt_args:
                                prompt_args.append(arg_name)

                    for arg_name in prompt_args:
                        existing_arg = (
                            db.query(ServerPromptArgument)
                            .filter_by(prompt_id=server_prompt.id, name=arg_name)
                            .first()
                        )
                        if not existing_arg:
                            argument = ServerPromptArgument(
                                prompt_id=server_prompt.id, name=arg_name
                            )
                            db.add(argument)

                    seeded_count += 1

            db.commit()

    if seeded_count > 0 or updated_count > 0:
        logging.info(f"Server prompts: {seeded_count} seeded, {updated_count} updated")


def seed_server_chains():
    """
    Seed server-level chains from the chains folder.
    These chains serve as the global defaults that can be inherited by companies and users.
    Server chains are the base level in the tiered hierarchy:
    Server → Company → User

    This function should be called during startup after the tiered tables are created.
    """
    chains_dir = os.path.join(os.path.dirname(__file__), "chains")
    if not os.path.exists(chains_dir):
        logging.debug("Chains directory not found, skipping server chain seeding")
        return

    seeded_count = 0

    with get_session() as db:
        for file in os.listdir(chains_dir):
            if not file.endswith(".json"):
                continue

            chain_name = os.path.splitext(file)[0]
            file_path = os.path.join(chains_dir, file)

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    chain_data = json.load(f)
            except Exception as e:
                logging.warning(f"Could not read chain file {file_path}: {e}")
                continue

            # Check if server chain already exists
            existing_chain = db.query(ServerChain).filter_by(name=chain_name).first()
            if existing_chain:
                continue

            # Create new server chain
            server_chain = ServerChain(
                name=chain_name,
                description=chain_data.get(
                    "description", f"Server-level chain: {chain_name}"
                ),
            )
            db.add(server_chain)
            db.commit()

            # Add chain steps
            steps = chain_data.get("steps", [])
            for step_data in steps:
                step = ServerChainStep(
                    chain_id=server_chain.id,
                    step_number=step_data.get("step", 1),
                    agent_name=step_data.get("agent_name", ""),
                    prompt_type=step_data.get("prompt_type", ""),
                    prompt=step_data.get("prompt", {}),
                )
                db.add(step)

            seeded_count += 1
            db.commit()

    if seeded_count > 0:
        logging.info(f"Server chains: {seeded_count} seeded")
