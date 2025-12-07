# YouTube Data API Quota Increase Request

## Project Information

**Application Name:** CloudVid Bridge  
**Project ID:** [Your Google Cloud Project ID]  
**Current Quota:** 10,000 units/day  
**Requested Quota:** 170,000 units/day  
**Support Email:** konnkonn34@gmail.com  
**Application Status:** Test Mode (Private, 3 users)

## Application Overview

CloudVid Bridge is an automated video upload tool that transfers gaming videos from Google Drive to YouTube. The application is designed for private use among a small group of friends (3 users) who regularly record and share their gaming sessions.

### Purpose
The primary purpose of this application is to automate the workflow of uploading gameplay recordings to YouTube, eliminating the need for manual uploads and ensuring consistent video publishing schedules.

### Use Case
- **Target Users:** 3 friends who play games together
- **Content Type:** Gaming session recordings
- **Upload Frequency:** Daily batch uploads of recorded gameplay
- **User Scope:** Private test mode (not public)

## Quota Requirements Breakdown

### Daily API Usage Calculation

Our application requires **170,000 units per day** based on the following breakdown:

| Operation | Units per Call | Calls per Day | Total Units |
|-----------|----------------|---------------|-------------|
| Video Upload (`videos.insert`) | 1,600 | 100 | 160,000 |
| List User Videos (`playlistItems.list`) | 1-3 | ~300 | 600 |
| Verify Video Existence | 1 | ~100 | 100 |
| Channel Information (`channels.list`) | 1 | ~10 | 10 |
| **Total Daily Usage** | | | **~160,710** |

**Safety Margin:** Requesting 170,000 units/day to account for retries and error handling.

### Upload Volume Justification

- **100 videos per day:** Our group records gaming sessions throughout the day, generating approximately 30-35 videos per user
- **3 active users:** Each user uploads their recorded gameplay independently
- **Batch Processing:** Videos are queued and uploaded in batches to optimize workflow

### Why Current Quota (10,000 units/day) is Insufficient

With the default quota of 10,000 units/day:
- **Maximum uploads:** 6 videos per day (10,000 ÷ 1,600 = 6.25)
- **Current requirement:** 100 videos per day
- **Shortfall:** 94 videos cannot be uploaded

This limitation prevents our group from maintaining a consistent upload schedule and causes significant backlog.

## Technical Implementation

### API Optimization Measures

Our application implements several optimization strategies to minimize API usage:

1. **Batch Operations**
   - Use `playlistItems.list` instead of `videos.list` where possible (cost reduction: 100 units → 1-3 units)
   - Batch fetch up to 50 videos per request using `get_videos_batch`

2. **Caching & Verification**
   - Pre-upload verification checks to prevent duplicate uploads
   - Local database (`upload_history` table) tracks uploaded videos
   - `last_verified_at` timestamp reduces redundant API calls

3. **Retry Logic with Exponential Backoff**
   - Implemented using `tenacity` library
   - Handles rate limits (HTTP 429) gracefully
   - Reduces failed uploads that would require re-attempts

4. **Quota Tracking**
   - Real-time quota monitoring via `QuotaTracker` class
   - Exposed through `/youtube/quota` endpoint
   - Alerts when approaching daily limit

5. **Efficient Queue Management**
   - Database-backed persistent queue (SQLAlchemy + PostgreSQL)
   - Configurable concurrent uploads (`MAX_CONCURRENT_UPLOADS=2`)
   - Worker process prevents redundant API polling

### Architecture Highlights

- **Backend:** FastAPI (Python 3.12)
- **Database:** PostgreSQL (production) / SQLite (development)
- **Authentication:** OAuth 2.0 with encrypted token storage
- **Upload Method:** Resumable uploads with chunking (10MB chunks)
- **Queue System:** Persistent job queue with worker processes

### Security & Privacy

- OAuth tokens encrypted using Fernet symmetric encryption
- User-specific data isolation (multi-user support)
- Session-based authentication for app access
- Test mode limits access to explicitly authorized users only

## Compliance & User Privacy

### Data Handling

- **Minimal Data Collection:** Only stores OAuth tokens (encrypted) and upload metadata
- **No Personal Data Storage:** Does not store video content locally (direct Drive-to-YouTube transfer)
- **User Consent:** All users explicitly authorize Google Drive and YouTube access via OAuth

### Privacy Policy & Terms of Service

- **Privacy Policy:** https://shkond.github.io/autouploader/privacy
- **Terms of Service:** https://shkond.github.io/autouploader/terms

### Test Mode Operation

This application operates in **Test Mode** with the following restrictions:
- Maximum 100 test users (currently 3 users)
- Users must be explicitly added to the allowlist in Google Cloud Console
- No public access or distribution
- No OAuth verification required for test mode

## Expected Usage Pattern

### Typical Daily Workflow

1. **Morning Batch (30-40 videos):** Previous night's gaming sessions
2. **Afternoon Batch (30-40 videos):** Morning gaming sessions  
3. **Evening Batch (30-40 videos):** Afternoon gaming sessions

### Peak Usage Times

- **06:00-08:00 JST:** Morning uploads (~40,000 units)
- **12:00-14:00 JST:** Afternoon uploads (~40,000 units)
- **20:00-22:00 JST:** Evening uploads (~80,000 units)

### Growth Expectations

- **User Count:** Will remain at 3 users (no expansion planned)
- **Upload Volume:** Expected to remain consistent at 100 videos/day
- **Future Needs:** No additional quota increase anticipated

## Why This Quota is Reasonable

1. **Legitimate Use Case:** Automated content management for small creator group
2. **Optimized Implementation:** Extensive measures to minimize API calls
3. **Transparent Operations:** Clear quota tracking and monitoring
4. **Limited Scope:** Private test mode with only 3 users
5. **Consistent Usage:** Predictable daily patterns, no sudden spikes

## Additional Information

### Repository
- **GitHub:** https://github.com/shkond/autouploader (assumed, please update)
- **Documentation:** Comprehensive README with architecture details
- **Code Quality:** CI/CD pipeline with automated testing and linting

### Contact Information
- **Developer Email:** konnkonn34@gmail.com
- **Response Time:** Available for follow-up questions within 24 hours

### Monitoring & Compliance

We commit to:
- Monitor quota usage daily via built-in `QuotaTracker`
- Implement additional optimizations if usage exceeds projections
- Notify Google immediately if application scope changes (e.g., public launch)
- Maintain compliance with YouTube Terms of Service and API policies

---

**Declaration:**  
We certify that this application will be used solely for the purposes described above, with the specified user count (3 users), and will not be distributed publicly without completing OAuth verification. We understand that misuse of increased quota may result in revocation and account suspension.

**Date:** December 7, 2025  
**Requested by:** konnkonn34@gmail.com
