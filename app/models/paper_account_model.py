from sqlalchemy import Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PaperAccount(Base):
    """계정별 가상매매 예수금/시드. 매수·매도 시 cash 갱신 (feature-spec §4.6)."""

    __tablename__ = "paper_account"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    cash: Mapped[float] = mapped_column(Float)
    seed: Mapped[float] = mapped_column(Float)
