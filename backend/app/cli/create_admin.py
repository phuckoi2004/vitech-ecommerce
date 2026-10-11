"""Create the initial Admin; only when an operator runs this command."""

import getpass
import sys
import uuid

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.errors import AuthError
from app.core.security import hash_password
from app.database import SessionLocal
from app.models import User
from app.repositories.user import UserRepository
from app.schemas.auth import RegistrationRequest


def main():
    try:
        data = RegistrationRequest(
            Email=input("Email Admin: ").strip(),
            PhoneNumber=input("Số điện thoại Việt Nam: ").strip(),
            FullName=input("Họ và tên: ").strip(),
            Password=getpass.getpass("Mật khẩu: "),
            ConfirmPassword=getpass.getpass("Nhập lại mật khẩu: "),
        )
        with SessionLocal() as db:
            if db.bind.dialect.name != "postgresql":
                raise AuthError(503, "Lệnh khởi tạo yêu cầu PostgreSQL của dự án")
            # Serialize initial setup without adding a table or modifying schema.
            db.execute(text("SELECT pg_advisory_xact_lock(5015005)"))
            existing = db.scalar(select(User.UserId).where(User.Role == "Admin").limit(1))
            if existing is not None:
                raise AuthError(409, "Hệ thống đã có Admin. Không tạo thêm tài khoản")
            users = UserRepository(db)
            if users.exists_by_email(str(data.Email)) or users.exists_by_phone(data.PhoneNumber):
                raise AuthError(409, "Email hoặc số điện thoại đã được sử dụng")
            users.create({
                "UserId": uuid.uuid4(), "Email": str(data.Email), "PhoneNumber": data.PhoneNumber,
                "FullName": data.FullName, "PasswordHash": hash_password(data.Password),
                "Role": "Admin", "AccountStatus": "Active", "IsEmailVerified": True,
                "IsDeleted": False,
            })
            db.commit()
        print("Đã tạo Admin. Đăng nhập bằng Portal=admin")
        return 0
    except AuthError as error:
        print(error.message, file=sys.stderr)
    except IntegrityError:
        print("Không thể tạo: email hoặc số điện thoại đã được sử dụng", file=sys.stderr)
    except SQLAlchemyError:
        print("Không thể kết nối hoặc lưu dữ liệu. Kiểm tra cấu hình database", file=sys.stderr)
    except (KeyboardInterrupt, EOFError):
        print("Đã dừng khởi tạo", file=sys.stderr)
    except ValueError:
        # Pydantic error details can contain the raw password; do not print them.
        print("Dữ liệu không hợp lệ: kiểm tra email, số điện thoại, họ tên và mật khẩu xác nhận", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
