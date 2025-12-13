/**
 * CloudVid Bridge Dashboard JavaScript
 * Handles folder browsing, upload settings, and queue management
 */

// State
let currentFolderId = 'root';
let currentFolderName = 'My Drive';
let scannedVideos = [];
let selectedFolderId = null;
let selectedFolderName = null;

// DOM Elements
const elements = {
    folderPath: document.getElementById('folder-path'),
    folderId: document.getElementById('folder-id'),
    browseBtn: document.getElementById('browse-folders'),
    uploadSettings: document.getElementById('upload-settings'),
    videoPreview: document.getElementById('video-preview'),
    videoList: document.getElementById('video-list'),
    videoCount: document.getElementById('video-count'),
    scanBtn: document.getElementById('scan-folder'),
    addToQueueBtn: document.getElementById('add-to-queue'),
    queueList: document.getElementById('queue-list'),
    queueCount: document.getElementById('queue-count'),
    progressInfo: document.getElementById('progress-info'),
    // Modal
    modal: document.getElementById('folder-modal'),
    closeModal: document.getElementById('close-modal'),
    folderList: document.getElementById('folder-list'),
    breadcrumb: document.getElementById('folder-breadcrumb'),
    selectFolderBtn: document.getElementById('select-folder'),
    cancelSelectBtn: document.getElementById('cancel-select'),
    // Settings
    titleTemplate: document.getElementById('title-template'),
    descriptionTemplate: document.getElementById('description-template'),
    privacyStatus: document.getElementById('privacy-status'),
    recursiveCheck: document.getElementById('recursive'),
    skipDuplicatesCheck: document.getElementById('skip-duplicates'),
    includeMd5Check: document.getElementById('include-md5'),
    // Toast
    toastContainer: document.getElementById('toast-container'),
    // Quota
    quotaStatus: document.getElementById('quota-status'),
    // Updates
    selectCurrentFolderBtn: document.getElementById('select-current-folder'),
    // Schedule Settings
    scheduleFolderUrl: document.getElementById('schedule-folder-url'),
    scheduleMaxFiles: document.getElementById('schedule-max-files'),
    scheduleTitleTemplate: document.getElementById('schedule-title-template'),
    scheduleDescriptionTemplate: document.getElementById('schedule-description-template'),
    schedulePrivacy: document.getElementById('schedule-privacy'),
    scheduleRecursive: document.getElementById('schedule-recursive'),
    scheduleSkipDuplicates: document.getElementById('schedule-skip-duplicates'),
    scheduleIncludeMd5: document.getElementById('schedule-include-md5'),
    scheduleEnabled: document.getElementById('schedule-enabled'),
    scheduleStatus: document.getElementById('schedule-status'),
    saveScheduleBtn: document.getElementById('save-schedule'),
    deleteScheduleBtn: document.getElementById('delete-schedule'),
    validateFolderBtn: document.getElementById('validate-folder'),
    folderValidationStatus: document.getElementById('folder-validation-status'),
};

// API Functions
async function fetchFiles(folderId = 'root') {
    try {
        const response = await fetch(`/drive/files?folder_id=${folderId}&video_only=true`);
        if (!response.ok) throw new Error('Failed to fetch files');
        return await response.json();
    } catch (error) {
        showToast('ファイル取得に失敗しました', 'error');
        return [];
    }
}

async function scanFolder(folderId, recursive = false) {
    try {
        const response = await fetch('/drive/scan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                folder_id: folderId,
                recursive: recursive,
                video_only: true,
            }),
        });
        if (!response.ok) throw new Error('Failed to scan folder');
        return await response.json();
    } catch (error) {
        showToast('フォルダスキャンに失敗しました', 'error');
        return null;
    }
}

async function uploadFolder(folderId, settings) {
    try {
        const response = await fetch('/drive/folder/upload', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                folder_id: folderId,
                recursive: settings.recursive,
                max_files: 100,
                skip_duplicates: settings.skipDuplicates,
                settings: {
                    title_template: settings.titleTemplate,
                    description_template: settings.descriptionTemplate,
                    include_md5_hash: settings.includeMd5,
                    default_privacy: settings.privacy,
                },
            }),
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Upload failed');
        }
        return await response.json();
    } catch (error) {
        showToast(`アップロード失敗: ${error.message}`, 'error');
        return null;
    }
}

