from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

# 테스트(sqlite)에서는 JSON, 운영(PG)에서는 JSONB로 저장.
JSON_VARIANT = JSON().with_variant(JSONB(), "postgresql")
