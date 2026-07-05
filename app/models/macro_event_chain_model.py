from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MacroEventChain(Base):
    """이벤트 체인 (SPEC §7). chain_key는 명시적 식별자 조합으로만 생성 — fuzzy 금지.

    체인 소속 이벤트와 순서는 macro_events.event_chain_id + publicly_observable_at로 본다."""

    __tablename__ = "macro_event_chains"

    id: Mapped[int] = mapped_column(primary_key=True)
    chain_key: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    # CertaintyLevel 값. LEAD→CONFIRMATION→OUTCOME 승격 시 갱신 (§7.4).
    highest_certainty_level: Mapped[str] = mapped_column(String(4))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
