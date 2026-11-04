"""Create Google Drive connections and audio recording metadata."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_google_drive_recordings"
down_revision = "0002_documents_updated_by"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_drive_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("google_email", sa.String(320), nullable=False),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=False),
        sa.Column("recordings_folder_id", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_google_drive_connections_user_id", "google_drive_connections", ["user_id"], unique=True)

    op.create_table(
        "google_oauth_states",
        sa.Column("state", sa.String(128), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_google_oauth_states_user_id", "google_oauth_states", ["user_id"])

    op.create_table(
        "audio_recordings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("drive_file_id", sa.String(255), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("language", sa.String(20), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audio_recordings_user_id", "audio_recordings", ["user_id"])
    op.create_index("ix_audio_recordings_drive_file_id", "audio_recordings", ["drive_file_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_audio_recordings_drive_file_id", table_name="audio_recordings")
    op.drop_index("ix_audio_recordings_user_id", table_name="audio_recordings")
    op.drop_table("audio_recordings")
    op.drop_index("ix_google_oauth_states_user_id", table_name="google_oauth_states")
    op.drop_table("google_oauth_states")
    op.drop_index("ix_google_drive_connections_user_id", table_name="google_drive_connections")
    op.drop_table("google_drive_connections")
