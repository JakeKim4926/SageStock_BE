from sqlalchemy import BigInteger, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PaperTrade(Base):
    """가상매매 체결 기록(실주문 아님). 체결가는 클라 요청가 그대로 저장 (feature-spec D7)."""

    __tablename__ = "paper_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    ticker: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    market: Mapped[str] = mapped_column(String(8))
    side: Mapped[str] = mapped_column(String(8))
    price: Mapped[float] = mapped_column(Float)
    quantity: Mapped[int] = mapped_column(Integer)
    # 체결 시각 = epoch milliseconds UTC (api-spec §0). 서버 부여.
    timestamp: Mapped[int] = mapped_column(BigInteger)
