/* ================================================
   ShieldTube Swipe-to-Rate Training Interface
   ================================================ */

const SwipeTrainer = {
  _stack: [],           // current video candidates
  _rated: 0,            // session counter
  _preloadBuffer: 5,    // how many thumbnails to preload
  _isAnimating: false,  // lock during card fly-out
  _currentCard: null,   // active swipe card element
  _startX: 0,
  _startY: 0,
  _currentX: 0,
  _currentY: 0,
  _isDragging: false,

  /** Render the swipe training screen into a container */
  async render(container) {
    while (container.firstChild) container.removeChild(container.firstChild);

    const screen = document.createElement('div');
    screen.className = 'swipe-screen screen-enter';

    // Header
    const header = document.createElement('div');
    header.className = 'swipe-header';

    const title = document.createElement('h2');
    title.className = 'swipe-header__title';
    title.textContent = 'Train Your Feed';
    header.appendChild(title);

    const counter = document.createElement('p');
    counter.className = 'swipe-header__counter';
    counter.id = 'swipe-counter';
    counter.textContent = '0 videos rated this session';
    header.appendChild(counter);

    screen.appendChild(header);

    // Card stack area
    const stack = document.createElement('div');
    stack.className = 'swipe-stack';
    stack.id = 'swipe-stack';
    screen.appendChild(stack);

    // Hints
    const hints = document.createElement('div');
    hints.className = 'swipe-hints';

    const hintDefs = [
      { label: 'Nope', icon: 'M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z', color: 'var(--color-accent)' },
      { label: 'Love', icon: 'M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z', color: '#FF6B81' },
      { label: 'Interested', icon: 'M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z', color: 'var(--color-primary)' },
    ];

    hintDefs.forEach(h => {
      const hint = document.createElement('div');
      hint.className = 'swipe-hint';

      const iconWrap = document.createElement('div');
      iconWrap.className = 'swipe-hint__icon';
      iconWrap.style.borderColor = h.color;
      iconWrap.style.color = h.color;

      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('viewBox', '0 0 24 24');
      svg.setAttribute('fill', 'currentColor');
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', h.icon);
      svg.appendChild(path);
      iconWrap.appendChild(svg);
      hint.appendChild(iconWrap);

      const label = document.createElement('span');
      label.textContent = h.label;
      hint.appendChild(label);

      hints.appendChild(hint);
    });

    screen.appendChild(hints);
    container.appendChild(screen);

    // Load candidates
    await this._loadCandidates();
    this._renderStack();
  },

  /** Load video candidates from multiple feeds, shuffle */
  async _loadCandidates() {
    const sources = ['recommended', 'subscriptions', 'home'];
    const allVideos = [];

    const results = await Promise.allSettled(
      sources.map(src => API.getFeed(src))
    );

    results.forEach(r => {
      if (r.status === 'fulfilled' && Array.isArray(r.value?.videos || r.value)) {
        const vids = r.value?.videos || r.value;
        allVideos.push(...vids);
      }
    });

    // Deduplicate by ID
    const seen = new Set();
    const unique = [];
    for (const v of allVideos) {
      if (v.id && !seen.has(v.id)) {
        seen.add(v.id);
        unique.push(v);
      }
    }

    // Shuffle (Fisher-Yates)
    for (let i = unique.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [unique[i], unique[j]] = [unique[j], unique[i]];
    }

    this._stack = unique;
    this._preloadThumbnails();
  },

  /** Preload upcoming thumbnails */
  _preloadThumbnails() {
    const upcoming = this._stack.slice(0, this._preloadBuffer);
    upcoming.forEach(v => {
      if (v.thumbnail || v.id) {
        const img = new Image();
        img.src = `${API.baseUrl}/api/video/${encodeURIComponent(v.id)}/thumbnail`;
      }
    });
  },

  /** Render the card stack */
  _renderStack() {
    const stackEl = document.getElementById('swipe-stack');
    if (!stackEl) return;

    while (stackEl.firstChild) stackEl.removeChild(stackEl.firstChild);

    if (this._stack.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';

      const title = document.createElement('h3');
      title.className = 'empty-state__title';
      title.textContent = 'All caught up!';
      empty.appendChild(title);

      const text = document.createElement('p');
      text.className = 'empty-state__text';
      text.textContent = 'No more videos to rate. Check back later!';
      empty.appendChild(text);

      stackEl.appendChild(empty);
      return;
    }

    // Show up to 3 cards in stack (front card on top)
    const visible = this._stack.slice(0, 3);

    visible.forEach((video, idx) => {
      const card = this._createCard(video, idx);
      stackEl.appendChild(card);
    });

    // Bind gestures to top card
    const topCard = stackEl.querySelector('.swipe-card:not(.swipe-card--behind):not(.swipe-card--far-behind)');
    if (topCard) {
      this._currentCard = topCard;
      this._bindGestures(topCard);
    }
  },

  /** Create a swipe card element */
  _createCard(video, stackIndex) {
    const card = document.createElement('div');
    card.className = 'swipe-card';
    card.dataset.videoId = video.id;
    card.style.zIndex = String(10 - stackIndex);

    if (stackIndex === 1) card.classList.add('swipe-card--behind');
    if (stackIndex >= 2) card.classList.add('swipe-card--far-behind');

    // Thumbnail
    const img = document.createElement('img');
    img.className = 'swipe-card__image';
    img.src = `${API.baseUrl}/api/video/${encodeURIComponent(video.id)}/thumbnail`;
    img.alt = '';
    img.loading = stackIndex === 0 ? 'eager' : 'lazy';
    card.appendChild(img);

    // Info area
    const info = document.createElement('div');
    info.className = 'swipe-card__info';

    const title = document.createElement('h3');
    title.className = 'swipe-card__title';
    title.textContent = video.title || 'Untitled';
    info.appendChild(title);

    const channel = document.createElement('p');
    channel.className = 'swipe-card__channel';
    channel.textContent = video.channel || '';
    info.appendChild(channel);

    if (video.duration) {
      const dur = document.createElement('span');
      dur.className = 'swipe-card__duration';
      dur.textContent = VideoCard.formatDuration(video.duration);
      info.appendChild(dur);
    }

    card.appendChild(info);

    // Overlays (visual feedback)
    const overlayLike = document.createElement('div');
    overlayLike.className = 'swipe-card__overlay swipe-card__overlay--like';
    card.appendChild(overlayLike);

    const overlayNope = document.createElement('div');
    overlayNope.className = 'swipe-card__overlay swipe-card__overlay--nope';
    card.appendChild(overlayNope);

    const overlayLove = document.createElement('div');
    overlayLove.className = 'swipe-card__overlay swipe-card__overlay--love';
    card.appendChild(overlayLove);

    // Stamp labels
    const stampLike = document.createElement('div');
    stampLike.className = 'swipe-card__stamp swipe-card__stamp--like';
    stampLike.textContent = 'YES';
    card.appendChild(stampLike);

    const stampNope = document.createElement('div');
    stampNope.className = 'swipe-card__stamp swipe-card__stamp--nope';
    stampNope.textContent = 'NOPE';
    card.appendChild(stampNope);

    const stampLove = document.createElement('div');
    stampLove.className = 'swipe-card__stamp swipe-card__stamp--love';
    stampLove.textContent = 'LOVE';
    card.appendChild(stampLove);

    return card;
  },

  /** Bind touch/mouse gestures to a card */
  _bindGestures(card) {
    const onStart = (x, y) => {
      if (this._isAnimating) return;
      this._isDragging = true;
      this._startX = x;
      this._startY = y;
      this._currentX = 0;
      this._currentY = 0;
      card.style.transition = 'none';
    };

    const onMove = (x, y) => {
      if (!this._isDragging || this._isAnimating) return;
      this._currentX = x - this._startX;
      this._currentY = y - this._startY;

      const rotation = this._currentX * 0.08;
      card.style.transform = `translate(${this._currentX}px, ${this._currentY}px) rotate(${rotation}deg)`;

      // Visual feedback
      const threshold = 80;
      const rightPct = Math.min(1, Math.max(0, this._currentX / threshold));
      const leftPct = Math.min(1, Math.max(0, -this._currentX / threshold));
      const upPct = Math.min(1, Math.max(0, -this._currentY / threshold));

      const likeOverlay = card.querySelector('.swipe-card__overlay--like');
      const nopeOverlay = card.querySelector('.swipe-card__overlay--nope');
      const loveOverlay = card.querySelector('.swipe-card__overlay--love');
      const likeStamp = card.querySelector('.swipe-card__stamp--like');
      const nopeStamp = card.querySelector('.swipe-card__stamp--nope');
      const loveStamp = card.querySelector('.swipe-card__stamp--love');

      if (likeOverlay) likeOverlay.style.opacity = String(rightPct);
      if (nopeOverlay) nopeOverlay.style.opacity = String(leftPct);
      if (loveOverlay) loveOverlay.style.opacity = String(upPct > 0.3 && Math.abs(this._currentX) < 60 ? upPct : 0);
      if (likeStamp) likeStamp.style.opacity = String(rightPct);
      if (nopeStamp) nopeStamp.style.opacity = String(leftPct);
      if (loveStamp) loveStamp.style.opacity = String(upPct > 0.3 && Math.abs(this._currentX) < 60 ? upPct : 0);
    };

    const onEnd = () => {
      if (!this._isDragging || this._isAnimating) return;
      this._isDragging = false;

      const threshold = 80;
      const upThreshold = 100;

      // Determine action
      if (this._currentX > threshold) {
        this._flyOut(card, 'right', 'interested');
      } else if (this._currentX < -threshold) {
        this._flyOut(card, 'left', 'not_interested');
      } else if (this._currentY < -upThreshold && Math.abs(this._currentX) < 60) {
        this._flyOut(card, 'up', 'love');
      } else {
        // Snap back
        card.style.transition = 'transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)';
        card.style.transform = '';

        // Reset overlays
        card.querySelectorAll('.swipe-card__overlay').forEach(o => { o.style.opacity = '0'; });
        card.querySelectorAll('.swipe-card__stamp').forEach(s => { s.style.opacity = '0'; });
      }
    };

    // Touch events
    card.addEventListener('touchstart', (e) => {
      const t = e.touches[0];
      onStart(t.clientX, t.clientY);
    }, { passive: true });

    card.addEventListener('touchmove', (e) => {
      const t = e.touches[0];
      onMove(t.clientX, t.clientY);
    }, { passive: true });

    card.addEventListener('touchend', () => onEnd());
    card.addEventListener('touchcancel', () => onEnd());

    // Mouse events
    card.addEventListener('mousedown', (e) => {
      onStart(e.clientX, e.clientY);

      const mouseMoveHandler = (ev) => onMove(ev.clientX, ev.clientY);
      const mouseUpHandler = () => {
        onEnd();
        document.removeEventListener('mousemove', mouseMoveHandler);
        document.removeEventListener('mouseup', mouseUpHandler);
      };

      document.addEventListener('mousemove', mouseMoveHandler);
      document.addEventListener('mouseup', mouseUpHandler);
    });
  },

  /** Animate card flying out and process rating */
  _flyOut(card, direction, rating) {
    this._isAnimating = true;

    let tx = 0, ty = 0, rot = 0;
    const flyDist = window.innerWidth + 200;

    switch (direction) {
      case 'right':
        tx = flyDist;
        rot = 30;
        break;
      case 'left':
        tx = -flyDist;
        rot = -30;
        break;
      case 'up':
        ty = -(window.innerHeight + 200);
        // Heart animation for love
        this._showHeartAnimation();
        break;
    }

    card.style.transition = 'transform 0.5s cubic-bezier(0.4, 0.0, 0.2, 1)';
    card.style.transform = `translate(${tx}px, ${ty}px) rotate(${rot}deg)`;

    // Rate the video
    const videoId = card.dataset.videoId;
    if (videoId) {
      API.rateVideo(videoId, rating).catch(() => {});
    }

    // Update counter
    this._rated++;
    this._updateCounter();

    // After animation, remove card and re-render
    setTimeout(() => {
      this._stack.shift();
      this._preloadThumbnails();
      this._renderStack();
      this._isAnimating = false;
    }, 500);
  },

  /** Show a heart burst animation */
  _showHeartAnimation() {
    const stackEl = document.getElementById('swipe-stack');
    if (!stackEl) return;

    const heart = document.createElement('div');
    heart.className = 'heart-burst';
    heart.textContent = '\u2764\uFE0F';
    stackEl.appendChild(heart);

    setTimeout(() => heart.remove(), 900);
  },

  /** Update the session counter */
  _updateCounter() {
    const el = document.getElementById('swipe-counter');
    if (!el) return;

    while (el.firstChild) el.removeChild(el.firstChild);
    const numSpan = document.createElement('span');
    numSpan.textContent = String(this._rated);
    el.appendChild(numSpan);
    el.appendChild(document.createTextNode(` video${this._rated === 1 ? '' : 's'} rated this session`));
  },
};
