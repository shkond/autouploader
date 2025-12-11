# Module Reference

## Overview

This document describes each module's responsibilities, key classes, and their relationships.

---

## Core Module (`app/core/`)

### `dependencies.py`
Centralized FastAPI dependency injection configuration.

**Key Functions:**

| Function | Purpose | Returns |
|----------|---------|---------|
| `get_user_credentials()` | Get OAuth credentials (required) | `Credentials` |
| `get_optional_credentials()` | Get OAuth credentials (optional) | `Credentials \| None` |
| `get_oauth_service_dep()` | Get OAuthService singleton | `OAuthService` |
| `get_session_data()` | Get session from cookie | `dict \| None` |
| `require_session()` | Require valid session | `dict` |
| `get_drive_service()` | Get DriveService with credentials | `DriveService` |
| `get_youtube_service()` | Get YouTubeService with credentials | `YouTubeService` |
| `get_queue_repository()` | Get QueueRepository with DB session | `QueueRepository` |
| `get_queue_service()` | Get QueueService with DB session | `QueueService` |
| `get_user_id_from_session()` | Extract user_id from session | `str` |

### `protocols.py`
Protocol definitions (interfaces) for repository layer.

**Protocols:**

| Protocol | Purpose |
|----------|---------|
| `DriveRepositoryProtocol` | Google Drive API operations |
| `YouTubeRepositoryProtocol` | YouTube Data API operations |
| `QueueRepositoryProtocol` | Queue database operations |
| `UploadHistoryRepositoryProtocol` | Upload history database operations |

---

## Auth Module (`app/auth/`)

Handles both app-level authentication and Google OAuth.

### `oauth.py` - OAuthService

**Class: `OAuthService`**

| Method | Purpose |
|--------|---------|
| `get_auth_url()` | Generate Google OAuth authorization URL |
| `get_credentials_from_code()` | Exchange auth code for credentials |
| `save_credentials()` | Save encrypted tokens to database |
| `get_stored_credentials()` | Retrieve and decrypt stored credentials |
| `clear_credentials()` | Remove stored credentials |

**Singleton Access:**
```python
from app.auth.oauth import get_oauth_service
oauth_service = get_oauth_service()
```

### `simple_auth.py` - Session Management

**Class: `SessionManager`**

| Method | Purpose |
|--------|---------|
| `create_session()` | Create new session with user_id |
| `get_session()` | Retrieve session by token |
| `delete_session()` | Remove session |
| `verify_credentials()` | Check username/password |

**Singleton Access:**
```python
from app.auth.simple_auth import get_session_manager
session_manager = get_session_manager()
```

### `routes.py`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/auth/login` | GET | Login page |
| `/auth/login` | POST | Process login |
| `/auth/dashboard` | GET | Dashboard page |
| `/auth/google` | GET | Start OAuth flow |
| `/auth/callback` | GET | OAuth callback |
| `/auth/status` | GET | Check auth status |
| `/auth/logout` | GET | Logout |

---

## Drive Module (`app/drive/`)

Google Drive integration for file browsing and downloading.

### `service.py` - DriveService

**Class: `DriveService`**

| Method | Purpose |
|--------|---------|
| `list_files()` | List files in a folder |
| `get_file_metadata()` | Get file metadata with MD5 |
| `get_folder_info()` | Get folder metadata |
| `scan_folder()` | Scan folder (optionally recursive) |
| `get_file_content_stream()` | Get download stream |

**Constructor:**
```python
drive_service = DriveService(credentials: Credentials)
```

### `repositories.py` - DriveRepository

Low-level Google Drive API calls. Implements `DriveRepositoryProtocol`.

### `routes.py`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/drive/files` | GET | List folder contents |
| `/drive/scan` | POST | Scan folder for videos |
| `/drive/file/{file_id}` | GET | Get file info |

### `schemas.py`

| Schema | Purpose |
|--------|---------|
| `DriveFile` | File metadata response |
| `DriveFolder` | Folder with files/subfolders |
| `ScanRequest` | Folder scan request |
| `ScanResponse` | Scan results |

---

## YouTube Module (`app/youtube/`)

YouTube Data API integration for video uploads.

### `service.py` - YouTubeService

**Class: `YouTubeService`**

| Method | Purpose |
|--------|---------|
| `upload_video_async()` | Upload from BytesIO (async) |
| `upload_video()` | Upload from BytesIO (sync) |
| `upload_from_drive_async()` | Download from Drive → Upload to YouTube |
| `get_channel_info()` | Get user's channel info |
| `list_my_videos()` | List uploaded videos (100 quota units) |
| `list_my_videos_optimized()` | List videos (1-2 quota units) |
| `check_video_exists_on_youtube()` | Verify video exists (1 quota unit) |
| `get_videos_batch()` | Get multiple videos info (1 quota unit) |

**Constructor:**
```python
youtube_service = YouTubeService(credentials: Credentials)
```

### `quota.py` - QuotaTracker

**Class: `QuotaTracker`**

| Method | Purpose |
|--------|---------|
| `record_usage()` | Record API usage |
| `get_usage()` | Get current usage stats |
| `get_remaining()` | Estimate remaining quota |
| `is_quota_exceeded()` | Check if near limit |

**Singleton Access:**
```python
from app.youtube.quota import get_quota_tracker
tracker = get_quota_tracker()
```

