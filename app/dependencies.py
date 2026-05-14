from typing import Optional

from fastapi import Request

from app.models import User, Workspace
from app.security import decode_access_token


def get_current_user(request: Request) -> Optional[User]:
    token = request.cookies.get("access_token")
    if not token:
        return None
    user_id = decode_access_token(token)
    if not user_id:
        return None
    return User.objects(id=user_id).first()


def require_user(request: Request) -> User:
    user = get_current_user(request)
    if not user:
        from fastapi.responses import RedirectResponse

        raise RedirectToLogin(RedirectResponse("/login", status_code=303))
    return user


class RedirectToLogin(Exception):
    def __init__(self, response):
        self.response = response


def get_owned_workspace(workspace_id: str, user: User) -> Optional[Workspace]:
    return Workspace.objects(id=workspace_id, owner=user).first()
