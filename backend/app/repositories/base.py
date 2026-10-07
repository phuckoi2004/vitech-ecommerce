"""BaseRepository dùng chung cho các repository.

Quy ước:
- Repository nhận Session từ bên ngoài (Service quản lý transaction).
- Repository không commit, không rollback.
- create/update/delete chỉ thay đổi object trong Session; dữ liệu được ghi khi Service flush/commit.
  SessionLocal dùng autoflush=False, nên truy vấn trong cùng transaction chỉ thấy object mới
  sau khi Service gọi ``flush()``.
- Không có thông báo lỗi kiểu HTTP; không kiểm tra quyền.
"""

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import exists, func, inspect, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from app.models import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Đọc
    # ------------------------------------------------------------------

    def get_by_id(self, id_: Any) -> ModelT | None:
        """Lấy theo primary key. Bảng PK ghép truyền tuple theo thứ tự cột PK."""
        return self.session.get(self.model, id_)

    def get_by_id_for_update(self, id_: Any) -> ModelT | None:
        """Lấy theo primary key và khóa dòng (SELECT ... FOR UPDATE) trong transaction hiện tại."""
        return self.session.get(self.model, id_, with_for_update=True)

    def get_one(self, *where: ColumnElement[bool]) -> ModelT | None:
        """Lấy một dòng theo điều kiện; lỗi MultipleResultsFound nếu có nhiều hơn một dòng."""
        return self.session.scalars(select(self.model).where(*where)).one_or_none()

    def get_all(
        self,
        *where: ColumnElement[bool],
        order_by: Sequence[Any] = (),
        offset: int | None = None,
        limit: int | None = None,
        options: Sequence[Any] = (),
    ) -> list[ModelT]:
        stmt = select(self.model).where(*where).order_by(*order_by).options(*options)
        if offset is not None:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.session.scalars(stmt))

    def count(self, *where: ColumnElement[bool]) -> int:
        stmt = select(func.count()).select_from(self.model).where(*where)
        return self.session.scalar(stmt) or 0

    def exists(self, *where: ColumnElement[bool]) -> bool:
        # select_from tường minh để câu lệnh hợp lệ cả khi không có điều kiện.
        return bool(self.session.scalar(select(exists().select_from(self.model).where(*where))))

    # ------------------------------------------------------------------
    # Ghi (không commit)
    # ------------------------------------------------------------------

    def add(self, obj: ModelT) -> ModelT:
        self.session.add(obj)
        return obj

    def create(self, values: Mapping[str, Any]) -> ModelT:
        """Tạo object từ dict tên column → giá trị (ví dụ từ ``schema.model_dump(exclude_unset=True)``).

        Giá trị do database sinh (UUID, now(), default) chỉ có sau khi Service flush.
        """
        self._check_columns(values)
        return self.add(self.model(**values))

    def update(self, obj: ModelT, values: Mapping[str, Any]) -> ModelT:
        """Gán giá trị cho các column có trong ``values``; không đổi primary key."""
        self._check_columns(values)
        pk_names = {column.key for column in inspect(self.model).primary_key}
        changed_pk = pk_names & set(values)
        if changed_pk:
            raise ValueError(f"Không được thay đổi primary key: {sorted(changed_pk)}")
        for key, value in values.items():
            setattr(obj, key, value)
        return obj

    def delete(self, obj: ModelT) -> None:
        """Xóa dòng (DELETE). Với bảng có IsDeleted, Service quyết định xóa mềm hay xóa thật."""
        self.session.delete(obj)

    def flush(self, objects: Iterable[ModelT] | None = None) -> None:
        """Ghi các thay đổi đang chờ vào transaction (không commit), ví dụ để lấy UUID do database sinh."""
        self.session.flush(objects)

    # ------------------------------------------------------------------

    def _check_columns(self, values: Mapping[str, Any]) -> None:
        columns = set(inspect(self.model).columns.keys())
        unknown = set(values) - columns
        if unknown:
            raise ValueError(f"{self.model.__name__} không có column: {sorted(unknown)}")
