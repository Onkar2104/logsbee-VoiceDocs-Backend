"""Create consolidated per-user settings."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_user_settings"
down_revision = "0005_user_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("two_factor_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("default_language", sa.String(length=12), nullable=False, server_default="en"),
        sa.Column("automatic_backup_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_settings_user_id", "user_settings", ["user_id"], unique=True)

    # Preserve existing language choices when moving from user_preferences.
    op.execute("""
        INSERT INTO user_settings
            (id, user_id, two_factor_enabled, default_language,
             automatic_backup_enabled, created_at, updated_at)
        SELECT gen_random_uuid(), user_id, FALSE, transcription_language,
               TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM user_preferences
        ON CONFLICT (user_id) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_index("ix_user_settings_user_id", table_name="user_settings")
    op.drop_table("user_settings")
