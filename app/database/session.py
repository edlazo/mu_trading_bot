from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



def ensure_sqlite_schema() -> None:
    if not settings.database_url.startswith("sqlite"):
        return

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    table_columns = {
        "alerts": {
            "entry_price": "FLOAT",
            "risk_reward": "FLOAT",
        },
        "decisions": {
            "entry_price": "FLOAT",
            "target": "FLOAT",
            "stop_loss": "FLOAT",
            "risk_reward": "FLOAT",
        },
    }

    # MVP compatibility for existing local SQLite DBs. Replace with Alembic migrations before production.
    with engine.begin() as connection:
        for table_name, columns_to_add in table_columns.items():
            if table_name not in tables:
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for name, column_type in columns_to_add.items():
                if name not in existing_columns:
                    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {name} {column_type}"))
