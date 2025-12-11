"""Heroku Scheduler entry point for periodic uploads.

This script is designed to be run by Heroku Scheduler or cron jobs.
It scans a configured Google Drive folder, adds new videos to the queue,
and processes them using the batch processing mode.

Usage:
    python -m app.tasks.scheduled_upload

Environment Variables:
    TARGET_USER_ID: User ID for authentication (default: "admin")
    TARGET_FOLDER_ID: Google Drive folder ID to scan (default: "root")
    MAX_FILES_PER_RUN: Maximum files to process per run (default: 50)
"""

import asyncio
import logging
import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.getcwd())

from app.auth.oauth import get_oauth_service
from app.database import close_db, get_db_context, init_db
from app.drive.schemas import FolderUploadSettings
from app.drive.services import DriveService
from app.queue.worker import get_queue_worker
from app.tasks.services import FolderUploadService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run_scheduled_upload() -> None:
    """Main entry point for scheduled upload task.

    1. Authenticates as the configured user
    2. Scans the target folder for videos
    3. Adds new videos to the queue (with duplicate detection)
    4. Processes the queue using batch mode
    """
    # Read configuration from environment
    user_id = os.getenv("TARGET_USER_ID", "admin")
    folder_id = os.getenv("TARGET_FOLDER_ID", "root")
    max_files = int(os.getenv("MAX_FILES_PER_RUN", "50"))

    logger.info("Starting scheduled upload...")
    logger.info("  User ID: %s", user_id)
    logger.info("  Folder ID: %s", folder_id)
    logger.info("  Max files: %d", max_files)

    await init_db()

    try:
        # Get user credentials
        oauth_service = get_oauth_service()
        credentials = await oauth_service.get_credentials(user_id)

        if not credentials:
            logger.error(
                "User '%s' not authenticated. "
                "Please login via web UI first.",
                user_id,
            )
            return

        # Create services (Manual DI)
        drive_service = DriveService(credentials=credentials)

        async with get_db_context() as db:
            folder_service = FolderUploadService(drive_service, db)

            # Default settings for scheduled uploads
            settings = FolderUploadSettings(
                title_template="{filename}",
                description_template="Uploaded from {folder_path}",
                default_privacy="private",
                include_md5_hash=True,
            )

            # Process folder
            logger.info("Scanning folder %s...", folder_id)
            result = await folder_service.process_folder(
                folder_id=folder_id,
                user_id=user_id,
                settings=settings,
                recursive=True,
                max_files=max_files,
                skip_duplicates=True,
            )

            logger.info(
                "Scan complete. Added: %d, Skipped: %d",
                len(result.added_jobs),
                len(result.skipped_files),
            )

            # Log skipped files for debugging
            for skipped in result.skipped_files[:10]:  # Limit to first 10
                logger.debug(
                    "  Skipped: %s (%s)",
                    skipped.file_name,
                    skipped.reason,
                )

        # Process queue if jobs were added
        if result.added_jobs:
            logger.info("Starting batch processing...")
            worker = get_queue_worker()
            processed = await worker.process_batch()
            logger.info("Batch processing complete. Processed: %d", processed)
        else:
            logger.info("No new jobs to process.")

    except Exception:
        logger.exception("Scheduled upload failed")

    finally:
        await close_db()
        logger.info("Scheduled upload finished.")


if __name__ == "__main__":
    asyncio.run(run_scheduled_upload())