### `routes.py`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/youtube/channel` | GET | Get channel info |
| `/youtube/videos` | GET | List uploaded videos |
| `/youtube/upload` | POST | Direct upload from Drive |
| `/youtube/quota` | GET | Get quota usage |

### `schemas.py`

| Schema | Purpose |
|--------|---------|
| `VideoMetadata` | Upload metadata (title, description, etc.) |
| `UploadProgress` | Progress update during upload |
| `UploadResult` | Upload completion result |

---

## Queue Module (`app/queue/`)

Database-backed job queue for upload tasks.

### `worker.py` - QueueWorker

**Class: `QueueWorker`**

| Method | Purpose |
|--------|---------|
| `start()` | Start background worker |
| `stop()` | Stop worker gracefully |
| `is_running()` | Check if worker is active |
| `process_batch()` | Process queue until empty (for Scheduler) |
| `_process_loop()` | Main polling loop |
| `_process_job()` | Process single job |
| `_pre_upload_check()` | Check for duplicates |
| `_save_upload_history()` | Save completed upload |

**Singleton Access:**
```python
from app.queue.worker import get_queue_worker
worker = get_queue_worker()
```

**Standalone Execution:**
```bash
# Continuous worker (dyno: worker)
python -m app.queue.worker

# Batch mode (Heroku Scheduler)
python -m app.tasks.scheduled_upload
```

### `manager_db.py` - QueueManagerDB

Database-backed queue manager.

| Method | Purpose |
|--------|---------|
| `add_job()` | Add job to queue |
| `get_job()` | Get job by ID |
| `get_jobs()` | List jobs with filters |
| `update_job_status()` | Update job status |
| `get_next_pending_job()` | Fetch next job to process |
| `get_queue_status()` | Get queue statistics |

### `repositories.py` - QueueRepository

Low-level database operations for queue. Implements `QueueRepositoryProtocol`.

### `services.py` - QueueService

Business logic layer for queue operations.

### `routes.py`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/queue/status` | GET | Get queue status |
| `/queue/jobs` | GET | List all jobs |
| `/queue/jobs` | POST | Add job |
| `/queue/jobs/bulk` | POST | Add multiple jobs |
| `/queue/jobs/{job_id}` | GET | Get job details |
| `/queue/jobs/{job_id}/cancel` | POST | Cancel job |
| `/queue/jobs/{job_id}` | DELETE | Delete job |
| `/queue/clear` | POST | Clear completed jobs |
| `/queue/worker/start` | POST | Start worker |
| `/queue/worker/stop` | POST | Stop worker |

### `schemas.py`

| Schema | Purpose |
|--------|---------|
| `QueueJobCreate` | Job creation request |
| `QueueJob` | Job response with all fields |
| `QueueStatus` | Queue statistics |
| `JobStatus` | Status enum (pending, uploading, etc.) |

---

## Tasks Module (`app/tasks/`)

Scheduled tasks and shared services for batch operations.

### `services.py` - FolderUploadService

**Class: `FolderUploadService`**

Shared logic for folder scanning and queue management.

| Method | Purpose |
|--------|---------|
| `process_folder()` | Scan folder and add videos to queue |
| `_check_duplicates()` | Check queue AND UploadHistory |
| `_create_video_metadata()` | Generate metadata from templates |

**Usage:**
```python
from app.tasks.services import FolderUploadService

async with get_db_context() as db:
    folder_service = FolderUploadService(drive_service, db)
    result = await folder_service.process_folder(
        folder_id="...",
        user_id="admin",
        settings=FolderUploadSettings(),
    )
```

### `scheduled_upload.py`

CLI entry point for Heroku Scheduler.

**Environment Variables:**

| Variable | Default | Purpose |
|----------|---------|--------|
| `TARGET_USER_ID` | `admin` | User ID for auth |
| `TARGET_FOLDER_ID` | `root` | Drive folder to scan |
| `MAX_FILES_PER_RUN` | `50` | Max files per run |

**Execution:**
```bash
python -m app.tasks.scheduled_upload
```

---

## App-Level Modules

### `config.py` - Settings

**Class: `Settings`** (Pydantic BaseSettings)

All environment variables are loaded here. Access via:
```python
from app.config import get_settings
settings = get_settings()
```

### `database.py`

| Function | Purpose |
|----------|---------|
| `init_db()` | Create all tables |
| `get_db()` | Async session dependency |
| `get_sync_session()` | Sync session for worker |

### `models.py`

| Model | Table | Purpose |
|-------|-------|---------|
| `QueueJobModel` | `queue_jobs` | Persistent upload queue |
| `OAuthToken` | `oauth_tokens` | Encrypted OAuth tokens |
| `UploadHistory` | `upload_history` | Upload records for dedup |

### `crypto.py`

| Function | Purpose |
|----------|---------|
| `get_cipher()` | Get Fernet cipher instance |
| `encrypt_token()` | Encrypt token string |
| `decrypt_token()` | Decrypt token string |

### `exceptions.py`

| Exception | Purpose |
|-----------|---------|
| `CloudVidBridgeError` | Base exception |
| `AuthenticationError` | Auth failures |
| `DriveAPIError` | Drive API errors |
| `YouTubeAPIError` | YouTube API errors |
| `QuotaExceededError` | API quota limit |
| `FileSizeExceededError` | File too large |
| `DuplicateUploadError` | Already uploaded |
