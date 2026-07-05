from datetime import date

from sqlalchemy import Boolean, Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MacroEntityAlias(Base):
    """entity alias 테이블 (SPEC §11.4). 정본은 config/macro_events/entity_alias_map.csv.

    사람이 검증한 alias만 등재하며(§11.1), 매칭은 normalized_alias 전체 문자열
    exact match만 — 단독 약칭 행 금지. 활성 행의 normalized_alias 유일성은
    config 로더가 검증한다 (비활성 이력 행과의 중복은 허용)."""

    __tablename__ = "macro_entity_alias_map"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_entity_name: Mapped[str] = mapped_column(String(200))
    alias_name: Mapped[str] = mapped_column(String(200))
    normalized_alias: Mapped[str] = mapped_column(String(200), index=True)
    ticker: Mapped[str] = mapped_column(String(20))
    exchange: Mapped[str] = mapped_column(String(16))
    cik: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    corp_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    uei: Mapped[str | None] = mapped_column(String(12), nullable=True)
    country: Mapped[str] = mapped_column(String(8))
    entity_type: Mapped[str] = mapped_column(String(32))
    mapping_confidence: Mapped[str] = mapped_column(String(8))
    verified_by: Mapped[str] = mapped_column(String(64))
    verified_at: Mapped[date] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
