from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StockMeta(Base):
    """종목 기본 메타 영속 캐시 (feature-spec §5). fdr 리스팅을 일배치로 갱신해
    검색·단건 조회·메타 조인이 콜드스타트 전체 다운로드 없이 DB를 읽도록 한다."""

    __tablename__ = "stock_meta"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    market: Mapped[str] = mapped_column(String(8), index=True)
    exchange: Mapped[str] = mapped_column(String(16))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
