/* ================================================
   ShieldTube UI Components
   ================================================ */

/* ---- Video Card ---- */
const VideoCard = {
  /**
   * Render a video card element.
   * @param {object} video - { id, title, channel, thumbnail, duration, cached }
   * @returns {string} HTML string
   */
  render(video) {
    const thumbUrl = video.thumbnail
      ? `${API.baseUrl}/api/video/${encodeURIComponent(video.id)}/thumbnail`
      : '';
    const durationStr = VideoCard.formatDuration(video.duration);

    // All interpolated values are escaped via VideoCard.esc() to prevent XSS
    return `
      <article class="video-card" data-video-id="${VideoCard.esc(video.id)}" role="button" tabindex="0">
        <div class="video-card__thumb">
          ${thumbUrl
            ? `<img src="${VideoCard.esc(thumbUrl)}" alt="" loading="lazy" data-loaded="false"
                    onload="this.dataset.loaded='true'" onerror="this.style.display='none'">`
            : ''}
          ${durationStr ? `<span class="video-card__duration">${durationStr}</span>` : ''}
          ${video.cached ? '<span class="video-card__cached"></span>' : ''}
        </div>
        <div class="video-card__info">
          <h3 class="video-card__title">${VideoCard.esc(video.title || 'Untitled')}</h3>
          <p class="video-card__channel">${VideoCard.esc(video.channel || '')}</p>
        </div>
      </article>
    `;
  },

  /**
   * Format seconds into HH:MM:SS or MM:SS.
   * @param {number} seconds
   * @returns {string}
   */
  formatDuration(seconds) {
    if (!seconds || seconds <= 0) return '';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) {
      return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    }
    return `${m}:${String(s).padStart(2, '0')}`;
  },

  /**
   * Escape HTML entities to prevent XSS.
   * Uses textContent assignment which is safe by design.
   */
  esc(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
  },
};


/* ---- Feed ---- */
const Feed = {
  /**
   * Render a grid of video cards into a container.
   * Uses DOM APIs for safe content insertion.
   * @param {Array} videos
   * @param {HTMLElement} container
   */
  render(videos, container) {
    // Clear previous content safely
    while (container.firstChild) container.removeChild(container.firstChild);

    if (!videos || videos.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';

      const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      icon.setAttribute('class', 'empty-state__icon');
      icon.setAttribute('viewBox', '0 0 24 24');
      icon.setAttribute('fill', 'currentColor');
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', 'M21 3H3c-1.11 0-2 .89-2 2v12c0 1.1.89 2 2 2h5v2h8v-2h5c1.1 0 1.99-.9 1.99-2L23 5c0-1.11-.9-2-2-2zm0 14H3V5h18v12zm-5-6l-7 4V7z');
      icon.appendChild(path);
      empty.appendChild(icon);

      const title = document.createElement('h3');
      title.className = 'empty-state__title';
      title.textContent = 'No videos yet';
      empty.appendChild(title);

      const text = document.createElement('p');
      text.className = 'empty-state__text';
      text.textContent = 'Videos will appear here once your backend is running and connected.';
      empty.appendChild(text);

      container.appendChild(empty);
      return;
    }

    const grid = document.createElement('div');
    grid.className = 'video-grid';

    // Build cards from sanitized template strings (all values escaped via esc())
    const fragment = document.createDocumentFragment();
    const tempDiv = document.createElement('div');

    videos.forEach(v => {
      tempDiv.innerHTML = VideoCard.render(v);
      while (tempDiv.firstChild) {
        fragment.appendChild(tempDiv.firstChild);
      }
    });

    grid.appendChild(fragment);
    container.appendChild(grid);

    // Event delegation for card clicks
    grid.addEventListener('click', (e) => {
      const card = e.target.closest('.video-card');
      if (!card) return;
      const videoId = card.dataset.videoId;
      const video = videos.find(v => v.id === videoId);
      if (video) BottomSheet.show(video);
    });

    // Keyboard support
    grid.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        const card = e.target.closest('.video-card');
        if (card) {
          e.preventDefault();
          card.click();
        }
      }
    });
  },
};