async function getQueueStatus() {
    try {
        const response = await fetch('/queue/jobs');
        if (!response.ok) throw new Error('Failed to get queue');
        return await response.json();
    } catch (error) {
        return { jobs: [], status: { total_jobs: 0 } };
    }
}

// Schedule Settings API Functions
async function loadScheduleSettings() {
    try {
        const response = await fetch('/settings/schedule');
        if (!response.ok) return null;
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Failed to load schedule settings:', error);
        return null;
    }
}

async function saveScheduleSettings() {
    const folderUrl = elements.scheduleFolderUrl?.value?.trim();
    if (!folderUrl) {
        showToast('フォルダURLを入力してください', 'error');
        return false;
    }

    const settings = {
        folder_url: folderUrl,
        max_files_per_run: parseInt(elements.scheduleMaxFiles?.value || '50', 10),
        title_template: elements.scheduleTitleTemplate?.value || '{filename}',
        description_template: elements.scheduleDescriptionTemplate?.value || 'Uploaded from {folder_path}',
        default_privacy: elements.schedulePrivacy?.value || 'private',
        recursive: elements.scheduleRecursive?.checked ?? true,
        skip_duplicates: elements.scheduleSkipDuplicates?.checked ?? true,
        include_md5_hash: elements.scheduleIncludeMd5?.checked ?? true,
        is_enabled: elements.scheduleEnabled?.checked ?? false,
    };

    try {
        const response = await fetch('/settings/schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings),
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to save settings');
        }
        showToast('スケジュール設定を保存しました', 'success');
        if (elements.deleteScheduleBtn) elements.deleteScheduleBtn.style.display = 'inline-block';
        return true;
    } catch (error) {
        showToast(`保存失敗: ${error.message}`, 'error');
        return false;
    }
}

async function deleteScheduleSettings() {
    if (!confirm('スケジュール設定を削除してもよろしいですか？')) return false;

    try {
        const response = await fetch('/settings/schedule', { method: 'DELETE' });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to delete settings');
        }
        showToast('スケジュール設定を削除しました', 'success');
        // Reset form
        if (elements.scheduleFolderUrl) elements.scheduleFolderUrl.value = '';
        if (elements.scheduleEnabled) elements.scheduleEnabled.checked = false;
        updateScheduleStatusDisplay(false);
        if (elements.deleteScheduleBtn) elements.deleteScheduleBtn.style.display = 'none';
        return true;
    } catch (error) {
        showToast(`削除失敗: ${error.message}`, 'error');
        return false;
    }
}

async function validateFolderUrl() {
    const folderUrl = elements.scheduleFolderUrl?.value?.trim();
    if (!folderUrl) {
        showToast('フォルダURLを入力してください', 'error');
        return;
    }

    if (elements.folderValidationStatus) {
        elements.folderValidationStatus.textContent = '検証中...';
        elements.folderValidationStatus.className = 'validation-status validating';
    }

    try {
        const response = await fetch('/settings/schedule/validate-folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folder_url: folderUrl }),
        });
        const result = await response.json();

        if (result.valid) {
            if (elements.folderValidationStatus) {
                elements.folderValidationStatus.textContent = `✓ ${result.folder_name}`;
                elements.folderValidationStatus.className = 'validation-status valid';
            }
            showToast(`フォルダ「${result.folder_name}」にアクセスできます`, 'success');
        } else {
            if (elements.folderValidationStatus) {
                elements.folderValidationStatus.textContent = `✗ ${result.error}`;
                elements.folderValidationStatus.className = 'validation-status invalid';
            }
            showToast(result.error || '無効なフォルダURL', 'error');
        }
    } catch (error) {
        if (elements.folderValidationStatus) {
            elements.folderValidationStatus.textContent = '✗ 検証エラー';
            elements.folderValidationStatus.className = 'validation-status invalid';
        }
        showToast('フォルダ検証に失敗しました', 'error');
    }
}

