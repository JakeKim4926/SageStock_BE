from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 테스트(sqlite)에서는 JSON, 운영(PG)에서는 JSONB로 저장.
JSON_VARIANT = JSON().with_variant(JSONB(), "postgresql")


class MacroEventSource(Base):
    """소스 레지스트리 (SPEC §4). 시드 8행은 마이그레이션에서 삽입."""

    __tablename__ = "macro_event_sources"

    source_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    target_description: Mapped[str] = mapped_column(String(200))
    # SourceRole 값 목록. KR_MARKET_DATA처럼 역할 없는 데이터 소스는 빈 리스트.
    source_roles: Mapped[list[str]] = mapped_column(JSON_VARIANT)
    collection_interval: Mapped[str] = mapped_column(String(100))
    observable_at_basis: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
