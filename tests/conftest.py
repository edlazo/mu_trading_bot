import os

os.environ["DATABASE_URL"] = "sqlite:///./test_mu_trading_bot.db"
os.environ["DISCORD_WEBHOOK_URL"] = ""
os.environ["TRADINGVIEW_WEBHOOK_SECRET"] = "test-secret"
os.environ["ENABLE_SCHEDULER"] = "false"
os.environ["SCHEDULER_INTERVAL_SECONDS"] = "300"

import pytest
from fastapi.testclient import TestClient

from app.database.base import Base
from app.database.session import SessionLocal, engine
from app.main import app


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()