function updateScheduleStatusDisplay(enabled) {
    if (elements.scheduleStatus) {
        elements.scheduleStatus.textContent = enabled ? '有効' : '無効';
        elements.scheduleStatus.className = enabled ? 'schedule-status enabled' : 'schedule-status disabled';
    }
}

function populateScheduleForm(settings) {
    if (!settings) return;

    if (elements.scheduleFolderUrl) elements.scheduleFolderUrl.value = settings.folder_url || '';
    if (elements.scheduleMaxFiles) elements.scheduleMaxFiles.value = settings.max_files_per_run || 50;
    if (elements.scheduleTitleTemplate) elements.scheduleTitleTemplate.value = settings.title_template || '{filename}';
    if (elements.scheduleDescriptionTemplate) elements.scheduleDescriptionTemplate.value = settings.description_template || '';
    if (elements.schedulePrivacy) elements.schedulePrivacy.value = settings.default_privacy || 'private';
    if (elements.scheduleRecursive) elements.scheduleRecursive.checked = settings.recursive ?? true;
    if (elements.scheduleSkipDuplicates) elements.scheduleSkipDuplicates.checked = settings.skip_duplicates ?? true;
    if (elements.scheduleIncludeMd5) elements.scheduleIncludeMd5.checked = settings.include_md5_hash ?? true;
    if (elements.scheduleEnabled) elements.scheduleEnabled.checked = settings.is_enabled ?? false;
    updateScheduleStatusDisplay(settings.is_enabled);
    if (elements.deleteScheduleBtn) elements.deleteScheduleBtn.style.display = 'inline-block';
}

async function cancelJob(jobId) {
    if (!confirm('このジョブをキャンセルしてもよろしいですか？')) return;

    try {
        const response = await fetch(`/queue/jobs/${jobId}/cancel`, { method: 'POST' });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to cancel job');
        }
        showToast('ジョブをキャンセルしました', 'success');
        refreshQueueList();
    } catch (error) {
        showToast(`キャンセル失敗: ${error.message}`, 'error');
    }
}

async function deleteJob(jobId) {
    if (!confirm('このジョブを削除してもよろしいですか？\n\n注意: アップロード履歴からも完全に削除されます。')) return;

    try {
        const response = await fetch(`/queue/jobs/${jobId}`, { method: 'DELETE' });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to delete job');
        }
        showToast('ジョブを削除しました', 'success');
        refreshQueueList();
    } catch (error) {
        showToast(`削除失敗: ${error.message}`, 'error');
    }
}

async function updateQuotaStatus() {
    if (!elements.quotaStatus) return;

    try {
        const response = await fetch('/youtube/quota');
        if (!response.ok) return;

        const data = await response.json();
        const percent = data.usage_percentage;
        const remaining = data.remaining;

        elements.quotaStatus.style.display = 'flex';
        const quotaText = elements.quotaStatus.querySelector('.quota-text');

        if (percent >= 100) {
            quotaText.textContent = '100% (上限到達)';
            elements.quotaStatus.classList.add('error');
        } else {
            quotaText.textContent = `${percent}% (残: ${remaining})`;
            elements.quotaStatus.classList.remove('error');
            if (percent > 80) {
                elements.quotaStatus.classList.add('warning');
            } else {
                elements.quotaStatus.classList.remove('warning');
            }
        }
    } catch (error) {
        console.error('Failed to update quota:', error);
    }
}

