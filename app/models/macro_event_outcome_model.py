from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MacroEventOutcome(Base):
    """체인별 사후 결과 (SPEC §16 event_outcomes). 향후 점수 보정의 원료."""

    __tablename__ = "macro_event_outcomes"
    __table_args__ = (
        UniqueConstraint("event_id", "horizon", name="uq_macro_event_outcomes_event_horizon"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("macro_events.id", ondelete="CASCADE"), index=True
    )
    event_chain_id: Mapped[int | None] = mapped_column(
        ForeignKey("macro_event_chains.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    horizon: Mapped[str] = mapped_column(String(4))  # OutcomeHorizon (1D~20D)
    measured_at_kst: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    reaction_target_type: Mapped[str] = mapped_column(String(20))  # ReactionTargetType
    reaction_target_id: Mapped[str | None] = mapped_column(String(40), nullable=True)

    price_change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_change_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 같은 기간 broad_market(SPY/KOSPI) 대비
    benchmark_change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    excess_return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    outcome_label: Mapped[str] = mapped_column(String(20))  # OutcomeLabel
    score_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
