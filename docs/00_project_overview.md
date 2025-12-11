# Project Overview

## Summary

CloudVid Bridge is a FastAPI-based web application that enables uploading videos from Google Drive to YouTube with queue management, OAuth authentication, and resumable uploads.

## Key Features

- **Google OAuth Authentication**: Secure OAuth 2.0 flow for Google Drive and YouTube APIs
- **Database-Backed Queue**: Persistent job queue using SQLAlchemy (SQLite/PostgreSQL)
- **Multi-User Support**: User-specific job queues and token management
- **Background Workers**: Standalone worker process for distributed job processing
- **Resumable Uploads**: Chunked, resumable upload support for large video files

## Technology Stack

| Category | Technology |
|----------|------------|
| Language | Python 3.12 |
| Web Framework | FastAPI (async) |
| Database ORM | SQLAlchemy (async support) |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Authentication | Google OAuth 2.0 |
| Token Encryption | Fernet (cryptography) |
| APIs | Google Drive API, YouTube Data API v3 |
| Template Engine | Jinja2 |

## Project Structure

```
cloudvid-bridge/
├── app/
│   ├── main.py              # FastAPI application entry point
│   ├── config.py            # Application settings (Pydantic)
│   ├── database.py          # SQLAlchemy async setup
│   ├── models.py            # Database models (ORM)
│   ├── crypto.py            # Token encryption utilities
│   ├── exceptions.py        # Custom exception classes
│   ├── core/                # Core infrastructure
│   │   ├── dependencies.py  # FastAPI dependency injection
│   │   └── protocols.py     # Repository interface protocols
│   ├── auth/                # Authentication module
│   │   ├── oauth.py         # Google OAuth service
│   │   ├── simple_auth.py   # Session-based app auth
│   │   ├── routes.py        # Auth API routes
│   │   ├── dependencies.py  # Auth-specific dependencies
│   │   └── schemas.py       # Pydantic schemas
│   ├── drive/               # Google Drive module
│   │   ├── service.py       # DriveService (high-level)
│   │   ├── repositories.py  # DriveRepository (API calls)
│   │   ├── routes.py        # Drive API routes
│   │   ├── services.py      # Additional drive services
│   │   └── schemas.py       # Pydantic schemas
│   ├── youtube/             # YouTube module
│   │   ├── service.py       # YouTubeService (uploads)
│   │   ├── repositories.py  # YouTubeRepository
│   │   ├── routes.py        # YouTube API routes
│   │   ├── quota.py         # QuotaTracker for API usage
│   │   └── schemas.py       # Pydantic schemas
│   ├── queue/               # Upload queue module
│   │   ├── worker.py        # Background job worker
│   │   ├── manager_db.py    # Queue management (DB-backed)
│   │   ├── repositories.py  # QueueRepository
│   │   ├── services.py      # QueueService
│   │   ├── routes.py        # Queue API routes
│   │   └── schemas.py       # Pydantic schemas
│   ├── tasks/               # Scheduled tasks module
│   │   ├── services.py      # FolderUploadService
│   │   └── scheduled_upload.py  # CLI for Heroku Scheduler
│   ├── static/              # Static files (CSS, JS)
│   └── templates/           # Jinja2 templates
├── tests/                   # Test files
├── docs/                    # Documentation
├── Dockerfile               # Docker configuration
├── docker-compose.yml       # Docker Compose setup
├── Procfile                 # Heroku deployment config
├── pyproject.toml           # Python project config
└── requirements.txt         # Python dependencies
```

## Key Entry Points

| Purpose | Entry Point |
|---------|-------------|
| Web Application | `uvicorn app.main:app` |
| Background Worker | `python -m app.queue.worker` |
| Scheduled Upload | `python -m app.tasks.scheduled_upload` |
| Database Init | `python -c "from app.database import init_db; ..."` |

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `GOOGLE_CLIENT_ID` | Google OAuth client ID | ✓ |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret | ✓ |
| `GOOGLE_REDIRECT_URI` | OAuth callback URL | ✓ |
| `SECRET_KEY` | App secret for encryption | ✓ |
| `AUTH_USERNAME` | App login username | ✓ (prod) |
| `AUTH_PASSWORD` | App login password | ✓ (prod) |
| `DATABASE_URL` | Database connection URL | ✓ |
| `MAX_CONCURRENT_UPLOADS` | Concurrent upload limit | Default: 2 |
| `UPLOAD_CHUNK_SIZE` | Upload chunk size (bytes) | Default: 10MB |
| `TARGET_USER_ID` | User ID for scheduled tasks | Default: admin |
| `TARGET_FOLDER_ID` | Drive folder ID for scheduled scan | Default: root |
| `MAX_FILES_PER_RUN` | Max files per scheduled run | Default: 50 |
