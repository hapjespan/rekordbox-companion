"""GET/PUT /api/config: the app_config key/value store (data-model.md)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from companion.db.models import AppConfig
from companion.db.session import get_db

router = APIRouter()


@router.get("/config")
def get_config(db: Session = Depends(get_db)) -> dict[str, str]:
    return {row.key: row.value for row in db.query(AppConfig).all()}


@router.put("/config")
def put_config(values: dict[str, str], db: Session = Depends(get_db)) -> dict[str, str]:
    for key, value in values.items():
        row = db.get(AppConfig, key)
        if row is None:
            db.add(AppConfig(key=key, value=value))
        else:
            row.value = value
    db.commit()
    return {row.key: row.value for row in db.query(AppConfig).all()}