/* ---- Bottom Sheet ---- */
const BottomSheet = {
  _currentVideo: null,

  /**
   * Show bottom sheet with video details.
   * Uses DOM APIs for safe content construction.
   * @param {object} video
   */
  show(video) {
    this._currentVideo = video;
    const sheet = document.getElementById('bottom-sheet');
    const content = document.getElementById('bottom-sheet-content');

    // Clear previous content safely
    while (content.firstChild) content.removeChild(content.firstChild);

    const thumbUrl = video.thumbnail
      ? `${API.baseUrl}/api/video/${encodeURIComponent(video.id)}/thumbnail`
      : '';

    // Build DOM elements safely
    if (thumbUrl) {
      const img = document.createElement('img');
      img.className = 'bottom-sheet__thumb';
      img.src = thumbUrl;
      img.alt = '';
      content.appendChild(img);
    }

    const title = document.createElement('h2');
    title.className = 'bottom-sheet__title';
    title.textContent = video.title || 'Untitled';
    content.appendChild(title);

    const meta = document.createElement('div');
    meta.className = 'bottom-sheet__meta';
    if (video.channel) {
      const s = document.createElement('span');
      s.textContent = video.channel;
      meta.appendChild(s);
    }
    if (video.duration) {
      const s = document.createElement('span');
      s.textContent = VideoCard.formatDuration(video.duration);
      meta.appendChild(s);
    }
    if (video.views) {
      const s = document.createElement('span');
      s.textContent = `${BottomSheet.formatViews(video.views)} views`;
      meta.appendChild(s);
    }
    content.appendChild(meta);

    // Action buttons
    const actions = document.createElement('div');
    actions.className = 'bottom-sheet__actions';

    const actionDefs = [
      { action: 'play', label: 'Play', primary: true, icon: 'M8 5v14l11-7z' },
      { action: 'cast', label: 'Cast', primary: false, icon: 'M1 18v3h3c0-1.66-1.34-3-3-3zm0-4v2c2.76 0 5 2.24 5 5h2c0-3.87-3.13-7-7-7zm0-4v2c4.97 0 9 4.03 9 9h2c0-6.08-4.93-11-11-11zm20-7H3c-1.1 0-2 .9-2 2v3h2V5h18v14h-7v2h7c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2z' },
      { action: 'rate-love', label: 'Love', primary: false, icon: 'M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z' },
    ];

    actionDefs.forEach(def => {
      const btn = document.createElement('button');
      btn.className = `bottom-sheet__action${def.primary ? ' bottom-sheet__action--primary' : ''}`;
      btn.dataset.action = def.action;

      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('viewBox', '0 0 24 24');
      svg.setAttribute('fill', 'currentColor');
      const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      p.setAttribute('d', def.icon);
      svg.appendChild(p);
      btn.appendChild(svg);

      const labelNode = document.createTextNode(def.label);
      btn.appendChild(labelNode);

      btn.addEventListener('click', () => BottomSheet.handleAction(def.action, video));
      actions.appendChild(btn);
    });

    content.appendChild(actions);

    sheet.hidden = false;
    // Force reflow for animation
    void sheet.offsetHeight;

    // Backdrop close
    const backdrop = sheet.querySelector('.bottom-sheet__backdrop');
    const closeHandler = () => {
      BottomSheet.hide();
      backdrop.removeEventListener('click', closeHandler);
    };
    backdrop.addEventListener('click', closeHandler);
  },

  /** Hide bottom sheet */
  hide() {
    const sheet = document.getElementById('bottom-sheet');
    const panel = sheet.querySelector('.bottom-sheet__panel');

    panel.style.transform = 'translateY(100%)';
    sheet.querySelector('.bottom-sheet__backdrop').style.opacity = '0';

    setTimeout(() => {
      sheet.hidden = true;
      panel.style.transform = '';
      sheet.querySelector('.bottom-sheet__backdrop').style.opacity = '';
    }, 400);

    this._currentVideo = null;
  },

  /**
   * Handle action button click.
   * @param {string} action
   * @param {object} video
   */
  async handleAction(action, video) {
    switch (action) {
      case 'play':
        BottomSheet.hide();
        Player.open(video);
        break;
      case 'cast':
        try {
          await API.castToShield(video.id);
          Toast.show('Casting to Shield TV');
          BottomSheet.hide();
        } catch {
          Toast.show('Failed to cast', 3000, 'error');
        }
        break;
      case 'rate-love':
        try {
          await API.rateVideo(video.id, 'love');
          Toast.show('Marked as loved');
        } catch {
          Toast.show('Failed to rate', 3000, 'error');
        }
        break;
    }
  },

  formatViews(n) {
    if (!n) return '';
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return String(n);
  },
};


/* ---- Tabs ---- */
const Tabs = {
  /**
   * Render horizontal scrollable tabs.
   * Uses DOM APIs for safe element construction.
   * @param {Array<{id: string, label: string}>} tabs
   * @param {string} active - active tab id
   * @param {function} onChange - callback(tabId)
   * @returns {HTMLElement}
   */
  render(tabs, active, onChange) {
    const container = document.createElement('div');
    container.className = 'tab-bar';

    tabs.forEach(tab => {
      const btn = document.createElement('button');
      btn.className = `tab-bar__item${tab.id === active ? ' active' : ''}`;
      btn.textContent = tab.label;
      btn.addEventListener('click', () => {
        container.querySelectorAll('.tab-bar__item').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        onChange?.(tab.id);
      });
      container.appendChild(btn);
    });

    return container;
  },
};


/* ---- Toast ---- */
const Toast = {
  /**
   * Show a toast notification.
   * @param {string} message
   * @param {number} duration - ms (default 2500)
   * @param {'info'|'warning'|'error'} type
   */
  show(message, duration = 2500, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast${type !== 'info' ? ` toast--${type}` : ''}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
      toast.classList.add('dismissing');
      toast.addEventListener('animationend', () => toast.remove());
    }, duration);
  },
};


/* ---- Skeleton ---- */
const Skeleton = {
  /**
   * Render skeleton loading cards using DOM APIs.
   * @param {number} count
   * @returns {HTMLElement}
   */
  render(count = 6) {
    const grid = document.createElement('div');
    grid.className = 'video-grid';

    for (let i = 0; i < count; i++) {
      const card = document.createElement('div');
      card.className = 'skeleton-card';

      const thumb = document.createElement('div');
      thumb.className = 'skeleton-card__thumb';
      card.appendChild(thumb);

      const line1 = document.createElement('div');
      line1.className = 'skeleton-card__line';
      card.appendChild(line1);

      const line2 = document.createElement('div');
      line2.className = 'skeleton-card__line skeleton-card__line--short';
      card.appendChild(line2);

      grid.appendChild(card);
    }

    return grid;
  },
};
