import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_runtime
from app.core.errors import AuthError
from app.core.storage import AVATAR_MAX_BYTES, AvatarStorage, get_avatar_storage
from app.database import get_db
from app.models import User
from app.schemas.account import DefaultAddressUpdate, ProfileUpdate
from app.schemas import (
    AddressCreate,
    AddressUpdate,
    NotificationCountResponse,
    NotificationResponse,
    PageResponse,
)
from app.schemas.user import AddressResponse, UserResponse
from app.services.user import AddressService, NotificationService, UserService

from .dependencies import CurrentActor, Page, PageSize, get_address_service, get_notification_service


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


# ------------------------------------------------------------------ address book (Customer, Stage 4 AddressService)

Addresses = Annotated[AddressService, Depends(get_address_service)]
Notifications = Annotated[NotificationService, Depends(get_notification_service)]


@router.get("/me/addresses", response_model=list[AddressResponse])
def list_addresses(service: Addresses, actor: CurrentActor):
    return service.list_addresses(actor)


@router.get("/me/addresses/{address_id}", response_model=AddressResponse)
def get_address(address_id: uuid.UUID, service: Addresses, actor: CurrentActor):
    return service.get_address(actor, address_id)


@router.post("/me/addresses", response_model=AddressResponse, status_code=status.HTTP_201_CREATED)
def create_address(data: AddressCreate, service: Addresses, actor: CurrentActor):
    return service.create_address(actor, data)


@router.patch("/me/addresses/{address_id}", response_model=AddressResponse)
def update_address(address_id: uuid.UUID, data: AddressUpdate, service: Addresses, actor: CurrentActor):
    return service.update_address(actor, address_id, data)


@router.delete("/me/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_address(address_id: uuid.UUID, service: Addresses, actor: CurrentActor):
    """Soft delete: orders keep referencing the old address."""
    service.delete_address(actor, address_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ notifications (every role, own only)


@router.get("/me/notifications", response_model=PageResponse[NotificationResponse])
def list_notifications(service: Notifications, actor: CurrentActor, is_read: bool | None = None,
                       page: Page = 1, page_size: PageSize = 20):
    return service.list_notifications(actor, is_read=is_read, page=page, page_size=page_size)


@router.get("/me/notifications/unread-count", response_model=NotificationCountResponse)
def count_unread_notifications(service: Notifications, actor: CurrentActor):
    return NotificationCountResponse(Count=service.count_unread(actor))


@router.post("/me/notifications/read-all", response_model=NotificationCountResponse)
def mark_all_notifications_read(service: Notifications, actor: CurrentActor):
    return NotificationCountResponse(Count=service.mark_all_read(actor))


@router.post("/me/notifications/{notification_id}/read", response_model=NotificationResponse)
def mark_notification_read(notification_id: uuid.UUID, service: Notifications, actor: CurrentActor):
    return service.mark_read(actor, notification_id)
