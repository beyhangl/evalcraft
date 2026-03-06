"""Initial migration — create all tables.

Revision ID: 001_initial
Revises:
Create Date: 2026-03-06
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Teams
    op.create_table(
        "teams",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), unique=True, nullable=False),
        sa.Column("slug", sa.String(255), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), unique=True, nullable=False, index=True),
        sa.Column("hashed_password", sa.Text, nullable=False),
        sa.Column("full_name", sa.String(255), server_default=""),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # API Keys
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key_prefix", sa.String(8), nullable=False, index=True),
        sa.Column("key_hash", sa.Text, nullable=False, unique=True),
        sa.Column("name", sa.String(255), server_default=""),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Projects
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, server_default=""),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Cassettes
    op.create_table(
        "cassettes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(255), server_default=""),
        sa.Column("agent_name", sa.String(255), server_default=""),
        sa.Column("framework", sa.String(100), server_default=""),
        sa.Column("fingerprint", sa.String(64), server_default="", index=True),
        sa.Column("total_tokens", sa.Integer, server_default="0"),
        sa.Column("total_cost_usd", sa.Float, server_default="0"),
        sa.Column("total_duration_ms", sa.Float, server_default="0"),
        sa.Column("llm_call_count", sa.Integer, server_default="0"),
        sa.Column("tool_call_count", sa.Integer, server_default="0"),
        sa.Column("input_text", sa.Text, server_default=""),
        sa.Column("output_text", sa.Text, server_default=""),
        sa.Column("raw_data", postgresql.JSONB, nullable=False),
        sa.Column("git_sha", sa.String(40), server_default=""),
        sa.Column("branch", sa.String(255), server_default=""),
        sa.Column("ci_run_url", sa.Text, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )

    # Golden Sets
    op.create_table(
        "golden_sets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, server_default=""),
        sa.Column("version", sa.Integer, server_default="1"),
        sa.Column("thresholds", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("raw_data", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Regression severity enum
    regression_severity = postgresql.ENUM("INFO", "WARNING", "CRITICAL", name="regression_severity", create_type=True)
    regression_severity.create(op.get_bind(), checkfirst=True)

    # Regression Events
    op.create_table(
        "regression_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("cassette_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cassettes.id"), nullable=False),
        sa.Column("golden_set_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("golden_sets.id"), nullable=True),
        sa.Column("severity", regression_severity, nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("details", postgresql.JSONB, server_default="{}"),
        sa.Column("resolved", sa.Boolean, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )

    # Alert channel enum
    alert_channel = postgresql.ENUM("email", "slack", "webhook", name="alert_channel", create_type=True)
    alert_channel.create(op.get_bind(), checkfirst=True)

    # Alerts
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("regression_event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("regression_events.id"), nullable=False),
        sa.Column("channel", alert_channel, nullable=False),
        sa.Column("sent", sa.Boolean, server_default=sa.text("false")),
        sa.Column("error", sa.Text, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("alerts")
    op.drop_table("regression_events")
    op.drop_table("golden_sets")
    op.drop_table("cassettes")
    op.drop_table("projects")
    op.drop_table("api_keys")
    op.drop_table("users")
    op.drop_table("teams")
    op.execute("DROP TYPE IF EXISTS regression_severity")
    op.execute("DROP TYPE IF EXISTS alert_channel")
