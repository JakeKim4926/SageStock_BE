"""Normalize Service (SPEC §17, PLAN Phase 1 공통 기반).

collector가 소스별 원문을 공통 이벤트 스키마(NormalizedMacroEvent)로 변환할 때 쓰는
모델·시각 변환 유틸. 모든 시각은 aware KST로 통일한다 (소스 원문 시각은 source
timezone으로 해석한 뒤 변환).
"""
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.constants.macro_enums import (
    CertaintyLevel,
    EventStatus,
    LatencyReferenceType,
    MacroEventType,
)
from app.models.macro_event_model import MacroEvent

KST = ZoneInfo("Asia/Seoul")


def now_kst() -> datetime:
    return datetime.now(KST)


def to_kst(moment: datetime, source_tz: ZoneInfo | None = None) -> datetime:
    """소스 시각을 aware KST로 변환. naive면 source_tz가 필수다."""
    if moment.tzinfo is None:
        if source_tz is None:
            raise ValueError("naive datetime은 source_tz 없이 변환할 수 없음")
        moment = moment.replace(tzinfo=source_tz)
    return moment.astimezone(KST)


class NormalizedMacroEvent(BaseModel):
    """공통 이벤트 스키마 — collector 산출물, 저장 직전 형태.

    - event_type은 v1 taxonomy 3종만 (SPEC §2.1, enum이 강제)
    - publicly_observable_at 필수 + aware (MarketLatency 기준 시각, §13.1)
    - raw_payload 또는 raw_text 중 하나는 반드시 보존 (§5.4)
    - linked_entities는 원문에 명시된 entity만 (§11 — 추론 삽입 금지)
    """

    model_config = ConfigDict(extra="forbid")

    event_unique_id: str = Field(min_length=1)
    event_type: MacroEventType
    title: str = Field(min_length=1)
    summary: str | None = None

    event_effective_at: datetime | None = None
    document_signed_at: datetime | None = None
    source_published_at: datetime | None = None
    publicly_observable_at: datetime
    latency_reference_type: LatencyReferenceType

    certainty_level: CertaintyLevel
    event_status: EventStatus = EventStatus.ACTIVE
    linked_entities: list[dict[str, Any]] | None = None

    raw_payload: dict[str, Any] | None = None
    raw_text: str | None = None
    source_url: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_invariants(self) -> "NormalizedMacroEvent":
        if self.raw_payload is None and self.raw_text is None:
            raise ValueError("raw_payload 또는 raw_text 중 하나는 보존해야 함 (SPEC §5.4)")

        aware_required = {
            "event_effective_at": self.event_effective_at,
            "document_signed_at": self.document_signed_at,
            "source_published_at": self.source_published_at,
            "publicly_observable_at": self.publicly_observable_at,
        }
        naive = [name for name, value in aware_required.items() if value is not None and value.tzinfo is None]
        if naive:
            raise ValueError(f"naive datetime 금지 (KST 변환 후 전달): {naive}")
        return self


def to_model(
    event: NormalizedMacroEvent,
    source_id: str,
    collected_at_kst: datetime,
) -> MacroEvent:
    """NormalizedMacroEvent → macro_events ORM 행.

    chain/domain/점수 필드는 파이프라인(Phase 2~3) 소유라 채우지 않는다."""
    return MacroEvent(
        event_unique_id=event.event_unique_id,
        source_id=source_id,
        event_type=event.event_type.value,
        title=event.title,
        summary=event.summary,
        event_effective_at=event.event_effective_at,
        document_signed_at=event.document_signed_at,
        source_published_at=event.source_published_at,
        collected_at_kst=collected_at_kst,
        publicly_observable_at=event.publicly_observable_at,
        latency_reference_type=event.latency_reference_type.value,
        event_status=event.event_status.value,
        certainty_level=event.certainty_level.value,
        linked_entities=event.linked_entities,
        raw_payload=event.raw_payload,
        raw_text=event.raw_text,
        source_url=event.source_url,
    )
