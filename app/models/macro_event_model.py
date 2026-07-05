from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.types import JSON_VARIANT


class MacroEvent(Base):
    """매크로 이벤트 (SPEC §16 macro_events).

    - event_unique_id는 소스별 고유 식별자(accession_number, receipt_no 등) — dedup 기준
    - publicly_observable_at이 MarketLatency 기준 시각 (§13.1, 서명 시각 아님)
    - linked_entities는 원문에 명시된 entity만 (§11 — 관련주/LLM 추론 삽입 금지)
    """

    __tablename__ = "macro_events"
    __table_args__ = (
        UniqueConstraint("source_id", "event_unique_id", name="uq_macro_events_source_unique_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # 식별
    event_unique_id: Mapped[str] = mapped_column(String(200))
    source_id: Mapped[str] = mapped_column(
        ForeignKey("macro_event_sources.source_id"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(40), index=True)  # MacroEventType
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 시각 필드 6종 (§13.1)
    event_effective_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    document_signed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    collected_at_kst: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    publicly_observable_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    latency_reference_type: Mapped[str] = mapped_column(String(32))  # LatencyReferenceType

    # 체인 (§7)
    event_chain_id: Mapped[int | None] = mapped_column(
        ForeignKey("macro_event_chains.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_status: Mapped[str] = mapped_column(String(20))  # EventStatus

    # 도메인 필드 5종 (§9.4) — 할당 전에는 전부 NULL
    primary_domain: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )  # MacroDomain
    secondary_domains: Mapped[list[str] | None] = mapped_column(JSON_VARIANT, nullable=True)
    domain_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    matched_keywords: Mapped[list[str] | None] = mapped_column(JSON_VARIANT, nullable=True)
    domain_assignment_version: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # entity (§11) — 원문 명시 entity만
    linked_entities: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON_VARIANT, nullable=True
    )

    # 점수/레벨 — priority/propagation은 Phase 3 측정 후 기록
    certainty_level: Mapped[str] = mapped_column(String(4))  # CertaintyLevel
    priority_score: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    propagation_stage: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 원문 보존 (§5.4 P1 조건: raw_payload 또는 raw_text 존재)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON_VARIANT, nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str] = mapped_column(String(1000))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
