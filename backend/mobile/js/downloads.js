/* ================================================
   ShieldTube — Download Progress UI
   DownloadTracker  · ProgressRing  · DownloadsTab
   ================================================ */

/* ---- DownloadTracker (singleton polling manager) ---- */
const DownloadTracker = {
    _activeDownloads: {},     // {videoId: {status, percent, bytes_downloaded, bytes_total}}
    _pollingTimer: null,
    _pollingInterval: 2500,
    _listeners: new Set(),
    _queueSize: 0,

    init() {
        // One-time check; only start polling if downloads are active
        this._poll().then(() => {
            if (this.activeCount > 0 || this.isDownloading) {
                this._startPolling();
            }
        }).catch(() => {});
    },

    async enqueue(videoId) {
        try {
            const result = await API.enqueueDownload(videoId);
            if (result.status === 'already_cached') {
                this._activeDownloads[videoId] = { status: 'cached', percent: 100 };
                this._notifyListeners();
                return result;
            }
            this._activeDownloads[videoId] = { status: 'queued', percent: 0 };
            this._startPolling();
            this._notifyListeners();
            return result;
        } catch (err) {
            console.error('Enqueue failed:', err);
            throw err;
        }
    },

    async _poll() {
        try {
            const data = await API.getActiveDownloads();
            const newState = {};

            // Update active downloads
            for (const dl of (data.active || [])) {
                newState[dl.video_id] = {
                    status: dl.status,
                    percent: dl.percent,
                    bytes_downloaded: dl.bytes_downloaded,
                    bytes_total: dl.bytes_total,
                };
            }

            // Check for transitions (downloading -> cached)
            for (const [id, prev] of Object.entries(this._activeDownloads)) {
                if (prev.status === 'downloading' && !newState[id]) {
                    // Was downloading, no longer active = finished
                    newState[id] = { status: 'cached', percent: 100 };
                }
            }

            this._activeDownloads = { ...newState };
            this._queueSize = data.queue_size || 0;
            this._notifyListeners();

            // Stop polling if nothing active
            const hasActive = data.active?.length > 0 || data.queue_size > 0;
            if (!hasActive) {
                this._stopPolling();
            } else if (!this._pollingTimer) {
                this._startPolling();
            }
        } catch (err) {
            console.warn('Download poll failed:', err);
            this._stopPolling();
        }
    },

    _startPolling() {
        if (this._pollingTimer) return;
        this._pollingTimer = setInterval(() => this._poll(), this._pollingInterval);
    },

    _stopPolling() {
        if (this._pollingTimer) {
            clearInterval(this._pollingTimer);
            this._pollingTimer = null;
        }
    },

    getStatus(videoId) {
        return this._activeDownloads[videoId] || null;
    },

    get activeCount() {
        const active = Object.values(this._activeDownloads).filter(
            d => d.status === 'downloading' || d.status === 'queued'
        ).length;
        return active + this._queueSize;
    },

    get isDownloading() {
        return Object.values(this._activeDownloads).some(d => d.status === 'downloading');
    },

    onChange(cb) { this._listeners.add(cb); },
    offChange(cb) { this._listeners.delete(cb); },

    _notifyListeners() {
        ProgressRing.update(this.activeCount, this.isDownloading);
        for (const cb of this._listeners) {
            try { cb(this._activeDownloads); } catch {}
        }
    },
};

