"""Repository for schedule settings database operations."""

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models import ScheduleSettings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class ScheduleSettingsRepository:
    """Repository for schedule settings CRUD operations."""

    def __init__(self, db: "AsyncSession") -> None:
        """Initialize repository with database session."""
        self._db = db

    async def get_by_user_id(self, user_id: str) -> ScheduleSettings | None:
        """Get schedule settings for a specific user.
        
        Args:
            user_id: User identifier
            
        Returns:
            ScheduleSettings or None if not found
        """
        result = await self._db.execute(
            select(ScheduleSettings).where(ScheduleSettings.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_all_enabled(self) -> list[ScheduleSettings]:
        """Get all enabled schedule settings.
        
        Used by Heroku Scheduler to process all enabled users.
        
        Returns:
            List of enabled ScheduleSettings
        """
        result = await self._db.execute(
            select(ScheduleSettings).where(ScheduleSettings.is_enabled == True)  # noqa: E712
        )
        return list(result.scalars().all())

    async def create(
        self,
        user_id: str,
        folder_url: str,
        folder_id: str,
        **kwargs,
    ) -> ScheduleSettings:
        """Create new schedule settings for a user.
        
        Args:
            user_id: User identifier
            folder_url: Full Google Drive folder URL
            folder_id: Extracted folder ID
            **kwargs: Additional settings fields
            
        Returns:
            Created ScheduleSettings
        """
        settings = ScheduleSettings(
            user_id=user_id,
            folder_url=folder_url,
            folder_id=folder_id,
            **kwargs,
        )
        self._db.add(settings)
        await self._db.flush()
        await self._db.refresh(settings)
        return settings

    async def update(
        self,
        settings: ScheduleSettings,
        **kwargs,
    ) -> ScheduleSettings:
        """Update existing schedule settings.
        
        Args:
            settings: Existing ScheduleSettings to update
            **kwargs: Fields to update
            
        Returns:
            Updated ScheduleSettings
        """
        for key, value in kwargs.items():
            if value is not None and hasattr(settings, key):
                setattr(settings, key, value)
        
        await self._db.flush()
        await self._db.refresh(settings)
        return settings

    async def delete(self, settings: ScheduleSettings) -> None:
        """Delete schedule settings.
        
        Args:
            settings: ScheduleSettings to delete
        """
        await self._db.delete(settings)
        await self._db.flush()
