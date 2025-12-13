"""Heroku Scheduler entry point for periodic uploads.

This script is designed to be run by Heroku Scheduler or cron jobs.
It reads enabled schedule settings from the database, scans configured
Google Drive folders, and processes uploads for all enabled users.

Usage:
    python -m app.tasks.scheduled_upload

Configuration:
    Schedule settings are stored in the database per user.
    Use the web UI to configure folder URL, max files, and other options.
"""

import asyncio
import logging
from typing import TYPE_CHECKING

from app.auth.oauth import get_oauth_service
from app.database import close_db, get_db_context, init_db
from app.drive.schemas import FolderUploadSettings
from app.drive.services import DriveService
from app.queue.worker import get_queue_worker
from app.settings.repositories import ScheduleSettingsRepository
from app.tasks.services import FolderUploadService
from app.youtube.quota import get_quota_tracker

if TYPE_CHECKING:
    from app.models import ScheduleSettings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def check_youtube_quota() -> bool:
    """Check if YouTube quota is available for uploads.
    
    Returns:
        True if quota is available, False otherwise
    """
    try:
        tracker = get_quota_tracker()
        # Check if we have quota for at least one upload (1600 units)
        if not tracker.can_perform("video_insert"):
            remaining = tracker.get_remaining_quota()
            logger.warning(
                "YouTube quota exhausted (remaining: %d units). "
                "Skipping scheduled run.",
                remaining,
            )
            return False
        return True
    except Exception as e:
        logger.warning("Failed to check quota: %s. Proceeding anyway.", e)
        return True  # Proceed if quota check fails


async def process_user_schedule(settings: "ScheduleSettings") -> int:
    """Process uploads for a single user's schedule settings.
    
    Args:
        settings: User's schedule settings from database
        
    Returns:
        Number of jobs added
    """
    user_id = settings.user_id
    folder_id = settings.folder_id

    logger.info("Processing schedule for user: %s", user_id)
    logger.info("  Folder ID: %s", folder_id)
    logger.info("  Max files: %d", settings.max_files_per_run)

    # Get user credentials
    oauth_service = get_oauth_service()
    credentials = await oauth_service.get_credentials(user_id)

    if not credentials:
        logger.error(
            "User '%s' not authenticated. "
            "Please login via web UI first. Skipping.",
            user_id,
        )
        return 0

    # Create services
    drive_service = DriveService(credentials=credentials)

    async with get_db_context() as db:
        folder_service = FolderUploadService(drive_service, db)

        # Build settings from database configuration
        upload_settings = FolderUploadSettings(
            title_template=settings.title_template,
            description_template=settings.description_template,
            default_privacy=settings.default_privacy,
            include_md5_hash=settings.include_md5_hash,
        )

        # Process folder
        logger.info("Scanning folder %s...", folder_id)
        result = await folder_service.process_folder(
            folder_id=folder_id,
            user_id=user_id,
            settings=upload_settings,
            recursive=settings.recursive,
            max_files=settings.max_files_per_run,
            skip_duplicates=settings.skip_duplicates,
        )

        logger.info(
            "User %s: Added %d jobs, Skipped %d files",
            user_id,
            len(result.added_jobs),
            len(result.skipped_files),
        )

        # Log skipped files for debugging
        for skipped in result.skipped_files[:5]:  # Limit to first 5
            logger.debug(
                "  Skipped: %s (%s)",
                skipped.file_name,
                skipped.reason,
            )

        return len(result.added_jobs)


async def run_scheduled_upload() -> None:
    """Main entry point for scheduled upload task.
    
    1. Checks YouTube quota availability
    2. Queries all enabled schedule settings from database
    3. For each enabled user, scans folder and adds jobs
    4. Processes the queue using batch mode
    """
    logger.info("=" * 60)
    logger.info("Starting scheduled upload...")
    logger.info("=" * 60)

    await init_db()

    try:
        # Check YouTube quota first to avoid unnecessary Drive API calls
        if not await check_youtube_quota():
            return

        # Get all enabled schedule settings
        async with get_db_context() as db:
            repo = ScheduleSettingsRepository(db)
            enabled_settings = await repo.get_all_enabled()

        if not enabled_settings:
            logger.warning("No enabled schedule settings found. Exiting.")
            return

        logger.info("Found %d enabled schedule setting(s)", len(enabled_settings))

        # Process each enabled user's schedule
        total_jobs_added = 0
        for settings in enabled_settings:
            try:
                jobs_added = await process_user_schedule(settings)
                total_jobs_added += jobs_added
            except Exception:
                logger.exception(
                    "Failed to process schedule for user %s",
                    settings.user_id,
                )
                # Continue with other users

        # Process queue if jobs were added
        if total_jobs_added > 0:
            logger.info("Starting batch processing for %d jobs...", total_jobs_added)
            worker = get_queue_worker()
            processed = await worker.process_batch()
            logger.info("Batch processing complete. Processed: %d", processed)
        else:
            logger.info("No new jobs to process.")

    except Exception:
        logger.exception("Scheduled upload failed")

    finally:
        await close_db()
        logger.info("=" * 60)
        logger.info("Scheduled upload finished.")
        logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_scheduled_upload())