/* ---- ProgressRing (global circular progress) ---- */
const ProgressRing = {
    _el: null,
    _badge: null,

    init() {
        const ring = document.getElementById('download-ring');
        if (!ring) return;
        this._el = ring;

        // Build SVG
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('class', 'download-ring__svg');
        svg.setAttribute('viewBox', '0 0 40 40');

        const track = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        track.setAttribute('class', 'download-ring__track');
        track.setAttribute('cx', '20');
        track.setAttribute('cy', '20');
        track.setAttribute('r', '16');
        svg.appendChild(track);

        const arc = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        arc.setAttribute('class', 'download-ring__arc');
        arc.setAttribute('cx', '20');
        arc.setAttribute('cy', '20');
        arc.setAttribute('r', '16');
        arc.setAttribute('stroke-dasharray', '100.5');
        arc.setAttribute('stroke-dashoffset', '100.5');
        svg.appendChild(arc);

        ring.appendChild(svg);

        // Badge
        const badge = document.createElement('span');
        badge.className = 'download-ring__badge';
        badge.hidden = true;
        ring.appendChild(badge);
        this._badge = badge;

        // Tap to open downloads
        ring.addEventListener('click', () => {
            window.location.hash = 'downloads';
        });
    },

    update(activeCount, isDownloading) {
        if (!this._el) return;

        if (activeCount === 0 && !isDownloading) {
            this._el.hidden = true;
            return;
        }

        this._el.hidden = false;

        // Indeterminate spin when downloading
        if (isDownloading) {
            this._el.classList.add('download-ring--indeterminate');
        } else {
            this._el.classList.remove('download-ring--indeterminate');
        }

        // Badge
        if (activeCount > 0) {
            this._badge.textContent = String(activeCount);
            this._badge.hidden = false;
        } else {
            this._badge.hidden = true;
        }
    },
};

