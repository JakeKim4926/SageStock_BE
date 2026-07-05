from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MacroSourceFreshness(Base):
    """소스별 수집 신선도 (SPEC §5.5, §16 source_freshness).

    collector 실패는 FAILED + last_error로 기록하고 리포트에 노출한다 — 조용한 실패 금지."""

    __tablename__ = "macro_source_freshness"

    source_id: Mapped[str] = mapped_column(
        ForeignKey("macro_event_sources.source_id", ondelete="CASCADE"),
        primary_key=True,
    )
    last_success_at_kst: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    freshness_status: Mapped[str] = mapped_column(String(12))  # FreshnessStatus
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
