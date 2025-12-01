# app/db.py - Database session management for Django web app
"""
Database configuration for Warden web dashboard.
Uses SQLAlchemy to connect to the same MySQL database as the Discord bot.
"""

import os
from contextlib import contextmanager
from urllib.parse import quote_plus
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool
import logging

logger = logging.getLogger(__name__)

# Global engine and session factory (singleton pattern)
_engine = None
_session_factory = None

def get_database_url() -> str:
    """Build MySQL connection URL from environment variables."""
    # Support both WARDEN_DB_* and DB_* variable names
    DB_SOCKET = os.getenv("WARDEN_DB_SOCKET") or os.getenv("DB_SOCKET")
    DB_HOST = os.getenv("WARDEN_DB_HOST") or os.getenv("DB_HOST")
    DB_PORT = os.getenv("WARDEN_DB_PORT") or os.getenv("DB_PORT", "3306")
    DB_USERNAME = os.getenv("WARDEN_DB_USER") or os.getenv("DB_USERNAME") or os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("WARDEN_DB_PASSWORD") or os.getenv("DB_PASSWORD")
    DB_NAME = os.getenv("WARDEN_DB_NAME") or os.getenv("DB_NAME", "warden")

    if not all([DB_USERNAME, DB_PASSWORD]):
        raise ValueError(
            "Database connection details are not fully set. "
            "Please set DB_USERNAME and DB_PASSWORD environment variables."
        )

    encoded_password = quote_plus(DB_PASSWORD)

    # Use mysqldb (from mysqlclient package) as SQLAlchemy driver
    # This is installed as 'mysqlclient' but imported as 'MySQLdb'
    if DB_SOCKET:
        return (
            f"mysql+mysqldb://{DB_USERNAME}:{encoded_password}"
            f"@/{DB_NAME}"
            f"?unix_socket={DB_SOCKET}&charset=utf8mb4"
        )
    else:
        if not DB_HOST:
            raise ValueError("Either DB_HOST or DB_SOCKET must be set.")
        return (
            f"mysql+mysqldb://{DB_USERNAME}:{encoded_password}"
            f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
            f"?charset=utf8mb4"
        )

def get_engine():
    """
    Get or create the database engine (Singleton).
    Optimized for web application with connection pooling.
    """
    global _engine
    if _engine is None:
        logger.info("Creating database engine...")

        _engine = create_engine(
            get_database_url(),
            echo=os.getenv("DB_ECHO", "false").lower() == "true",

            # Connection Pool Settings
            poolclass=QueuePool,
            pool_size=10,              # Base connections for web app
            max_overflow=20,           # Extra connections under load (30 total max)
            pool_pre_ping=True,        # Verify connection health
            pool_recycle=1800,         # Recycle connections every 30 min
            pool_timeout=30,           # Wait 30s for connection before error

            # Connection settings
            connect_args={
                "connect_timeout": 10,
                "charset": "utf8mb4",
            }
        )

        logger.info("✅ Database engine created successfully")

    return _engine

def get_session_factory():
    """
    Get or create the session factory (Singleton).
    Uses scoped_session for thread-safety.
    """
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = scoped_session(
            sessionmaker(
                bind=engine,
                autocommit=False,
                autoflush=True,
                expire_on_commit=False  # Keep objects usable after commit
            )
        )
    return _session_factory

@contextmanager
def get_db_session():
    """
    Context manager for database sessions.
    Auto-commits on success, rolls back on error, closes session.

    Usage:
        with get_db_session() as session:
            guild = session.query(Guild).filter_by(guild_id=12345).first()
            guild.subscription_tier = SubscriptionTier.PREMIUM.value
            # Auto-commits on exit
    """
    SessionFactory = get_session_factory()
    session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Database transaction failed: {e}", exc_info=True)
        raise
    finally:
        session.close()

@contextmanager
def db_session_scope():
    """
    Alias for get_db_session() for backwards compatibility.
    """
    with get_db_session() as session:
        yield session
