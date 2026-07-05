from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MacroMarketReactionSnapshot(Base):
    """측정 시점별 시장 반응 스냅샷 (SPEC §16 market_reaction_snapshots).

    실패도 기록 대상이다: basket 매핑 실패·데이터 부재는 status+reason으로 남기고
    조용히 UNKNOWN으로 숨기지 않는다 (§10.4, §13.3)."""

    __tablename__ = "macro_market_reaction_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("macro_events.id", ondelete="CASCADE"), index=True
    )
    measured_at_kst: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    reaction_target_type: Mapped[str] = mapped_column(String(20))  # ReactionTargetType
    reaction_target_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reaction_target_status: Mapped[str] = mapped_column(String(30))  # ReactionTargetStatus

    basket_mapping_status: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # BasketMappingStatus
    basket_mapping_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    market_latency_status: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # MarketLatencyStatus
    data_quality: Mapped[str | None] = mapped_column(
        String(24), nullable=True
    )  # LatencyDataQuality

    # 측정 시점 가격 스냅샷
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
