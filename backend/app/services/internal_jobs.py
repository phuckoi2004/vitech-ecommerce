"""Vòng chạy chung của các tác vụ nội bộ do cron gọi (hết hạn QR, xử lý lại webhook).

- Mỗi bản ghi một transaction riêng, có timeout của tác vụ (PostgreSQL ``SET LOCAL``: chỉ có hiệu lực trong
  transaction đó, tự hết khi commit/rollback, không đổi cấu hình kết nối hay toàn hệ thống).
- Bản ghi lỗi: transaction của nó được rollback toàn bộ (BaseService.transaction), lỗi được đếm và ghi log theo loại
  (database / nghiệp vụ / không mong đợi), các bản ghi sau vẫn được xử lý. Bản ghi lỗi không bị đánh dấu hay bỏ đi:
  giữ nguyên trạng thái và được chọn lại ở lần chạy sau (quy tắc thử lại hiện có).
- Log chỉ gồm tên tác vụ, số liệu, thời gian, id nội bộ của bản ghi và loại/mã lỗi; không ghi secret, dữ liệu cá nhân,
  payload webhook hay nội dung lỗi của driver (có thể chứa câu SQL và tham số).
"""

import logging
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .base import BaseService
from .exceptions import ServiceError

logger = logging.getLogger("app.jobs")

# Giả định (code và cấu hình hiện có không có giá trị nào để dựa vào): các luồng người dùng chỉ giữ khóa đơn/sự kiện
# trong vài mili giây, nên chờ khóa quá 5 giây là bất thường; bản ghi đó được tính là lỗi và thử lại ở lần chạy sau.
# 30 giây là trần cho một câu lệnh trong transaction của tác vụ.
JOB_LOCK_TIMEOUT_MS = 5_000
JOB_STATEMENT_TIMEOUT_MS = 30_000


class JobSelectionError(ServiceError):
    """Lỗi bất ngờ (không phải database hay nghiệp vụ) khi chọn bản ghi: tác vụ chưa xử lý bản ghi nào (HTTP 500)."""

    code = "job_selection_failed"

    def __init__(self) -> None:
        super().__init__("Không chọn được bản ghi để xử lý; tác vụ chưa xử lý bản ghi nào. Vui lòng thử lại sau.")


@dataclass(frozen=True)
class JobRun:
    """Kết quả một lần chạy: số bản ghi được chọn, đã xử lý, bỏ qua (không còn đủ điều kiện khi khóa) và lỗi."""

    job: str
    selected: int = 0
    processed: int = 0
    skipped: int = 0
    failed: int = 0


def database_error_code(error: BaseException) -> str | None:
    """SQLSTATE của lỗi database (ví dụ 55P03 hết thời gian chờ khóa, 57014 hủy câu lệnh), không kèm nội dung lỗi."""
    return getattr(getattr(error, "orig", None), "sqlstate", None)


def set_job_timeouts(session: Session) -> None:
    """Đặt timeout chờ khóa và câu lệnh cho transaction hiện tại của tác vụ (chỉ PostgreSQL; Session khác bỏ qua)."""
    if not isinstance(session, Session) or session.get_bind().dialect.name != "postgresql":
        return
    session.execute(text(f"SET LOCAL lock_timeout = {int(JOB_LOCK_TIMEOUT_MS)}"))
    session.execute(text(f"SET LOCAL statement_timeout = {int(JOB_STATEMENT_TIMEOUT_MS)}"))


def run_job(
    service: BaseService,
    job: str,
    select: Callable[[], Iterable[uuid.UUID]],
    handle: Callable[[uuid.UUID], bool],
) -> JobRun:
    """Chọn bản ghi (``select``, trong một transaction có timeout) rồi xử lý từng bản ghi trong transaction riêng.

    ``handle(id)`` trả True khi đã xử lý bản ghi, False khi bỏ qua. Lỗi khi chọn bản ghi (chưa xử lý gì) được ghi log
    rồi ném tiếp: lỗi database và lỗi nghiệp vụ giữ nguyên (HTTP 503 / mã của lỗi), lỗi khác thành ``JobSelectionError``
    (HTTP 500). Lỗi của một bản ghi được rollback, đếm và ghi log; vòng lặp chạy tiếp với bản ghi sau.
    """
    started = time.monotonic()
    logger.info("job=%s event=started", job, extra={"job": job, "job_event": "started"})
    try:
        with service.transaction():
            set_job_timeouts(service.session)
            ids = list(select())
    except Exception as exc:
        logger.error(
            "job=%s event=selection_failed error=%s sqlstate=%s duration_ms=%d", job, type(exc).__name__,
            database_error_code(exc), _elapsed_ms(started),
            extra={"job": job, "job_event": "selection_failed", "error_code": type(exc).__name__},
        )
        if isinstance(exc, (SQLAlchemyError, ServiceError)):
            raise
        raise JobSelectionError() from exc

    processed = skipped = failed = 0
    for record_id in ids:
        try:
            with service.transaction():
                set_job_timeouts(service.session)
                done = handle(record_id)
        except SQLAlchemyError as exc:
            failed += 1
            _record_failed(job, record_id, "database", database_error_code(exc) or type(exc).__name__)
        except ServiceError as exc:
            failed += 1
            cause = exc.__cause__
            if isinstance(cause, SQLAlchemyError):
                # transaction() turns a constraint violation (IntegrityError) into a ServiceError: a database error.
                _record_failed(job, record_id, "database", database_error_code(cause) or type(cause).__name__)
            else:
                _record_failed(job, record_id, "business", exc.code)
        except Exception as exc:  # một lỗi bất ngờ của một bản ghi không được dừng các bản ghi khác
            failed += 1
            _record_failed(job, record_id, "unexpected", type(exc).__name__)
        else:
            if done:
                processed += 1
            else:
                skipped += 1

    run = JobRun(job=job, selected=len(ids), processed=processed, skipped=skipped, failed=failed)
    duration = _elapsed_ms(started)
    logger.log(
        logging.WARNING if failed else logging.INFO,
        "job=%s event=finished selected=%d processed=%d skipped=%d failed=%d duration_ms=%d",
        job, run.selected, processed, skipped, failed, duration,
        extra={"job": job, "job_event": "finished", "selected": run.selected, "processed": processed,
               "skipped": skipped, "failed": failed, "duration_ms": duration},
    )
    return run


def _record_failed(job: str, record_id: uuid.UUID, kind: str, code: str) -> None:
    logger.error(
        "job=%s event=record_failed record_id=%s error_kind=%s error_code=%s", job, record_id, kind, code,
        extra={"job": job, "job_event": "record_failed", "record_id": str(record_id), "error_kind": kind,
               "error_code": code},
    )


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
