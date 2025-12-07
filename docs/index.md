# CloudVid Bridge Documentation Index

Welcome to CloudVid Bridge. This index page provides a short overview and links to key documentation pages.

## Overview

CloudVid Bridge is a server-side application built with FastAPI for uploading videos from Google Drive to YouTube with resumable uploads and background workers.

## Key Features

- Google OAuth authentication
- Drive scanning and resumable uploads
- Background worker queue and persistent storage
- Quota tracking and retry/backoff for YouTube API

## YouTube API Optimization & Quota Monitoring

This release includes the following improvements to reduce YouTube API quota usage and make the system more resilient:

- Optimized listing using `playlistItems.list` (lower quota cost)
- Batch video retrieval (`get_videos_batch`) supporting up to 50 videos per request
- `tenacity` based retry/backoff for uploads to handle 403/429 errors
- `QuotaTracker` for monitoring daily quota usage and remaining quota
- `youtube_etag` and `last_verified_at` added to `upload_history` for change detection and verification
- Pre-upload checks to skip re-uploads when the video is confirmed to exist on YouTube

## Important Notes

- Tenacity is added to `requirements.txt` to provide retry/backoff functionality.
- Database schema change: `upload_history` now contains `youtube_etag` and `last_verified_at`. A migration is required for production deployments.

## Links

- [Terms](terms.md)
- [Privacy](privacy.md)

If you need a migration script or help testing the new YouTube features, let me know and I can scaffold the migration and tests.
