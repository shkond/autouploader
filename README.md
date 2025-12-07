# CloudVid Bridge

FastAPI backend for uploading videos from Google Drive to YouTube with resumable uploads, queue management, and OAuth authentication.

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [Docker](#docker)
- [Heroku Deployment](#heroku-deployment)
- [Worker Process](#worker-process)
- [YouTube API Optimization & Quota Monitoring](#youtube-api-optimization--quota-monitoring)
- [API Endpoints](#api-endpoints)
- [Project Structure](#project-structure)
- [Environment Variables](#environment-variables)
- [Development](#development)
- [License](#license)

## Features

- 🔐 **Google OAuth Authentication** - Secure authentication for Google Drive and YouTube APIs
- 🔑 **Simple App Authentication** - Session-based login for app access control
- 🗄️ **Database-Backed Queue** - Persistent job queue using SQLAlchemy (SQLite/PostgreSQL)
- 🔒 **Token Encryption** - OAuth tokens encrypted with Fernet symmetric encryption
- 👥 **Multi-User Support** - User-specific job queues and token management
- 🌐 **Web UI** - Modern dark theme dashboard for video management
- 📁 **Folder Upload UI** - Browse Drive folders, configure batch upload settings, preview videos, and manage upload queue
- 📁 **Drive Folder Scanning** - Browse and scan Google Drive folders for video files
- 📤 **Resumable Uploads** - Reliable YouTube uploads with chunked, resumable upload support
- 📋 **Upload Queue Management** - Queue multiple videos for sequential or concurrent uploads
- ⚡ **Background Workers** - Standalone worker process for distributed job processing
- 🔄 **Progress Tracking** - Real-time progress updates for downloads and uploads
- 🐳 **Docker Ready** - Containerized deployment with Docker and docker-compose
- ☁️ **Heroku Ready** - One-click deployment to Heroku with PostgreSQL support
- 🚀 **CI/CD Pipeline** - GitHub Actions workflow for linting, testing, and building

## Technology Stack

- **Python 3.12**
- **FastAPI** - Modern async web framework
- **SQLAlchemy** - Database ORM with async support
- **PostgreSQL/SQLite** - Database backends (PostgreSQL for production, SQLite for development)
- **Cryptography** - Fernet symmetric encryption for OAuth tokens
- **Jinja2** - Template engine for web UI
- **google-api-python-client** - Google APIs client library
- **Pydantic** - Data validation using Python type annotations
- **Docker** - Containerization
- **GitHub Actions** - CI/CD automation

## Quick Start

### Prerequisites

- Python 3.12+
- Google Cloud Project with Drive and YouTube APIs enabled
- OAuth 2.0 credentials (Web application type)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/shkond/cloudvid-bridge.git
cd cloudvid-bridge
```

2. Create a virtual environment and install dependencies:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and configure:
```bash
cp .env.example .env
```

4. Set up Google OAuth credentials:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a project and enable Google Drive API and YouTube Data API v3
   - Create OAuth 2.0 credentials (Web application)
   - Add `http://localhost:8000/auth/callback` as an authorized redirect URI
   - Copy the Client ID and Client Secret to your `.env` file

5. Set app authentication credentials in `.env`:
```
AUTH_USERNAME=your-username
AUTH_PASSWORD=your-secure-password
```

6. Run database migrations (creates tables automatically on first run):
```bash
python -c "import asyncio; from app.database import init_db; asyncio.run(init_db())"
```

7. Run the application:
```bash
uvicorn app.main:app --reload
```

8. Visit `http://localhost:8000/auth/login` to access the login page.

### Docker

Build and run with Docker:

```bash
# Development mode
docker-compose up --build

# Production mode
docker build --target production -t cloudvid-bridge .
docker run -p 8000:8000 --env-file .env cloudvid-bridge
```

### Heroku Deployment

Deploy to Heroku with these steps:

1. Create a Heroku app:
```bash
heroku create your-app-name
```

2. Set environment variables:
```bash
heroku config:set GOOGLE_CLIENT_ID=your-client-id
heroku config:set GOOGLE_CLIENT_SECRET=your-client-secret
heroku config:set GOOGLE_REDIRECT_URI=https://your-app-name.herokuapp.com/auth/callback
heroku config:set SECRET_KEY=your-random-secret-key
heroku config:set AUTH_USERNAME=your-username
heroku config:set AUTH_PASSWORD=your-secure-password
heroku config:set APP_ENV=production
```

3. Deploy:
```bash
git push heroku main
```

4. Update Google Cloud Console:
   - Add `https://your-app-name.herokuapp.com/auth/callback` as an authorized redirect URI

5. Add PostgreSQL addon (recommended for production):
```bash
heroku addons:create heroku-postgresql:mini
```

### Worker Process

The application uses a separate worker process for background job processing:

**Local Development:**
```bash
# Terminal 1: Run web server
uvicorn app.main:app --reload

# Terminal 2: Run worker
python -m app.queue.worker
```

**Heroku Deployment:**
The `Procfile` defines both `web` and `worker` processes. Scale the worker:
```bash
heroku ps:scale worker=1
```

**Docker Deployment:**
Use `docker-compose.yml` which runs both web and worker services.

## Web UI

The application includes a modern web interface:

- **Login Page** (`/auth/login`) - App authentication with username/password
- **Dashboard** (`/auth/dashboard`) - Main control panel after login
  - Google account connection
  - Drive folder selection
  - Upload queue management
  - Progress monitoring

## API Endpoints

### Authentication
- `GET /auth/login` - Login page (Web UI)
- `POST /auth/login` - Process login form
- `GET /auth/dashboard` - Dashboard page (Web UI)
- `GET /auth/google` - Redirect to Google OAuth
- `GET /auth/callback` - Google OAuth callback handler
- `GET /auth/status` - Check authentication status (API)
- `GET /auth/logout` - Logout and clear credentials

### Google Drive
- `GET /drive/files` - List files in a folder
- `POST /drive/scan` - Scan folder for video files (with recursive option)
- `GET /drive/file/{file_id}` - Get file information

### YouTube
- `GET /youtube/channel` - Get authenticated user's channel info
- `GET /youtube/videos` - List uploaded videos
- `POST /youtube/upload` - Upload video directly from Drive

### Upload Queue
- `GET /queue/status` - Get queue status
- `GET /queue/jobs` - List all jobs
- `POST /queue/jobs` - Add job to queue
- `POST /queue/jobs/bulk` - Add multiple jobs
- `GET /queue/jobs/{job_id}` - Get job details
- `POST /queue/jobs/{job_id}/cancel` - Cancel a job
- `DELETE /queue/jobs/{job_id}` - Delete a job
- `POST /queue/clear` - Clear completed jobs
- `POST /queue/worker/start` - Start the worker
- `POST /queue/worker/stop` - Stop the worker

## Project Structure

```
cloudvid-bridge/
├── Procfile             # Heroku deployment config
├── runtime.txt          # Python version for Heroku
├── app/
│   ├── main.py          # FastAPI application entry point
│   ├── config.py        # Application configuration
│   ├── static/          # Static files (CSS, JS)
│   │   └── css/
│   ├── templates/       # Jinja2 templates
│   │   ├── base.html
│   │   ├── login.html
│   │   └── dashboard.html
│   ├── auth/            # Authentication (OAuth + Simple)
│   │   ├── oauth.py
│   │   ├── simple_auth.py
│   │   ├── dependencies.py
│   │   ├── routes.py
│   │   └── schemas.py
│   ├── drive/           # Google Drive integration
│   ├── youtube/         # YouTube upload functionality
│   └── queue/           # Upload queue management
├── tests/               # Test files
├── .github/workflows/   # CI/CD configuration
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
└── .env.example
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `APP_NAME` | Application name | CloudVid Bridge |
| `APP_ENV` | Environment (development/production) | development |
| `DEBUG` | Enable debug mode | true |
| `SECRET_KEY` | Application secret key | (required) |
| `HOST` | Server host | 0.0.0.0 |
| `PORT` | Server port | 8000 |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID | (required) |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret | (required) |
| `GOOGLE_REDIRECT_URI` | OAuth callback URL | http://localhost:8000/auth/callback |
| `AUTH_USERNAME` | App login username | (required for production) |
| `AUTH_PASSWORD` | App login password | (required for production) |
| `DATABASE_URL` | Database connection URL | sqlite+aiosqlite:///./cloudvid_bridge.db |
| `MAX_CONCURRENT_UPLOADS` | Maximum concurrent uploads | 2 |
| `UPLOAD_CHUNK_SIZE` | Upload chunk size in bytes | 10485760 (10MB) |

## Architecture

### Database Persistence

The application uses SQLAlchemy with async support for database operations:

- **Development**: SQLite with aiosqlite driver
- **Production**: PostgreSQL (recommended for Heroku/cloud deployments)

Three main tables:
1. `queue_jobs` - Persistent upload queue with user ownership
2. `oauth_tokens` - Encrypted OAuth credentials per user
3. `upload_history` - Record of completed uploads for duplicate detection

### Queue Management

The upload queue is database-backed for persistence across restarts:

- Jobs survive server restarts and crashes
- Multi-user support with user-specific job filtering
- Worker process polls database for pending jobs
- Supports concurrent uploads (configurable via `MAX_CONCURRENT_UPLOADS`)

### Security

- OAuth tokens encrypted using Fernet symmetric encryption
- Encryption key derived from `SECRET_KEY` environment variable
- Session-based authentication for app access
- User-specific data isolation

## Scaling for Production

The current architecture supports production deployments:

1. **Database**: PostgreSQL recommended for production (already implemented)
2. **Worker Scaling**: Run multiple worker processes for higher throughput
3. **Load Balancer**: Deploy multiple web instances behind a load balancer
4. **Monitoring**: Add application monitoring and logging (e.g., Sentry, Datadog)
5. **Caching**: Add Redis for session storage and caching (optional)

For higher scale:
- Consider message queue systems (RabbitMQ, Redis) for job distribution
- Implement worker heartbeat mechanism for better status tracking
- Add database connection pooling for high concurrency

## Development

### Running Tests

```bash
# Install dev dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ -v --cov=app --cov-report=term-missing
```

### Linting

```bash
# Install ruff
pip install ruff

# Check code
ruff check app/

# Format code
ruff format app/
```

## License

MIT License

## YouTube API Optimization & Quota Monitoring

This project includes newly implemented YouTube API quota optimizations and error handling features:

- **Quota Optimizations**: Use `playlistItems.list` where appropriate (reduced cost from 100 units to 1-2 units), and `get_videos_batch` to fetch up to 50 videos per request to reduce the number of requests.
- **Retry & Backoff**: Implemented retry/backoff for uploads using `tenacity` to handle rate limits and transient API errors.
- **Quota Tracking**: A `QuotaTracker` is available to monitor daily usage and estimated remaining quota via the `/youtube/quota` endpoint.
- **Pre-upload Verification**: Worker pre-upload checks verify existence of videos on YouTube and updates `last_verified_at` to reduce duplicate uploads.

