/* ================================================
   ShieldTube Full-Screen Video Player
   ================================================ */

const Player = {
  _video: null,
  _el: null,
  _overlay: null,
  _controls: null,
  _topBar: null,
  _seekBar: null,
  _progressTimer: null,
  _hideTimer: null,
  _sponsorSegments: [],
  _chapters: [],
  _currentSpeed: 1,
  _speeds: [0.5, 0.75, 1, 1.25, 1.5, 2],
  _controlsVisible: true,
  _seeking: false,
  _startPosition: 0,

  /** Helper: create an SVG icon element from a path string */
  _svgIcon(pathD, size = 24) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'currentColor');
    svg.setAttribute('width', String(size));
    svg.setAttribute('height', String(size));
    const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    p.setAttribute('d', pathD);
    svg.appendChild(p);
    return svg;
  },

  /** Play icon SVG path */
  _ICON_PLAY: 'M8 5v14l11-7z',
  /** Pause icon SVG path */
  _ICON_PAUSE: 'M6 19h4V5H6v14zm8-14v14h4V5h-4z',
  /** Back arrow SVG path */
  _ICON_BACK: 'M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z',
  /** Rewind SVG path */
  _ICON_REWIND: 'M11.99 5V1l-5 5 5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6h-2c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z',
  /** Forward SVG path */
  _ICON_FORWARD: 'M12.01 5V1l5 5-5 5V7c-3.31 0-6 2.69-6 6s2.69 6 6 6 6-2.69 6-6h2c0 4.42-3.58 8-8 8s-8-3.58-8-8 3.58-8 8-8z',
  /** Subtitle SVG path */
  _ICON_SUBTITLES: 'M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 14H4V6h16v12zM6 10h2v2H6v-2zm0 4h8v2H6v-2zm10 0h2v2h-2v-2zm-6-4h8v2h-8v-2z',

  /**
   * Open the player with a video.
   * @param {object} video - { id, title, duration, position }
   */
  async open(video) {
    this._video = video;
    this._currentSpeed = 1;
    this._sponsorSegments = [];
    this._chapters = [];
    this._startPosition = video.position || 0;

    const overlay = document.getElementById('player-overlay');
    const container = document.getElementById('player-container');
    this._overlay = overlay;

    this._buildPlayer(container);

    overlay.hidden = false;
    void overlay.offsetHeight;

    const streamUrl = `${API.baseUrl}/api/video/${encodeURIComponent(video.id)}/stream`;
    this._el.src = streamUrl;

    this._loadSponsorSegments(video.id);
    this._loadChapters(video.id);
    this._tryLandscapeLock();
    this._startProgressReporting();
  },

  /** Build player DOM using safe DOM APIs */
  _buildPlayer(container) {
    while (container.firstChild) container.removeChild(container.firstChild);

    // Video element
    const videoEl = document.createElement('video');
    videoEl.className = 'player__video';
    videoEl.playsInline = true;
    videoEl.autoplay = true;
    videoEl.preload = 'auto';
    this._el = videoEl;
    container.appendChild(videoEl);

    // Top bar
    const topBar = document.createElement('div');
    topBar.className = 'player__top-bar';
    this._topBar = topBar;

    const backBtn = document.createElement('button');
    backBtn.className = 'player__back-btn';
    backBtn.setAttribute('aria-label', 'Close player');
    backBtn.appendChild(this._svgIcon(this._ICON_BACK));
    backBtn.addEventListener('click', () => this.close('abandoned'));
    topBar.appendChild(backBtn);

    const titleEl = document.createElement('span');
    titleEl.className = 'player__title';
    titleEl.textContent = this._video?.title || '';
    topBar.appendChild(titleEl);

    container.appendChild(topBar);

    // Controls
    const controls = document.createElement('div');
    controls.className = 'player__controls';
    this._controls = controls;

    // Seek row
    const seekRow = document.createElement('div');
    seekRow.className = 'player__seek-row';

    const currentTime = document.createElement('span');
    currentTime.className = 'player__time';
    currentTime.id = 'player-current-time';
    currentTime.textContent = '0:00';
    seekRow.appendChild(currentTime);

    const seekBar = document.createElement('div');
    seekBar.className = 'player__seek';
    this._seekBar = seekBar;

    const seekTrack = document.createElement('div');
    seekTrack.className = 'player__seek-track';

    const seekBuffered = document.createElement('div');
    seekBuffered.className = 'player__seek-buffered';
    seekBuffered.id = 'player-buffered';
    seekTrack.appendChild(seekBuffered);

    const seekProgress = document.createElement('div');
    seekProgress.className = 'player__seek-progress';
    seekProgress.id = 'player-progress';
    seekTrack.appendChild(seekProgress);

    const seekThumb = document.createElement('div');
    seekThumb.className = 'player__seek-thumb';
    seekThumb.id = 'player-thumb';
    seekTrack.appendChild(seekThumb);

    seekBar.appendChild(seekTrack);
    seekRow.appendChild(seekBar);

    const totalTime = document.createElement('span');
    totalTime.className = 'player__time';
    totalTime.id = 'player-total-time';
    totalTime.textContent = '0:00';
    seekRow.appendChild(totalTime);

    controls.appendChild(seekRow);

    // Button row
    const buttonRow = document.createElement('div');
    buttonRow.className = 'player__button-row';

    // Speed button
    const speedBtn = document.createElement('button');
    speedBtn.className = 'player__btn';
    speedBtn.id = 'player-speed-btn';
    speedBtn.setAttribute('aria-label', 'Playback speed');
    const speedLabel = document.createElement('span');
    speedLabel.className = 'player__speed-label';
    speedLabel.id = 'player-speed-label';
    speedLabel.textContent = '1x';
    speedBtn.appendChild(speedLabel);
    speedBtn.addEventListener('click', () => this._cycleSpeed());
    buttonRow.appendChild(speedBtn);

    // Rewind 10s
    const rewBtn = document.createElement('button');
    rewBtn.className = 'player__btn';
    rewBtn.setAttribute('aria-label', 'Rewind 10 seconds');
    rewBtn.appendChild(this._svgIcon(this._ICON_REWIND));
    rewBtn.addEventListener('click', () => {
      if (this._el) this._el.currentTime = Math.max(0, this._el.currentTime - 10);
    });
    buttonRow.appendChild(rewBtn);

    // Play/Pause
    const playBtn = document.createElement('button');
    playBtn.className = 'player__btn player__btn--play';
    playBtn.id = 'player-play-btn';
    playBtn.setAttribute('aria-label', 'Play');
    playBtn.appendChild(this._svgIcon(this._ICON_PLAY, 32));
    playBtn.addEventListener('click', () => this._togglePlayPause());
    buttonRow.appendChild(playBtn);

    // Forward 10s
    const fwdBtn = document.createElement('button');
    fwdBtn.className = 'player__btn';
    fwdBtn.setAttribute('aria-label', 'Forward 10 seconds');
    fwdBtn.appendChild(this._svgIcon(this._ICON_FORWARD));
    fwdBtn.addEventListener('click', () => {
      if (this._el) this._el.currentTime = Math.min(this._el.duration || 0, this._el.currentTime + 10);
    });
    buttonRow.appendChild(fwdBtn);

    // Subtitle button
    const subBtn = document.createElement('button');
    subBtn.className = 'player__btn';
    subBtn.setAttribute('aria-label', 'Subtitles');
    subBtn.appendChild(this._svgIcon(this._ICON_SUBTITLES));
    subBtn.addEventListener('click', () => Toast.show('Subtitles coming soon'));
    buttonRow.appendChild(subBtn);

    controls.appendChild(buttonRow);
    container.appendChild(controls);

    // Tap to toggle controls
    videoEl.addEventListener('click', () => this._toggleControls());

    // Video events
    videoEl.addEventListener('loadedmetadata', () => this._onMetadataLoaded());
    videoEl.addEventListener('timeupdate', () => this._onTimeUpdate());
    videoEl.addEventListener('play', () => this._onPlay());
    videoEl.addEventListener('pause', () => this._onPause());
    videoEl.addEventListener('ended', () => this._onEnded());
    videoEl.addEventListener('progress', () => this._onBufferUpdate());

    // Seek bar touch/mouse
    this._initSeekBar(seekBar);

    // Auto-hide controls
    this._scheduleHideControls();
  },

  _initSeekBar(seekBar) {
    const onSeek = (clientX) => {
      const rect = seekBar.getBoundingClientRect();
      const pct = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
      if (this._el?.duration) {
        this._el.currentTime = pct * this._el.duration;
        this._updateSeekVisuals(pct);
      }
    };

    seekBar.addEventListener('touchstart', (e) => {
      this._seeking = true;
      onSeek(e.touches[0].clientX);
    }, { passive: true });

    seekBar.addEventListener('touchmove', (e) => {
      if (this._seeking) onSeek(e.touches[0].clientX);
    }, { passive: true });

    seekBar.addEventListener('touchend', () => { this._seeking = false; });

    seekBar.addEventListener('mousedown', (e) => {
      this._seeking = true;
      onSeek(e.clientX);
      const onMove = (ev) => onSeek(ev.clientX);
      const onUp = () => {
        this._seeking = false;
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });
  },

  _togglePlayPause() {
    if (!this._el) return;
    if (this._el.paused) {
      this._el.play();
    } else {
      this._el.pause();
    }
  },

  _cycleSpeed() {
    const idx = this._speeds.indexOf(this._currentSpeed);
    const nextIdx = (idx + 1) % this._speeds.length;
    this._currentSpeed = this._speeds[nextIdx];
    if (this._el) this._el.playbackRate = this._currentSpeed;
    const label = document.getElementById('player-speed-label');
    if (label) label.textContent = `${this._currentSpeed}x`;
    Toast.show(`Speed: ${this._currentSpeed}x`, 1500);
  },

  _toggleControls() {
    this._controlsVisible = !this._controlsVisible;
    this._controls?.classList.toggle('hidden', !this._controlsVisible);
    this._topBar?.classList.toggle('hidden', !this._controlsVisible);
    if (this._controlsVisible) this._scheduleHideControls();
  },

  _scheduleHideControls() {
    clearTimeout(this._hideTimer);
    this._hideTimer = setTimeout(() => {
      if (this._el && !this._el.paused) {
        this._controlsVisible = false;
        this._controls?.classList.add('hidden');
        this._topBar?.classList.add('hidden');
      }
    }, 3000);
  },

  _updateSeekVisuals(pct) {
    const progress = document.getElementById('player-progress');
    const thumb = document.getElementById('player-thumb');
    if (progress) progress.style.width = `${pct * 100}%`;
    if (thumb) thumb.style.left = `${pct * 100}%`;
  },

  _formatTime(seconds) {
    if (!seconds || !isFinite(seconds)) return '0:00';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    return `${m}:${String(s).padStart(2, '0')}`;
  },

  // ---- Video Event Handlers ----

  _onMetadataLoaded() {
    const total = document.getElementById('player-total-time');
    if (total && this._el) total.textContent = this._formatTime(this._el.duration);

    if (this._startPosition > 0 && this._el) {
      this._el.currentTime = this._startPosition;
      Toast.show(`Resuming from ${this._formatTime(this._startPosition)}`, 2000);
    }

    this._renderChapterMarkers();
  },

  _onTimeUpdate() {
    if (this._seeking || !this._el) return;
    const current = this._el.currentTime;
    const duration = this._el.duration || 1;
    const pct = current / duration;

    this._updateSeekVisuals(pct);

    const currentTimeEl = document.getElementById('player-current-time');
    if (currentTimeEl) currentTimeEl.textContent = this._formatTime(current);

    this._checkSponsorSegments(current);
  },

  _onPlay() {
    const btn = document.getElementById('player-play-btn');
    if (btn) {
      while (btn.firstChild) btn.removeChild(btn.firstChild);
      btn.appendChild(this._svgIcon(this._ICON_PAUSE, 32));
    }
    this._scheduleHideControls();
  },

  _onPause() {
    const btn = document.getElementById('player-play-btn');
    if (btn) {
      while (btn.firstChild) btn.removeChild(btn.firstChild);
      btn.appendChild(this._svgIcon(this._ICON_PLAY, 32));
    }
    this._controlsVisible = true;
    this._controls?.classList.remove('hidden');
    this._topBar?.classList.remove('hidden');
    clearTimeout(this._hideTimer);
  },

  _onEnded() {
    this._reportProgress('completed');
    Toast.show('Video ended');
    setTimeout(() => this.close('completed'), 1500);
  },

  _onBufferUpdate() {
    if (!this._el?.buffered?.length) return;
    const duration = this._el.duration || 1;
    const buffered = this._el.buffered.end(this._el.buffered.length - 1);
    const el = document.getElementById('player-buffered');
    if (el) el.style.width = `${(buffered / duration) * 100}%`;
  },

  // ---- SponsorBlock ----

  async _loadSponsorSegments(videoId) {
    try {
      const data = await API.getSponsorSegments(videoId);
      this._sponsorSegments = data?.segments || data || [];
    } catch {
      this._sponsorSegments = [];
    }
  },

  _checkSponsorSegments(currentTime) {
    for (const seg of this._sponsorSegments) {
      const start = seg.segment?.[0] ?? seg.start;
      const end = seg.segment?.[1] ?? seg.end;
      if (currentTime >= start && currentTime < end - 0.5) {
        if (this._el) this._el.currentTime = end;
        Toast.show(`Skipped ${seg.category || 'sponsor'} segment`, 2000, 'warning');
        break;
      }
    }
  },

  // ---- Chapters ----

  async _loadChapters(videoId) {
    try {
      const meta = await API.getVideoMeta(videoId);
      this._chapters = meta?.chapters || [];
    } catch {
      this._chapters = [];
    }
  },

  _renderChapterMarkers() {
    if (!this._chapters.length || !this._el?.duration) return;
    const track = this._seekBar?.querySelector('.player__seek-track');
    if (!track) return;

    this._chapters.forEach(ch => {
      const pct = (ch.start_time || ch.start || 0) / this._el.duration * 100;
      const marker = document.createElement('div');
      marker.className = 'player__seek-chapter';
      marker.style.left = `${pct}%`;
      marker.title = ch.title || '';
      track.appendChild(marker);
    });
  },

  // ---- Progress Reporting ----

  _startProgressReporting() {
    this._stopProgressReporting();
    this._progressTimer = setInterval(() => {
      this._reportProgress('playing');
    }, 10000);
  },

  _stopProgressReporting() {
    if (this._progressTimer) {
      clearInterval(this._progressTimer);
      this._progressTimer = null;
    }
  },

  async _reportProgress(status) {
    if (!this._video?.id || !this._el) return;
    try {
      await API.reportProgress(this._video.id, {
        position_seconds: Math.floor(this._el.currentTime),
        duration: Math.floor(this._el.duration || 0),
        event: status,
      });
    } catch {
      // Silently fail
    }
  },

  // ---- Lifecycle ----

  close(reason = 'abandoned') {
    this._reportProgress(reason);
    this._stopProgressReporting();
    clearTimeout(this._hideTimer);

    if (this._el) {
      this._el.pause();
      this._el.removeAttribute('src');
      this._el.load();
    }

    const overlay = document.getElementById('player-overlay');
    if (overlay) overlay.hidden = true;

    try {
      screen.orientation?.unlock?.();
    } catch { /* not supported */ }

    this._video = null;
    this._el = null;
    this._controls = null;
    this._topBar = null;
    this._seekBar = null;
  },

  _tryLandscapeLock() {
    try {
      screen.orientation?.lock?.('landscape').catch(() => {});
    } catch { /* not supported */ }
  },
};