// UI Functions
function showToast(message, type = 'info') {
    if (!elements.toastContainer) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    elements.toastContainer.appendChild(toast);

    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function openModal() {
    if (elements.modal) {
        elements.modal.style.display = 'flex';
        loadFolderContents('root');
    }
}

function closeModalFn() {
    if (elements.modal) {
        elements.modal.style.display = 'none';
    }
}

async function loadFolderContents(folderId) {
    if (!elements.folderList) return;

    elements.folderList.innerHTML = '<p class="loading">読み込み中...</p>';
    selectedFolderId = null;
    if (elements.selectFolderBtn) elements.selectFolderBtn.disabled = true;

    const files = await fetchFiles(folderId);
    currentFolderId = folderId;

    if (files.length === 0) {
        elements.folderList.innerHTML = '<p class="empty-state">フォルダが空です</p>';
        return;
    }

    elements.folderList.innerHTML = '';

    files.forEach(file => {
        const item = document.createElement('div');
        item.className = `folder-item ${file.file_type}`;
        item.dataset.id = file.id;
        item.dataset.name = file.name;
        item.dataset.type = file.file_type;

        const icon = file.file_type === 'folder'
            ? '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" stroke="currentColor" stroke-width="2"/></svg>'
            : '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M23 7l-7 5 7 5V7z" stroke="currentColor" stroke-width="2"/><rect x="1" y="5" width="15" height="14" rx="2" stroke="currentColor" stroke-width="2"/></svg>';

        item.innerHTML = `${icon}<span>${file.name}</span>`;

        item.addEventListener('click', () => {
            if (file.file_type === 'folder') {
                // Double-click to enter folder
                item.addEventListener('dblclick', () => {
                    navigateToFolder(file.id, file.name);
                });
            }
            // Select this item
            document.querySelectorAll('.folder-item.selected').forEach(el => el.classList.remove('selected'));
            item.classList.add('selected');
            selectedFolderId = file.id;
            selectedFolderName = file.name;
            if (elements.selectFolderBtn) elements.selectFolderBtn.disabled = false;
        });

        elements.folderList.appendChild(item);
    });
}

function navigateToFolder(folderId, folderName) {
    // Update breadcrumb
    if (elements.breadcrumb) {
        const item = document.createElement('span');
        item.className = 'breadcrumb-item';
        item.dataset.id = folderId;
        item.textContent = ` / ${folderName}`;
        item.addEventListener('click', () => {
            // Remove all items after this one
            while (item.nextSibling) {
                item.nextSibling.remove();
            }
            loadFolderContents(folderId);
        });
        elements.breadcrumb.appendChild(item);
    }
    loadFolderContents(folderId);
}

function selectCurrentFolder() {
    if (!currentFolderId) return;

    // Set variables as if selected from list
    selectedFolderId = currentFolderId;
    selectedFolderName = currentFolderName; // This might be "My Drive" or last folder name

    selectFolder();
}

function selectFolder() {
    if (!selectedFolderId) return;

    if (elements.folderPath) elements.folderPath.value = selectedFolderName || 'Selected Folder';
    if (elements.folderId) elements.folderId.value = selectedFolderId;

    currentFolderId = selectedFolderId;
    currentFolderName = selectedFolderName;

    // Show upload settings and preview
    if (elements.uploadSettings) elements.uploadSettings.style.display = 'block';
    if (elements.videoPreview) elements.videoPreview.style.display = 'block';

    closeModalFn();
    showToast(`フォルダ "${selectedFolderName}" を選択しました`, 'success');
}

async function performScan() {
    if (!currentFolderId || currentFolderId === 'root') {
        showToast('フォルダを選択してください', 'warning');
        return;
    }

    const recursive = elements.recursiveCheck?.checked ?? true;

    if (elements.videoList) elements.videoList.innerHTML = '<p class="loading">スキャン中...</p>';
    if (elements.scanBtn) elements.scanBtn.disabled = true;

    const result = await scanFolder(currentFolderId, recursive);

    if (elements.scanBtn) elements.scanBtn.disabled = false;

    if (!result) {
        if (elements.videoList) elements.videoList.innerHTML = '<p class="empty-state">スキャンに失敗しました</p>';
        return;
    }

    scannedVideos = flattenVideos(result.folder);

    if (elements.videoCount) elements.videoCount.textContent = scannedVideos.length;

    if (scannedVideos.length === 0) {
        if (elements.videoList) elements.videoList.innerHTML = '<p class="empty-state">動画が見つかりませんでした</p>';
        if (elements.addToQueueBtn) elements.addToQueueBtn.disabled = true;
        return;
    }

    renderVideoList(scannedVideos);
    if (elements.addToQueueBtn) elements.addToQueueBtn.disabled = false;
}

function flattenVideos(folder, path = '') {
    let videos = [];
    const currentPath = path ? `${path}/${folder.name}` : folder.name;

    folder.files.forEach(file => {
        videos.push({ ...file, path: currentPath });
    });

    folder.subfolders.forEach(subfolder => {
        videos = videos.concat(flattenVideos(subfolder, currentPath));
    });

    return videos;
}

// File size limits (in bytes) - should match backend config
const MAX_FILE_SIZE = 5 * 1024 * 1024 * 1024; // 5GB
const WARNING_FILE_SIZE = 4 * 1024 * 1024 * 1024; // 4GB

function renderVideoList(videos) {
    if (!elements.videoList) return;

    elements.videoList.innerHTML = '';

    let hasOversizedFiles = false;

    videos.forEach(video => {
        const item = document.createElement('div');
        item.className = 'video-item';

        const sizeStr = video.size ? formatBytes(video.size) : 'N/A';

        // Determine file size status
        let sizeClass = '';
        let sizeIcon = '';
        let sizeTooltip = '';

        if (video.size && video.size > MAX_FILE_SIZE) {
            sizeClass = 'size-error';
            sizeIcon = '⚠️';
            sizeTooltip = ' (ファイルサイズ超過: 5GB以下にしてください)';
            hasOversizedFiles = true;
        } else if (video.size && video.size > WARNING_FILE_SIZE) {
            sizeClass = 'size-warning';
            sizeIcon = '⚡';
            sizeTooltip = ' (大きなファイル)';
        }

        item.innerHTML = `
            <div class="video-info">
                <span class="video-name">${video.name}</span>
                <span class="video-path">${video.path}</span>
            </div>
            <span class="video-size ${sizeClass}" title="${sizeStr}${sizeTooltip}">${sizeIcon} ${sizeStr}</span>
        `;

        elements.videoList.appendChild(item);
    });

    // Disable add to queue button if there are oversized files
    if (elements.addToQueueBtn) {
        if (hasOversizedFiles) {
            elements.addToQueueBtn.disabled = true;
            elements.addToQueueBtn.title = '5GBを超えるファイルがあります';
        } else {
            elements.addToQueueBtn.disabled = false;
            elements.addToQueueBtn.title = '';
        }
    }
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

async function addToQueue() {
    if (!currentFolderId) return;

    const settings = {
        titleTemplate: elements.titleTemplate?.value || '{filename}',
        descriptionTemplate: elements.descriptionTemplate?.value || '',
        privacy: elements.privacyStatus?.value || 'private',
        recursive: elements.recursiveCheck?.checked ?? true,
        skipDuplicates: elements.skipDuplicatesCheck?.checked ?? true,
        includeMd5: elements.includeMd5Check?.checked ?? true,
    };

    if (elements.addToQueueBtn) elements.addToQueueBtn.disabled = true;
    showToast('キューに追加中...', 'info');

    const result = await uploadFolder(currentFolderId, settings);

    if (elements.addToQueueBtn) elements.addToQueueBtn.disabled = false;

    if (result) {
        showToast(`${result.added_count}件をキューに追加しました`, 'success');
        if (result.skipped_count > 0) {
            showToast(`${result.skipped_count}件をスキップしました`, 'warning');
        }
        refreshQueueList();
    }
}

async function refreshQueueList() {
    const data = await getQueueStatus();

    if (elements.queueCount) {
        elements.queueCount.textContent = data.status?.total_jobs || data.jobs?.length || 0;
    }

    if (!elements.queueList) return;

    if (!data.jobs || data.jobs.length === 0) {
        elements.queueList.innerHTML = '<p class="empty-state">アップロード待ちの動画はありません</p>';
        return;
    }

    elements.queueList.innerHTML = '';

    data.jobs.forEach(job => {
        const item = document.createElement('div');
        item.className = `queue-item status-${job.status}`;

        const progressBar = job.progress > 0
            ? `<div class="progress-bar"><div class="progress-fill" style="width: ${job.progress}%"></div></div>`
            : '';

        let actionBtn = '';
        if (job.status === 'pending' || job.status === 'downloading') {
            actionBtn = `<button class="btn-icon btn-cancel" onclick="cancelJob('${job.id}')" title="キャンセル">⛔</button>`;
        } else if (job.status !== 'uploading') {
            // Completed, failed, cancelled can be deleted
            // Uploading cannot be cancelled (safely) or deleted yet in this simple UI
            actionBtn = `<button class="btn-icon btn-delete" onclick="deleteJob('${job.id}')" title="削除">🗑️</button>`;
        }

        item.innerHTML = `
            <div class="job-info">
                <span class="job-name">${job.drive_file_name}</span>
                <span class="job-status">${job.status} ${job.message ? '- ' + job.message : ''}</span>
            </div>
            ${progressBar}
            ${actionBtn}
        `;

        elements.queueList.appendChild(item);
    });

    // Update progress section
    // 進捗状況セクションの更新を追加
    const activeJobs = data.jobs.filter(j =>
        j.status === 'downloading' || j.status === 'uploading'
    );

    if (elements.progressInfo) {
        if (activeJobs.length === 0) {
            elements.progressInfo.innerHTML =
                '<p class="empty-state">アップロード中の動画はありません</p>';
        } else {
            elements.progressInfo.innerHTML = '';
            activeJobs.forEach(job => {
                const progressItem = document.createElement('div');
                progressItem.className = 'progress-item';

                const statusText = job.status === 'downloading'
                    ? 'ダウンロード中'
                    : 'アップロード中';

                progressItem.innerHTML = `
                    <div class="progress-header">
                        <span class="progress-filename">${job.drive_file_name}</span>
                        <span class="progress-percentage">${Math.round(job.progress)}%</span>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${job.progress}%"></div>
                    </div>
                    <div class="progress-status">${statusText}: ${job.message}</div>
                `;

                elements.progressInfo.appendChild(progressItem);
            });
        }
    }
}

// Event Listeners
document.addEventListener('DOMContentLoaded', () => {
    // Browse folders button
    if (elements.browseBtn) {
        elements.browseBtn.addEventListener('click', () => {
            openModal();
            // Reset select current folder button text
            if (elements.selectCurrentFolderBtn) {
                elements.selectCurrentFolderBtn.textContent = 'このフォルダを選択';
                elements.selectCurrentFolderBtn.disabled = false;
            }
        });
    }

    // Modal controls
    if (elements.closeModal) {
        elements.closeModal.addEventListener('click', closeModalFn);
    }
    if (elements.cancelSelectBtn) {
        elements.cancelSelectBtn.addEventListener('click', closeModalFn);
    }
    if (elements.selectFolderBtn) {
        elements.selectFolderBtn.addEventListener('click', selectFolder);
    }

    // Breadcrumb root click
    if (elements.breadcrumb) {
        const root = elements.breadcrumb.querySelector('.breadcrumb-item');
        if (root) {
            root.addEventListener('click', () => {
                // Clear breadcrumb except root
                while (root.nextSibling) {
                    root.nextSibling.remove();
                }
                loadFolderContents('root');
            });
        }
    }

    // Scan button
    if (elements.scanBtn) {
        elements.scanBtn.addEventListener('click', performScan);
    }

    // Add to queue button
    if (elements.addToQueueBtn) {
        elements.addToQueueBtn.addEventListener('click', addToQueue);
    }

    // Schedule Settings
    if (elements.saveScheduleBtn) {
        elements.saveScheduleBtn.addEventListener('click', saveScheduleSettings);
    }
    if (elements.deleteScheduleBtn) {
        elements.deleteScheduleBtn.addEventListener('click', deleteScheduleSettings);
    }
    if (elements.validateFolderBtn) {
        elements.validateFolderBtn.addEventListener('click', validateFolderUrl);
    }
    if (elements.scheduleEnabled) {
        elements.scheduleEnabled.addEventListener('change', (e) => {
            updateScheduleStatusDisplay(e.target.checked);
        });
    }

    // Close modal on outside click
    if (elements.modal) {
        elements.modal.addEventListener('click', (e) => {
            if (e.target === elements.modal) {
                closeModalFn();
            }
        });
    }

    // Select Current Folder button
    if (elements.selectCurrentFolderBtn) {
        elements.selectCurrentFolderBtn.addEventListener('click', selectCurrentFolder);
    }

    // Initial data load
    refreshQueueList();
    updateQuotaStatus();

    // Load schedule settings
    loadScheduleSettings().then(settings => {
        if (settings) populateScheduleForm(settings);
    });

    // Periodic queue refresh
    setInterval(() => {
        refreshQueueList();
        updateQuotaStatus();
    }, 5000);
});
