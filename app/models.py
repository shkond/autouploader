"""Database models for CloudVid Bridge."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UploadHistory(Base):
    """Record of uploaded videos for duplicate detection."""

    __tablename__ = "upload_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    drive_file_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    drive_file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    drive_md5_checksum: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )
    youtube_video_id: Mapped[str] = mapped_column(String(50), nullable=False)
    youtube_video_url: Mapped[str] = mapped_column(String(255), nullable=False)
    youtube_etag: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # YouTube API ETag for change detection
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # Last time video existence was verified on YouTube
    folder_path: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="completed"
    )  # completed, failed
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<UploadHistory(id={self.id}, "
            f"file={self.drive_file_name}, "
            f"youtube={self.youtube_video_id})>"
        )


class QueueJobModel(Base):
    """Persistent queue job for upload queue.
    
    This model stores upload jobs in the database for persistence
    across server restarts and for communication between web and worker processes.
    """

    __tablename__ = "queue_jobs"

    # UUID stored as String(36) for SQLite compatibility
    # Type annotation uses str to match actual database type
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )  # User who created this job
    drive_file_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    drive_file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    drive_md5_checksum: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # File size in bytes
    folder_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    batch_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False)  # VideoMetadata as JSON
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )  # pending, downloading, uploading, completed, failed, cancelled
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    video_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    video_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<QueueJobModel(id={self.id}, "
            f"file={self.drive_file_name}, "
            f"status={self.status})>"
        )


class OAuthToken(Base):
    """Encrypted OAuth token storage.
    
    Stores OAuth credentials with encryption for security.
    Tokens are encrypted using Fernet symmetric encryption.
    """

    __tablename__ = "oauth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True, index=True
    )  # Session identifier or user identifier
    encrypted_access_token: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_uri: Mapped[str] = mapped_column(
        String(255), nullable=False, default="https://oauth2.googleapis.com/token"
    )
    scopes: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON array
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<OAuthToken(id={self.id}, user_id={self.user_id})>"

