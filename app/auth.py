from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import dashboard_credentials

security = HTTPBasic()


def require_user(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    user, password = dashboard_credentials()
    if not user or not password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dashboard credentials are not configured. Set DASHBOARD_USER and DASHBOARD_PASSWORD.",
        )
    user_ok = secrets.compare_digest(credentials.username.encode("utf-8"), user.encode("utf-8"))
    pass_ok = secrets.compare_digest(credentials.password.encode("utf-8"), password.encode("utf-8"))
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": 'Basic realm="Podcast aggregator"'},
        )
    return credentials.username
