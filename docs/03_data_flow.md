# Data Flow

## Main Upload Pipeline

This document describes the data flow for the primary use case: uploading videos from Google Drive to YouTube.

### 1. Job Creation Flow

```
User clicks "Add to Queue" on dashboard
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│              POST /queue/jobs                                │
│              (app/queue/routes.py)                           │
├─────────────────────────────────────────────────────────────┤
│  1. Extract user_id from session                            │
│  2. Validate QueueJobCreate schema                          │
│  3. Check for MD5 duplicates (optional)                     │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              QueueService.add_job()                          │
│              (app/queue/services.py)                         │
├─────────────────────────────────────────────────────────────┤
│  1. Generate UUID for job                                   │
│  2. Serialize VideoMetadata to JSON                         │
│  3. Create QueueJobModel instance                           │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              QueueRepository.add_job()                       │
│              (app/queue/repositories.py)                     │
├─────────────────────────────────────────────────────────────┤
│  1. Insert into queue_jobs table                            │
│  2. Commit transaction                                      │
│  3. Return created QueueJob                                 │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
              Job status: "pending"
              Ready for worker pickup
```

### 2. Job Processing Flow (Worker)

```
┌─────────────────────────────────────────────────────────────┐
│              QueueWorker._process_loop()                     │
│              (app/queue/worker.py)                           │
├─────────────────────────────────────────────────────────────┤
│  Loop every 5 seconds:                                      │
│  1. Check if _running is True                               │
│  2. Call get_next_pending_job()                             │
│  3. If job found, call _process_job(job_id)                 │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              QueueWorker._process_job(job_id)                │
├─────────────────────────────────────────────────────────────┤
│  1. Update job status to "downloading"                      │
│  2. Get user credentials from OAuthService                  │
│  3. Create DriveService and YouTubeService                  │
│  4. Run pre-upload duplicate check                          │
│  5. Call YouTubeService.upload_from_drive_async()           │
│  6. Update job status to "completed" or "failed"            │
│  7. Save to upload_history on success                       │
└─────────────────────────────────────────────────────────────┘
```

### 3. Upload Execution Flow

```
┌─────────────────────────────────────────────────────────────┐
│        YouTubeService.upload_from_drive_async()              │
│        (app/youtube/service.py)                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Phase 1: Download from Drive                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  1. Create DriveService with credentials                │ │
│  │  2. Get file metadata (name, size, mime_type)           │ │
│  │  3. Create temp file on disk                            │ │
│  │  4. Download in chunks using MediaIoBaseDownload        │ │
│  │  5. Report progress (0-50%)                             │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  Phase 2: Upload to YouTube                                 │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  1. Create MediaFileUpload with resumable=True          │ │
│  │  2. Build videos().insert() request                     │ │
│  │  3. Execute resumable upload with next_chunk()          │ │
│  │  4. Report progress (50-100%)                           │ │
│  │  5. Return UploadResult (video_id, video_url)           │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  Cleanup: Delete temp file                                  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 4. Batch Processing / Scheduler Flow

For Heroku Scheduler or cron-like execution:

```
python -m app.tasks.scheduled_upload
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│              run_scheduled_upload()                          │
│              (app/tasks/scheduled_upload.py)                 │
├─────────────────────────────────────────────────────────────┤
│  1. Read env: TARGET_USER_ID, TARGET_FOLDER_ID              │
│  2. Initialize database                                      │
│  3. Get user credentials from OAuthService                   │
│  4. Create DriveService, FolderUploadService                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              FolderUploadService.process_folder()            │
│              (app/tasks/services.py)                         │
├─────────────────────────────────────────────────────────────┤
│  1. Scan Drive folder for videos                            │
│  2. Check each file for duplicates:                         │
│     - Queue (file_id, md5)                                  │
│     - UploadHistory (md5)                                   │
│  3. Add non-duplicate videos to queue                       │
│  4. Return FolderProcessResult                              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              QueueWorker.process_batch()                     │
│              (app/queue/worker.py)                           │
├─────────────────────────────────────────────────────────────┤
│  1. Check quota availability                                │
│  2. Loop: get_next_pending_job()                            │
│  3. For each job: call _process_job()                       │
│  4. Stop when queue empty or quota exhausted                │
│  5. Return processed count                                  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
              Process exits (Scheduler complete)
```

## Duplicate Detection Flow

### Pre-Upload Check

```
┌─────────────────────────────────────────────────────────────┐
│           QueueWorker._pre_upload_check()                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Step 1: Check upload_history table                         │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  SELECT * FROM upload_history                           │ │
│  │  WHERE drive_md5_checksum = :md5                        │ │
│  │  ORDER BY uploaded_at DESC LIMIT 1                      │ │
│  └──────────────────────────┬─────────────────────────────┘ │
│                             │                                │
│              ┌──────────────┴──────────────┐                │
│              │      Found in history?       │                │
│              └──────────────┬──────────────┘                │
│                    │                │                        │
│                   Yes              No                        │
│                    │                │                        │
│                    ▼                ▼                        │
│  Step 2: Verify on YouTube    Step 3: Allow upload          │
│  ┌───────────────────────┐    ┌───────────────────────┐    │
│  │ check_video_exists_on │    │ Return:               │    │
│  │ _youtube(video_id)    │    │ { skip: false }       │    │
│  └───────────┬───────────┘    └───────────────────────┘    │
│              │                                               │
│      ┌───────┴───────┐                                      │
│      │  Still exists? │                                      │
│      └───────┬───────┘                                      │
│         │         │                                          │
│        Yes       No                                          │
│         │         │                                          │
│         ▼         ▼                                          │
│    Skip upload   Allow upload                                │
│    (return      (video was                                   │
│    existing     deleted)                                     │
│    video_id)                                                 │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Authentication Data Flow

