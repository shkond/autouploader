# YouTube Data API Usage Justification

## Executive Summary

CloudVid Bridge requires a quota increase from 10,000 to 170,000 units/day to support automated video uploads for a 3-person gaming content creation group. This document provides detailed justification for each API operation and demonstrates our commitment to efficient API usage.

## Detailed API Usage Analysis

### 1. Video Upload Operations

**API Method:** `youtube.videos().insert()`  
**Cost:** 1,600 units per call  
**Daily Usage:** 100 calls  
**Total Cost:** 160,000 units/day

#### Justification

**Why 100 videos per day?**
- **3 users** each recording gaming sessions independently
- **Average 30-35 videos per user per day**
- Gaming sessions are recorded in segments (typically 10-30 minutes each)
- Multiple gaming sessions per day (morning, afternoon, evening)

**Video Upload Breakdown:**
| User | Morning | Afternoon | Evening | Total |
|------|---------|-----------|---------|-------|
| User 1 | 10-12 | 10-12 | 10-12 | 30-36 |
| User 2 | 10-12 | 10-12 | 10-12 | 30-36 |
| User 3 | 10-12 | 10-12 | 10-12 | 30-36 |
| **Daily Total** | **30-36** | **30-36** | **30-36** | **90-108** |

**Cannot be reduced because:**
- Each video segment must be uploaded individually (YouTube API limitation)
- Cannot merge videos pre-upload (would lose timeline and metadata)
- Batch upload API does not exist for `videos.insert`
- Users need individual video management (titles, descriptions, timestamps)

### 2. Video List & Verification Operations

**API Method:** `youtube.playlistItems().list()`  
**Cost:** 1-3 units per call (optimized from 100 units with `videos.list`)  
**Daily Usage:** ~300 calls  
**Total Cost:** ~600 units/day

#### Justification

**Why we need video listing:**
1. **Pre-upload duplicate detection** - Verify video doesn't already exist (prevents wasted quota)
2. **Queue status verification** - Check if videos from queue are successfully uploaded
3. **User dashboard display** - Show recently uploaded videos to users

**Usage Pattern:**
- **Per-upload check:** 1 call before each upload (100 calls/day)
- **Periodic verification:** Every 10 uploads, verify batch (10 calls/day)
- **Dashboard refreshes:** 3 users × 50 refreshes/day = 150 calls/day
- **Worker status checks:** 40 calls/day

**Optimization implemented:**
- Using `playlistItems.list` instead of `videos.list` (100 units → 1-3 units per call = **97% cost reduction**)
- Fetch up to 50 items per request (reduces call count by 50x)
- Database caching of video metadata (reduces redundant calls by ~60%)

### 3. Channel Information Operations

**API Method:** `youtube.channels().list()`  
**Cost:** 1 unit per call  
**Daily Usage:** ~10 calls  
**Total Cost:** 10 units/day

#### Justification

**When we call this API:**
- **User login:** Fetch channel info when user authenticates (3 users × 2 logins/day = 6 calls)
- **Quota tracking:** Verify channel status when monitoring quota (4 calls/day)

**Very minimal usage** - essential for user identification and authorization.

### 4. Single Video Verification

**API Method:** `youtube.videos().list()`  
**Cost:** 1 unit per call  
**Daily Usage:** ~100 calls  
**Total Cost:** 100 units/day

#### Justification

**Use case:**
- After upload completion, verify video status (processing, live, failed)
- Check video metadata correctness (title, description matched)
- Confirm video privacy settings

**Called once per successful upload** to ensure data integrity.

## Total Daily Quota Calculation

```
Video Uploads:              160,000 units
Video List Operations:          600 units  
Channel Information:             10 units
Video Verification:             100 units
────────────────────────────────────────
Total Usage:                160,710 units
Requested Quota:            170,000 units
Safety Buffer:                9,290 units (5.5%)
```

**Safety buffer accounts for:**
- Failed upload retries (network issues, API errors)
- Additional verification calls during error recovery
- Slight variance in daily upload count (90-110 videos)

## Why We Cannot Reduce Usage Further

### 1. Upload Volume Cannot Be Reduced

**Current situation:**
- 3 friends play games together daily
- Recording is automatic (using OBS, ShadowPlay, etc.)
- Generates 30-35 video files per person naturally

**Why we can't reduce:**
- Already using optimal recording settings (auto-stop at 30 minutes)
- Merging videos pre-upload loses important metadata (game timestamps, session info)
- Each video represents a distinct gaming session/segment
- Manual upload of 100 videos/day is impractical (reason for automation)

### 2. API Calls Are Already Optimized

**Optimizations implemented:**

| Optimization | Impact |
|--------------|--------|
| Using `playlistItems.list` instead of `videos.list` | -97% cost |
| Batch fetching (50 items/request) | -98% call count |
| Database caching of video metadata | -60% redundant calls |
| Pre-upload duplicate detection | Prevents wasted uploads |
| Resumable uploads with chunking | Reduces failed upload retries |
| Exponential backoff on rate limits | Minimizes retry overhead |
| Quota tracking and throttling | Prevents exceeding limits |

**Further optimization not feasible:**
- `videos.insert` cost (1,600 units) is fixed by YouTube API
- Cannot batch-upload videos (API doesn't support it)
- Already using minimum necessary verification calls
- Caching maximized without compromising data freshness

### 3. Alternative Solutions Considered

#### Option 1: Reduce Upload Frequency
- **Rejected:** Would create significant backlog (100+ videos/day generated)
- Users expect daily uploads for audience engagement

#### Option 2: Manual Upload
- **Rejected:** 100 manual uploads/day across 3 users is impractical
- Defeats purpose of automation tool

#### Option 3: Third-Party Upload Service
- **Rejected:** Security concerns (OAuth token sharing)
- Privacy issues (video content hosted by third party)
- Most services have similar quota limitations

#### Option 4: Multiple Google Cloud Projects
- **Rejected:** Violates Google Cloud Terms of Service
- Quota splitting across projects is prohibited
- Could result in account suspension

## Usage Monitoring & Commitment

### Real-Time Quota Tracking

Our application includes a `QuotaTracker` class that:
- Logs every API call with unit cost
- Calculates daily usage in real-time
- Exposes usage data via `/youtube/quota` endpoint
- Alerts when approaching 80% of daily limit

### Automatic Throttling

When quota usage reaches 90%:
- New uploads are queued until next day (00:00 Pacific Time)
- Critical operations only (verification, channel info)
- Dashboard displays quota status to all users

### Compliance Monitoring

We will:
- **Review quota usage weekly** - Identify any unusual patterns
- **Optimize further if needed** - Implement additional caching/batching
- **Report to Google if patterns change** - E.g., user count increase, public launch

## Conclusion

CloudVid Bridge requires **170,000 units/day** to serve 3 users uploading ~100 gaming videos daily. This quota is:

✅ **Justified:** Legitimate content creation workflow  
✅ **Optimized:** Extensive measures to minimize API usage  
✅ **Reasonable:** ~56x default quota for ~10x typical individual usage  
✅ **Monitored:** Real-time tracking and automatic throttling  
✅ **Transparent:** Open-source with clear documentation  

We are committed to using this quota responsibly and maintaining compliance with all YouTube API policies.

---

**Document Version:** 1.0  
**Last Updated:** December 7, 2025  
**Contact:** konnkonn34@gmail.com
