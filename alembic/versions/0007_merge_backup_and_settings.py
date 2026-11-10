"""Merge the independent audio-fallback and user-settings migration branches."""

revision = "0007_merge_backup_and_settings"
down_revision = ("0005_database_backup_fallback", "0006_user_settings")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Both parent migrations are schema changes; no additional operation is needed.
    pass


def downgrade() -> None:
    # A merge revision has no independent schema changes to reverse.
    pass
