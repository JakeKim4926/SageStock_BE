# 모델 레지스트리. Alembic autogenerate가 메타데이터를 인식하도록
# 모델 모듈을 여기서 import 한다.
from app.models.macro_entity_alias_model import MacroEntityAlias
from app.models.macro_event_chain_model import MacroEventChain
from app.models.macro_event_model import MacroEvent
from app.models.macro_event_outcome_model import MacroEventOutcome
from app.models.macro_event_source_model import MacroEventSource
from app.models.macro_market_reaction_snapshot_model import MacroMarketReactionSnapshot
from app.models.macro_source_freshness_model import MacroSourceFreshness
from app.models.paper_account_model import PaperAccount
from app.models.paper_trade_model import PaperTrade
from app.models.refresh_token_model import RefreshToken
from app.models.stock_meta_model import StockMeta
from app.models.user_model import User
from app.models.watchlist_model import Watchlist

__all__ = [
    "MacroEntityAlias",
    "MacroEvent",
    "MacroEventChain",
    "MacroEventOutcome",
    "MacroEventSource",
    "MacroMarketReactionSnapshot",
    "MacroSourceFreshness",
    "PaperAccount",
    "PaperTrade",
    "RefreshToken",
    "StockMeta",
    "User",
    "Watchlist",
]
