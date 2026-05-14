from mongoengine import connect

from app.config import get_settings


def init_db() -> None:
    settings = get_settings()
    connect(host=settings.mongodb_uri, alias="default")
