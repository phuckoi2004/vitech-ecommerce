from sqlalchemy import CheckConstraint, MetaData
from sqlalchemy.orm import DeclarativeBase


NAMING_CONVENTION = {
    "pk": "PK_%(table_name)s",
    "fk": "FK_%(table_name)s_%(column_0_name)s",
    "uq": "UQ_%(table_name)s_%(column_0_N_name)s",
    "ck": "CK_%(table_name)s_%(constraint_name)s",
    "ix": "IX_%(table_name)s_%(column_0_N_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def check_in(column: str, values: tuple[str, ...], name: str) -> CheckConstraint:
    """CHECK "<column>" IN ('v1', 'v2', ...) cho các cột status lưu bằng varchar."""
    allowed = ", ".join(f"'{value}'" for value in values)
    return CheckConstraint(f'"{column}" IN ({allowed})', name=name)
