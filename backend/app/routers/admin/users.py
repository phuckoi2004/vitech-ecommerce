import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_runtime, require_permission
from app.database import get_db
from app.models import User
from app.schemas.account import AdminUserPage, InternalUserCreate, ManagedUserUpdate
from app.schemas.common import UserRole
from app.schemas.user import AddressResponse, AdminUserResponse
from app.services.user import UserService


router = APIRouter(prefix="/admin/users", tags=["Quản lý tài khoản"])
Actor = Annotated[User, Depends(require_permission("users:manage"))]
Database = Annotated[Session, Depends(get_db)]
Runtime = Annotated[Any, Depends(get_runtime)]


@router.get("", response_model=AdminUserPage)
def list_users(actor: Actor, db: Database, runtime: Runtime,
               page: Annotated[int, Query(ge=1)] = 1,
               page_size: Annotated[int, Query(ge=1, le=100)] = 20,
               role: UserRole | None = None,
               account_status: Literal["Active", "Locked"] | None = None,
               include_deleted: bool = False,
               search: Annotated[str | None, Query(max_length=100)] = None,
               deleted_only: bool = False):
    """`search` tìm trong họ tên, email, số điện thoại; `deleted_only` chỉ lấy tài khoản đã xóa mềm."""
    return UserService(db, runtime).list_users(actor, page=page, page_size=page_size,
                                             role=role, account_status=account_status,
                                             include_deleted=include_deleted, search=search,
                                             deleted_only=deleted_only)


@router.get("/{user_id}", response_model=AdminUserResponse)
def get_user(user_id: uuid.UUID, actor: Actor, db: Database, runtime: Runtime,
             include_deleted: bool = False):
    return UserService(db, runtime).get_user(actor, user_id, include_deleted=include_deleted)


@router.get("/{user_id}/default-address", response_model=AddressResponse | None)
def get_default_address(user_id: uuid.UUID, actor: Actor, db: Database, runtime: Runtime):
    service = UserService(db, runtime)
    return service.get_default_address(service.get_user(actor, user_id, include_deleted=True))


@router.post("", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
def create_user(payload: InternalUserCreate, actor: Actor, db: Database, runtime: Runtime):
    return UserService(db, runtime).create_user(actor, payload)


@router.patch("/{user_id}", response_model=AdminUserResponse)
def update_user(user_id: uuid.UUID, payload: ManagedUserUpdate, actor: Actor,
                db: Database, runtime: Runtime):
    return UserService(db, runtime).update_user(actor, user_id, payload)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: uuid.UUID, actor: Actor, db: Database, runtime: Runtime):
    UserService(db, runtime).delete_user(actor, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