/* ---- DownloadsTab ---- */
const DownloadsTab = {
    _listener: null,

    async render(container) {
        // Cleanup previous listener
        if (this._listener) {
            DownloadTracker.offChange(this._listener);
        }

        const wrapper = document.createElement('div');
        wrapper.className = 'downloads-screen screen-enter';

        const title = document.createElement('h2');
        title.className = 'screen-title';
        title.textContent = 'Downloads';
        wrapper.appendChild(title);

        const listContainer = document.createElement('div');
        listContainer.id = 'downloads-list';
        wrapper.appendChild(listContainer);

        container.appendChild(wrapper);

        // Do an immediate poll
        await DownloadTracker._poll();
        await this._loadAndRender(listContainer);

        // Subscribe to updates for active downloads
        this._listener = () => this._updateActiveSection(listContainer);
        DownloadTracker.onChange(this._listener);
    },

    async _loadAndRender(container) {
        while (container.firstChild) container.removeChild(container.firstChild);

        try {
            const library = await API.getDownloadLibrary();
            const videos = library.videos || [];
            const activeDownloads = DownloadTracker._activeDownloads;

            // Section 1: Currently downloading
            const downloading = Object.entries(activeDownloads)
                .filter(([, d]) => d.status === 'downloading' || d.status === 'queued')
                .map(([id, d]) => ({ id, ...d }));

            if (downloading.length > 0) {
                const section = this._createSection('Downloading');
                for (const dl of downloading) {
                    section.appendChild(this._renderActiveEntry(dl));
                }
                container.appendChild(section);
            }

            // Section 2: Manual downloads
            const manual = videos.filter(v => v.download_source === 'manual');
            if (manual.length > 0) {
                const section = this._createSection('My Downloads');
                for (const v of manual) {
                    section.appendChild(this._renderCachedEntry(v));
                }
                container.appendChild(section);
            }

            // Section 3: Auto-cached
            const auto = videos.filter(v => v.download_source !== 'manual');
            if (auto.length > 0) {
                if (manual.length > 0) {
                    const divider = document.createElement('div');
                    divider.className = 'downloads-section__divider';
                    container.appendChild(divider);
                }
                const section = this._createSection('Auto-cached');
                for (const v of auto) {
                    section.appendChild(this._renderCachedEntry(v));
                }
                container.appendChild(section);
            }

            if (videos.length === 0 && downloading.length === 0) {
                const empty = document.createElement('div');
                empty.className = 'empty-state';
                const emptyTitle = document.createElement('h3');
                emptyTitle.className = 'empty-state__title';
                emptyTitle.textContent = 'No downloads yet';
                empty.appendChild(emptyTitle);
                const emptyText = document.createElement('p');
                emptyText.className = 'empty-state__text';
                emptyText.textContent = 'Tap the download button on any video to start';
                empty.appendChild(emptyText);
                container.appendChild(empty);
            }
        } catch (err) {
            const errDiv = document.createElement('div');
            errDiv.className = 'empty-state';
            const errTitle = document.createElement('h3');
            errTitle.className = 'empty-state__title';
            errTitle.textContent = 'Could not load downloads';
            errDiv.appendChild(errTitle);
            container.appendChild(errDiv);
        }
    },

    _createSection(title) {
        const section = document.createElement('div');
        section.className = 'downloads-section';
        const h = document.createElement('h3');
        h.className = 'downloads-section__title';
        h.textContent = title;
        section.appendChild(h);
        return section;
    },

    _renderActiveEntry(dl) {
        const entry = document.createElement('div');
        entry.className = 'download-entry';
        entry.dataset.videoId = dl.id;

        const thumb = document.createElement('img');
        thumb.className = 'download-entry__thumb';
        thumb.src = `${API.baseUrl}/api/video/${encodeURIComponent(dl.id)}/thumbnail`;
        thumb.alt = '';
        entry.appendChild(thumb);

        const info = document.createElement('div');
        info.className = 'download-entry__info';

        const titleEl = document.createElement('div');
        titleEl.className = 'download-entry__title';
        titleEl.textContent = dl.title || dl.id;
        info.appendChild(titleEl);

        const meta = document.createElement('div');
        meta.className = 'download-entry__meta';
        const pct = document.createElement('span');
        pct.className = 'download-entry__pct';
        pct.textContent = dl.status === 'queued' ? 'Queued' : `${Math.round(dl.percent || 0)}%`;
        meta.appendChild(pct);
        if (dl.bytes_total) {
            const size = document.createElement('span');
            size.textContent = DownloadsTab._formatSize(dl.bytes_downloaded || 0) + ' / ' + DownloadsTab._formatSize(dl.bytes_total);
            meta.appendChild(size);
        }
        info.appendChild(meta);

        // Progress bar
        const bar = document.createElement('div');
        bar.className = 'download-entry__progress-bar';
        const fill = document.createElement('div');
        fill.className = 'download-entry__progress-fill';
        fill.style.width = `${dl.percent || 0}%`;
        bar.appendChild(fill);
        info.appendChild(bar);

        entry.appendChild(info);
        return entry;
    },

    _renderCachedEntry(video) {
        const entry = document.createElement('div');
        entry.className = 'download-entry download-entry--cached';
        entry.dataset.videoId = video.id;

        const thumb = document.createElement('img');
        thumb.className = 'download-entry__thumb';
        thumb.src = `${API.baseUrl}/api/video/${encodeURIComponent(video.id)}/thumbnail`;
        thumb.alt = '';
        entry.appendChild(thumb);

        const info = document.createElement('div');
        info.className = 'download-entry__info';

        const titleEl = document.createElement('div');
        titleEl.className = 'download-entry__title';
        titleEl.textContent = video.title || video.id;
        info.appendChild(titleEl);

        const meta = document.createElement('div');
        meta.className = 'download-entry__meta';
        if (video.channel_name) {
            const ch = document.createElement('span');
            ch.textContent = video.channel_name;
            meta.appendChild(ch);
        }
        if (video.file_size) {
            const sz = document.createElement('span');
            sz.textContent = DownloadsTab._formatSize(video.file_size);
            meta.appendChild(sz);
        }
        if (video.duration) {
            const dur = document.createElement('span');
            dur.textContent = VideoCard.formatDuration(video.duration);
            meta.appendChild(dur);
        }
        info.appendChild(meta);
        entry.appendChild(info);

        // Tap to play
        entry.addEventListener('click', () => {
            Player.open({
                id: video.id,
                title: video.title,
                channel: video.channel_name,
                duration: video.duration,
            });
        });

        return entry;
    },

    _updateActiveSection(container) {
        // Update progress bars for active downloads
        const entries = container.querySelectorAll('.download-entry[data-video-id]');
        for (const entry of entries) {
            const videoId = entry.dataset.videoId;
            const status = DownloadTracker.getStatus(videoId);
            if (status && (status.status === 'downloading' || status.status === 'queued')) {
                const fill = entry.querySelector('.download-entry__progress-fill');
                if (fill) fill.style.width = `${status.percent || 0}%`;
                const pct = entry.querySelector('.download-entry__pct');
                if (pct) pct.textContent = status.status === 'queued' ? 'Queued' : `${Math.round(status.percent || 0)}%`;
            }
        }
    },

    _formatSize(bytes) {
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + ' KB';
        if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
        return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
    },
};
