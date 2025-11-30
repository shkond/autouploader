# AutoUploader

FastAPI backend for uploading videos from Google Drive to YouTube with resumable uploads, queue management, and OAuth authentication.

## Features

- 🔐 **Google OAuth Authentication** - Secure authentication for Google Drive and YouTube APIs
- 📁 **Drive Folder Scanning** - Browse and scan Google Drive folders for video files
- 📤 **Resumable Uploads** - Reliable YouTube uploads with chunked, resumable upload support
- 📋 **Upload Queue Management** - Queue multiple videos for sequential or concurrent uploads
- ⚡ **Background Workers** - Async background processing using FastAPI BackgroundTasks
- 🔄 **Progress Tracking** - Real-time progress updates for downloads and uploads
- 🐳 **Docker Ready** - Containerized deployment with Docker and docker-compose
- 🚀 **CI/CD Pipeline** - GitHub Actions workflow for linting, testing, and building

## Technology Stack

- **Python 3.12**
- **FastAPI** - Modern async web framework
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
git clone https://github.com/shkond/autouploader.git
cd autouploader
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

5. Run the application:
```bash
uvicorn app.main:app --reload
```

6. Visit `http://localhost:8000/docs` to access the API documentation.

### Docker

Build and run with Docker:

```bash
# Development mode
docker-compose up --build

# Production mode
docker build --target production -t autouploader .
docker run -p 8000:8000 --env-file .env autouploader
```

## API Endpoints

### Authentication
- `GET /auth/login` - Get OAuth authorization URL
- `GET /auth/callback` - OAuth callback handler
- `GET /auth/status` - Check authentication status
- `POST /auth/logout` - Clear stored credentials

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
autouploader/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI application entry point
│   ├── config.py        # Application configuration
│   ├── auth/            # Google OAuth authentication
│   │   ├── oauth.py
│   │   ├── routes.py
│   │   └── schemas.py
│   ├── drive/           # Google Drive integration
│   │   ├── service.py
│   │   ├── routes.py
│   │   └── schemas.py
│   ├── youtube/         # YouTube upload functionality
│   │   ├── service.py
│   │   ├── routes.py
│   │   └── schemas.py
│   └── queue/           # Upload queue management
│       ├── manager.py
│       ├── worker.py
│       ├── routes.py
│       └── schemas.py
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
| `APP_NAME` | Application name | AutoUploader |
| `APP_ENV` | Environment (development/production) | development |
| `DEBUG` | Enable debug mode | true |
| `SECRET_KEY` | Application secret key | (required) |
| `HOST` | Server host | 0.0.0.0 |
| `PORT` | Server port | 8000 |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID | (required) |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret | (required) |
| `GOOGLE_REDIRECT_URI` | OAuth callback URL | http://localhost:8000/auth/callback |
| `MAX_CONCURRENT_UPLOADS` | Maximum concurrent uploads | 2 |
| `UPLOAD_CHUNK_SIZE` | Upload chunk size in bytes | 10485760 (10MB) |

## Scaling for Production

For production deployments with higher load, consider:

1. **Redis for Queue Management**: Replace in-memory queue with Redis for persistence and horizontal scaling
2. **Celery Workers**: Use Celery for distributed task processing
3. **Database**: Store job history in PostgreSQL
4. **Load Balancer**: Deploy multiple app instances behind a load balancer
5. **Cloud Storage**: Use cloud storage for temporary file handling

Example Redis integration is included (commented) in `docker-compose.yml`.

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