### OAuth Token Storage

```
Google OAuth Callback
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│         OAuthService.save_credentials()                      │
│         (app/auth/oauth.py)                                  │
├─────────────────────────────────────────────────────────────┤
│  1. Get credentials object from Google                      │
│  2. Extract access_token, refresh_token, expiry             │
│  3. Encrypt tokens using Fernet (app/crypto.py)             │
│  4. Upsert into oauth_tokens table                          │
└─────────────────────────────────────────────────────────────┘

Data stored in database:
┌─────────────────────────────────────────────────────────────┐
│  user_id: "session_abc123"                                   │
│  encrypted_access_token: "gAAA...encrypted..."               │
│  encrypted_refresh_token: "gAAA...encrypted..."              │
│  scopes: '["drive.readonly", "youtube.upload"]'             │
│  expires_at: "2025-12-11T12:00:00Z"                         │
└─────────────────────────────────────────────────────────────┘
```

### Credential Retrieval

```
API Request with session cookie
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│          get_user_credentials()                              │
│          (app/core/dependencies.py)                          │
├─────────────────────────────────────────────────────────────┤
│  1. Extract session_token from cookie                       │
│  2. Get user_id from SessionManager                         │
│  3. Call OAuthService.get_stored_credentials(user_id)       │
│                                                              │
│    ┌─────────────────────────────────────────────────────┐  │
│    │  OAuthService.get_stored_credentials()              │  │
│    │  1. Query oauth_tokens by user_id                   │  │
│    │  2. Decrypt access_token and refresh_token          │  │
│    │  3. Check expiry, refresh if needed                 │  │
│    │  4. Return google.oauth2.credentials.Credentials    │  │
│    └─────────────────────────────────────────────────────┘  │
│                                                              │
│  4. Return Credentials object                               │
│  5. If any step fails, raise HTTPException(401)             │
└─────────────────────────────────────────────────────────────┘
```

## Progress Callback Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    Upload Progress Flow                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  YouTubeService                                             │
│       │                                                      │
│       │ progress_callback(UploadProgress)                   │
│       ▼                                                      │
│  QueueWorker._process_job.progress_callback()               │
│       │                                                      │
│       │ Update job in database                              │
│       ▼                                                      │
│  QueueRepository.update_job_progress()                      │
│       │                                                      │
│       │ UPDATE queue_jobs SET progress=X, message=Y         │
│       ▼                                                      │
│  Database (queue_jobs table)                                │
│       │                                                      │
│       │ Dashboard polls GET /queue/jobs                     │
│       ▼                                                      │
│  User sees progress update                                  │
│                                                              │
└─────────────────────────────────────────────────────────────┘

UploadProgress schema:
{
    "progress": 45.5,          # 0.0 - 100.0
    "stage": "uploading",      # "downloading" | "uploading"
    "bytes_uploaded": 47185920,
    "total_bytes": 103809024,
    "message": "Uploading 45%"
}
```

## Error Handling Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    Error Handling in Worker                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Exception caught in _process_job()                         │
│       │                                                      │
│       ├─── QuotaExceededError ───▶ Status: "failed"         │
│       │                            No retry (quota limit)    │
│       │                                                      │
│       ├─── HttpError 403/429 ────▶ Check retry_count        │
│       │                            If < max_retries: retry   │
│       │                            Else: Status: "failed"    │
│       │                                                      │
│       ├─── DuplicateUploadError ─▶ Status: "completed"      │
│       │                            (reuse existing video_id) │
│       │                                                      │
│       └─── Other exceptions ─────▶ Status: "failed"         │
│                                    Record error message      │
│                                                              │
│  Always:                                                    │
│  - Log error with logger.exception()                        │
│  - Update job with error message                            │
│  - Clean up temp files                                      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Job Status State Machine

```
                        ┌─────────────────┐
                        │     pending     │
                        │   (initial)     │
                        └────────┬────────┘
                                 │
                    Worker picks up job
                                 │
                                 ▼
                        ┌─────────────────┐
                        │  downloading    │
                        └────────┬────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
         Error occurs    Download complete    Duplicate found
              │                  │                  │
              ▼                  ▼                  ▼
     ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
     │     failed      │ │   uploading     │ │   completed     │
     └─────────────────┘ └────────┬────────┘ │ (skip upload)   │
                                  │          └─────────────────┘
                    ┌─────────────┴─────────────┐
                    │                           │
              Error occurs              Upload complete
                    │                           │
                    ▼                           ▼
           ┌─────────────────┐         ┌─────────────────┐
           │     failed      │         │   completed     │
           └─────────────────┘         └─────────────────┘
                    │
           If retry_count < max_retries
                    │
                    ▼
           ┌─────────────────┐
           │     pending     │
           │    (retry)      │
           └─────────────────┘


           User action:
           ┌─────────────────┐
           │   cancelled     │◀──── POST /queue/jobs/{id}/cancel
           └─────────────────┘      (from any non-completed state)
```
