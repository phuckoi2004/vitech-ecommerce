from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_runtime
from app.core.errors import AuthError
from app.core.storage import AVATAR_MAX_BYTES, AvatarStorage, get_avatar_storage
from app.database import get_db
from app.models import User
from app.schemas.account import DefaultAddressUpdate, ProfileUpdate
from app.schemas.user import AddressResponse, UserResponse
from app.services.user import UserService


router = APIRouter(prefix="/users", tags=["Hồ sơ"])
CurrentUser = Annotated[User, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_db)]
Runtime = Annotated[Any, Depends(get_runtime)]
TOO_LARGE = "Ảnh đại diện tối đa 2 MB."


@router.get("/me", response_model=UserResponse)
def get_profile(user: CurrentUser):
    return user


@router.patch("/me", response_model=UserResponse)
def update_profile(payload: ProfileUpdate, user: CurrentUser, db: Database, runtime: Runtime):
    return UserService(db, runtime).update_profile(user, payload)


@router.put("/me/avatar", response_model=UserResponse)
async def upload_avatar(request: Request, user: CurrentUser, db: Database, runtime: Runtime,
                        storage: Annotated[AvatarStorage | None, Depends(get_avatar_storage)]):
    """The body is the raw image file; its signature decides the type."""
    declared = request.headers.get("Content-Length", "")
    if declared.isdigit() and int(declared) > AVATAR_MAX_BYTES:
        raise AuthError(413, TOO_LARGE)
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > AVATAR_MAX_BYTES:
            raise AuthError(413, TOO_LARGE)
    if not data:
        raise AuthError(422, "Vui lòng chọn ảnh đại diện.")
    return await run_in_threadpool(UserService(db, runtime).update_avatar, user, bytes(data), storage)


@router.get("/me/default-address", response_model=AddressResponse | None)
def get_default_address(user: CurrentUser, db: Database, runtime: Runtime):
    return UserService(db, runtime).get_default_address(user)


@router.put("/me/default-address", response_model=AddressResponse)
def save_default_address(payload: DefaultAddressUpdate, user: CurrentUser, db: Database, runtime: Runtime):
    return UserService(db, runtime).save_default_address(user, payload)
