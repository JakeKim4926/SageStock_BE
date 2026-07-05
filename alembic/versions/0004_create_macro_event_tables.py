"""create macro event engine tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-05

macro-event-engine Phase 0 (SPEC §16). 테이블 7종 + 소스 레지스트리 시드 8행(§4).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_VARIANT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

# 소스 레지스트리 시드 (SPEC §4). KR_MARKET_DATA는 역할 없는 데이터 소스.
SOURCE_SEED_ROWS = [
    {
        "source_id": "US_SEC_EDGAR",
        "target_description": "Form 4, 13D/13G, 8-K",
        "source_roles": ["CONFIRMATION"],
        "collection_interval": "15~30분",
        "observable_at_basis": "filing accepted time",
        "is_active": True,
    },
    {
        "source_id": "US_SAM_GOV",
        "target_description": "조달 opportunity",
        "source_roles": ["LEAD"],
        "collection_interval": "1일 1~2회",
        "observable_at_basis": "opportunity posted date",
        "is_active": True,
    },
    {
        "source_id": "US_USASPENDING",
        "target_description": "award / obligation",
        "source_roles": ["CONFIRMATION", "OUTCOME"],
        "collection_interval": "1일 1회",
        "observable_at_basis": "award publication date",
        "is_active": True,
    },
    {
        "source_id": "US_DEFENSE_CONTRACTS",
        "target_description": "일일 국방 계약 발표",
        "source_roles": ["LEAD", "CONFIRMATION"],
        "collection_interval": "미 동부 17:00 발표 직후 1회 (≈06:00 KST)",
        "observable_at_basis": "발표 게시 시각",
        "is_active": True,
    },
    {
        "source_id": "US_WHITE_HOUSE",
        "target_description": "Presidential Actions",
        "source_roles": ["LEAD"],
        "collection_interval": "1시간",
        "observable_at_basis": "published time",
        "is_active": True,
    },
    {
        "source_id": "US_FEDERAL_REGISTER",
        "target_description": "Presidential Documents",
        "source_roles": ["CONFIRMATION"],
        "collection_interval": "1일 1~2회",
        "observable_at_basis": "publication date/time",
        "is_active": True,
    },
    {
        "source_id": "KR_OPENDART",
        "target_description": "공급계약, 대량보유, 임원·주요주주",
        "source_roles": ["CONFIRMATION"],
        "collection_interval": "EOD 1회 (v1)",
        "observable_at_basis": "접수/공시 시각",
        "is_active": True,
    },
    {
        "source_id": "KR_MARKET_DATA",
        "target_description": "KRX 가격/지수",
        "source_roles": [],
        "collection_interval": "EOD 1회",
        "observable_at_basis": "—",
        "is_active": True,
    },
]


def upgrade() -> None:
    sources_table = op.create_table(
        "macro_event_sources",
        sa.Column("source_id", sa.String(length=32), nullable=False),
        sa.Column("target_description", sa.String(length=200), nullable=False),
        sa.Column("source_roles", JSON_VARIANT, nullable=False),
        sa.Column("collection_interval", sa.String(length=100), nullable=False),
        sa.Column("observable_at_basis", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("source_id"),
    )
    op.bulk_insert(sources_table, SOURCE_SEED_ROWS)

    op.create_table(
        "macro_event_chains",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chain_key", sa.String(length=300), nullable=False),
        sa.Column("highest_certainty_level", sa.String(length=4), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_macro_event_chains_chain_key", "macro_event_chains", ["chain_key"], unique=True
    )

    op.create_table(
        "macro_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_unique_id", sa.String(length=200), nullable=False),
        sa.Column("source_id", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("event_effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("document_signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collected_at_kst", sa.DateTime(timezone=True), nullable=False),
        sa.Column("publicly_observable_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latency_reference_type", sa.String(length=32), nullable=False),
        sa.Column("event_chain_id", sa.Integer(), nullable=True),
        sa.Column("event_status", sa.String(length=20), nullable=False),
        sa.Column("primary_domain", sa.String(length=32), nullable=True),
        sa.Column("secondary_domains", JSON_VARIANT, nullable=True),
        sa.Column("domain_confidence", sa.Float(), nullable=True),
        sa.Column("matched_keywords", JSON_VARIANT, nullable=True),
        sa.Column("domain_assignment_version", sa.String(length=40), nullable=True),
        sa.Column("linked_entities", JSON_VARIANT, nullable=True),
        sa.Column("certainty_level", sa.String(length=4), nullable=False),
        sa.Column("priority_score", sa.Integer(), nullable=True),
        sa.Column("propagation_stage", sa.Integer(), nullable=True),
        sa.Column("raw_payload", JSON_VARIANT, nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["source_id"], ["macro_event_sources.source_id"]),
        sa.ForeignKeyConstraint(
            ["event_chain_id"], ["macro_event_chains.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_id", "event_unique_id", name="uq_macro_events_source_unique_id"
        ),
    )
    op.create_index("ix_macro_events_source_id", "macro_events", ["source_id"], unique=False)
    op.create_index("ix_macro_events_event_type", "macro_events", ["event_type"], unique=False)
    op.create_index(
        "ix_macro_events_publicly_observable_at",
        "macro_events",
        ["publicly_observable_at"],
        unique=False,
    )
    op.create_index(
        "ix_macro_events_event_chain_id", "macro_events", ["event_chain_id"], unique=False
    )
    op.create_index(
        "ix_macro_events_primary_domain", "macro_events", ["primary_domain"], unique=False
    )
    op.create_index(
        "ix_macro_events_priority_score", "macro_events", ["priority_score"], unique=False
    )

    op.create_table(
        "macro_event_outcomes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("event_chain_id", sa.Integer(), nullable=True),
        sa.Column("horizon", sa.String(length=4), nullable=False),
        sa.Column("measured_at_kst", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reaction_target_type", sa.String(length=20), nullable=False),
        sa.Column("reaction_target_id", sa.String(length=40), nullable=True),
        sa.Column("price_change_pct", sa.Float(), nullable=True),
        sa.Column("volume_change_ratio", sa.Float(), nullable=True),
        sa.Column("benchmark_change_pct", sa.Float(), nullable=True),
        sa.Column("excess_return_pct", sa.Float(), nullable=True),
        sa.Column("outcome_label", sa.String(length=20), nullable=False),
        sa.Column("score_version", sa.String(length=40), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["event_id"], ["macro_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["event_chain_id"], ["macro_event_chains.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "horizon", name="uq_macro_event_outcomes_event_horizon"),
    )
    op.create_index(
        "ix_macro_event_outcomes_event_id", "macro_event_outcomes", ["event_id"], unique=False
    )
    op.create_index(
        "ix_macro_event_outcomes_event_chain_id",
        "macro_event_outcomes",
        ["event_chain_id"],
        unique=False,
    )

    op.create_table(
        "macro_market_reaction_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("measured_at_kst", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reaction_target_type", sa.String(length=20), nullable=False),
        sa.Column("reaction_target_id", sa.String(length=40), nullable=True),
        sa.Column("reaction_target_status", sa.String(length=30), nullable=False),
        sa.Column("basket_mapping_status", sa.String(length=20), nullable=True),
        sa.Column("basket_mapping_reason", sa.Text(), nullable=True),
        sa.Column("market_latency_status", sa.String(length=20), nullable=True),
        sa.Column("data_quality", sa.String(length=24), nullable=True),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("change_percent", sa.Float(), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["event_id"], ["macro_events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_macro_market_reaction_snapshots_event_id",
        "macro_market_reaction_snapshots",
        ["event_id"],
        unique=False,
    )

    op.create_table(
        "macro_source_freshness",
        sa.Column("source_id", sa.String(length=32), nullable=False),
        sa.Column("last_success_at_kst", sa.DateTime(timezone=True), nullable=True),
        sa.Column("freshness_status", sa.String(length=12), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["macro_event_sources.source_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("source_id"),
    )

    op.create_table(
        "macro_entity_alias_map",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("canonical_entity_name", sa.String(length=200), nullable=False),
        sa.Column("alias_name", sa.String(length=200), nullable=False),
        sa.Column("normalized_alias", sa.String(length=200), nullable=False),
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("exchange", sa.String(length=16), nullable=False),
        sa.Column("cik", sa.String(length=10), nullable=True),
        sa.Column("corp_code", sa.String(length=8), nullable=True),
        sa.Column("uei", sa.String(length=12), nullable=True),
        sa.Column("country", sa.String(length=8), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("mapping_confidence", sa.String(length=8), nullable=False),
        sa.Column("verified_by", sa.String(length=64), nullable=False),
        sa.Column("verified_at", sa.Date(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_macro_entity_alias_map_normalized_alias",
        "macro_entity_alias_map",
        ["normalized_alias"],
        unique=False,
    )
    op.create_index(
        "ix_macro_entity_alias_map_cik", "macro_entity_alias_map", ["cik"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_macro_entity_alias_map_cik", table_name="macro_entity_alias_map")
    op.drop_index(
        "ix_macro_entity_alias_map_normalized_alias", table_name="macro_entity_alias_map"
    )
    op.drop_table("macro_entity_alias_map")
    op.drop_table("macro_source_freshness")
    op.drop_index(
        "ix_macro_market_reaction_snapshots_event_id",
        table_name="macro_market_reaction_snapshots",
    )
    op.drop_table("macro_market_reaction_snapshots")
    op.drop_index("ix_macro_event_outcomes_event_chain_id", table_name="macro_event_outcomes")
    op.drop_index("ix_macro_event_outcomes_event_id", table_name="macro_event_outcomes")
    op.drop_table("macro_event_outcomes")
    op.drop_index("ix_macro_events_priority_score", table_name="macro_events")
    op.drop_index("ix_macro_events_primary_domain", table_name="macro_events")
    op.drop_index("ix_macro_events_event_chain_id", table_name="macro_events")
    op.drop_index("ix_macro_events_publicly_observable_at", table_name="macro_events")
    op.drop_index("ix_macro_events_event_type", table_name="macro_events")
    op.drop_index("ix_macro_events_source_id", table_name="macro_events")
    op.drop_table("macro_events")
    op.drop_index("ix_macro_event_chains_chain_key", table_name="macro_event_chains")
    op.drop_table("macro_event_chains")
    op.drop_table("macro_event_sources")
