# 모델 레지스트리. Alembic autogenerate가 메타데이터를 인식하도록
# 모델 모듈을 여기서 import 한다.
from app.models.paper_account_model import PaperAccount
from app.models.paper_trade_model import PaperTrade
from app.models.refresh_token_model import RefreshToken
from app.models.user_model import User
from app.models.watchlist_model import Watchlist

__all__ = ["PaperAccount", "PaperTrade", "RefreshToken", "User", "Watchlist"]
