/* ================================================
   ShieldTube Mobile App — Main Application Logic
   ================================================ */

const App = {
  _currentTab: 'home',
  _currentFeedType: 'home',
  _feedCache: {},
  _pullStartY: 0,
  _isPulling: false,

  /** Initialize the app */
  async init() {
    const configured = API.loadConfig();

    if (!configured) {
      this._showSetup();
    } else {
      this._hideSetup();
      this._initRouting();
      this._navigateToHash();
    }

    this._bindSetupForm();
    this._bindNavigation();

    // Listen for hash changes
    window.addEventListener('hashchange', () => this._navigateToHash());
  },

  // ---- Setup ----

  _showSetup() {
    const modal = document.getElementById('setup-modal');
    if (modal) modal.hidden = false;
  },

  _hideSetup() {
    const modal = document.getElementById('setup-modal');
    if (modal) modal.hidden = true;
  },

  _bindSetupForm() {
    const form = document.getElementById('setup-form');
    const testBtn = document.getElementById('setup-test-btn');
    const saveBtn = document.getElementById('setup-save-btn');
    const urlInput = document.getElementById('setup-url');
    const secretInput = document.getElementById('setup-secret');
    const statusEl = document.getElementById('setup-status');

    if (!form) return;

    testBtn?.addEventListener('click', async () => {
      const url = urlInput.value.trim();
      const secret = secretInput.value.trim();

      if (!url || !secret) {
        this._showSetupStatus('Please fill in both fields', false);
        return;
      }

      testBtn.disabled = true;
      testBtn.textContent = 'Testing...';

      // Temporarily set config for testing
      API.saveConfig(url, secret);
      const ok = await API.testConnection();

      testBtn.disabled = false;
      testBtn.textContent = 'Test Connection';

      if (ok) {
        this._showSetupStatus('Connected successfully!', true);
        saveBtn.disabled = false;
      } else {
        this._showSetupStatus('Could not connect. Check URL and secret.', false);
        saveBtn.disabled = true;
        API.clearConfig();
      }
    });

    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const url = urlInput.value.trim();
      const secret = secretInput.value.trim();

      if (!url || !secret) return;

      API.saveConfig(url, secret);
      this._hideSetup();
      this._navigateToHash();
    });
  },

  _showSetupStatus(message, success) {
    const el = document.getElementById('setup-status');
    if (!el) return;
    el.hidden = false;
    el.textContent = message;
    el.className = `setup-status ${success ? 'setup-status--success' : 'setup-status--error'}`;
  },

  // ---- Navigation ----

  _bindNavigation() {
    const nav = document.getElementById('bottom-nav');
    if (!nav) return;

    nav.addEventListener('click', (e) => {
      const item = e.target.closest('.bottom-nav__item');
      if (!item) return;
      e.preventDefault();
      const tab = item.dataset.tab;
      if (tab) window.location.hash = tab;
    });
  },

  _initRouting() {
    if (!window.location.hash || window.location.hash === '#') {
      window.location.hash = 'home';
    }
  },

  _navigateToHash() {
    const hash = (window.location.hash || '#home').slice(1);
    const tab = ['home', 'search', 'train', 'settings'].includes(hash) ? hash : 'home';

    this._currentTab = tab;
    this._updateActiveNav(tab);
    this._renderScreen(tab);
  },

  _updateActiveNav(tab) {
    document.querySelectorAll('.bottom-nav__item').forEach(item => {
      item.classList.toggle('active', item.dataset.tab === tab);
    });
  },

  // ---- Screen Rendering ----

  async _renderScreen(tab) {
    const content = document.getElementById('content');
    if (!content) return;

    // Clear content
    while (content.firstChild) content.removeChild(content.firstChild);

    switch (tab) {
      case 'home':
        await this._renderHomeScreen(content);
        break;
      case 'search':
        this._renderSearchScreen(content);
        break;
      case 'train':
        await this._renderTrainScreen(content);
        break;
      case 'settings':
        await this._renderSettingsScreen(content);
        break;
    }
  },

  // ---- Home Screen ----

  async _renderHomeScreen(content) {
    const wrapper = document.createElement('div');
    wrapper.className = 'screen-enter';

    // Tab bar
    const feedTabs = [
      { id: 'recommended', label: 'For You' },
      { id: 'home', label: 'Home' },
      { id: 'subscriptions', label: 'Subscriptions' },
      { id: 'history', label: 'History' },
    ];

    const tabBar = Tabs.render(feedTabs, this._currentFeedType, (tabId) => {
      this._currentFeedType = tabId;
      this._loadFeed(tabId, feedContainer);
    });
    wrapper.appendChild(tabBar);

    // Pull-to-refresh indicator
    const pullIndicator = document.createElement('div');
    pullIndicator.className = 'pull-indicator';
    pullIndicator.id = 'pull-indicator';
    const pullSpinner = document.createElement('div');
    pullSpinner.className = 'pull-indicator__spinner';
    pullIndicator.appendChild(pullSpinner);
    wrapper.appendChild(pullIndicator);

    // Feed container
    const feedContainer = document.createElement('div');
    feedContainer.id = 'feed-container';
    wrapper.appendChild(feedContainer);

    content.appendChild(wrapper);

    // Bind pull-to-refresh
    this._bindPullToRefresh(content, feedContainer);

    // Load initial feed
    await this._loadFeed(this._currentFeedType, feedContainer);
  },

  async _loadFeed(type, container) {
    // Show skeleton
    while (container.firstChild) container.removeChild(container.firstChild);
    container.appendChild(Skeleton.render(6));

    try {
      // Check cache first
      const cached = this._feedCache[type];
      if (cached && Date.now() - cached.timestamp < 60000) {
        Feed.render(cached.data, container);
        return;
      }

      const response = await API.getFeed(type);
      const videos = response?.videos || response || [];

      // Cache it
      this._feedCache[type] = { data: videos, timestamp: Date.now() };

      Feed.render(videos, container);
    } catch (err) {
      while (container.firstChild) container.removeChild(container.firstChild);

      const errDiv = document.createElement('div');
      errDiv.className = 'empty-state';

      const title = document.createElement('h3');
      title.className = 'empty-state__title';
      title.textContent = 'Could not load feed';
      errDiv.appendChild(title);

      const text = document.createElement('p');
      text.className = 'empty-state__text';
      text.textContent = err.message || 'Check your connection and try again.';
      errDiv.appendChild(text);

      container.appendChild(errDiv);
    }
  },

  _bindPullToRefresh(scrollContainer, feedContainer) {
    let startY = 0;
    let pulling = false;

    scrollContainer.addEventListener('touchstart', (e) => {
      if (scrollContainer.scrollTop <= 0) {
        startY = e.touches[0].clientY;
        pulling = true;
      }
    }, { passive: true });

    scrollContainer.addEventListener('touchmove', (e) => {
      if (!pulling) return;
      const dy = e.touches[0].clientY - startY;
      const indicator = document.getElementById('pull-indicator');
      if (dy > 10 && scrollContainer.scrollTop <= 0 && indicator) {
        indicator.classList.add('active');
      }
    }, { passive: true });

    scrollContainer.addEventListener('touchend', async () => {
      const indicator = document.getElementById('pull-indicator');
      if (indicator?.classList.contains('active')) {
        // Clear cache and reload
        delete this._feedCache[this._currentFeedType];
        await this._loadFeed(this._currentFeedType, feedContainer);
        indicator.classList.remove('active');
        Toast.show('Feed refreshed');
      }
      pulling = false;
    });
  },

  // ---- Search Screen ----

  _renderSearchScreen(content) {
    const wrapper = document.createElement('div');
    wrapper.className = 'screen-enter';

    // Search bar
    const searchBar = document.createElement('div');
    searchBar.className = 'search-bar';

    const inner = document.createElement('div');
    inner.className = 'search-bar__inner';

    const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    icon.setAttribute('class', 'search-bar__icon');
    icon.setAttribute('viewBox', '0 0 24 24');
    icon.setAttribute('fill', 'currentColor');
    const iconPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    iconPath.setAttribute('d', 'M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z');
    icon.appendChild(iconPath);
    inner.appendChild(icon);

    const input = document.createElement('input');
    input.className = 'search-bar__input';
    input.type = 'search';
    input.placeholder = 'Search videos...';
    input.setAttribute('autocomplete', 'off');
    inner.appendChild(input);

    const clearBtn = document.createElement('button');
    clearBtn.className = 'search-bar__clear';
    clearBtn.setAttribute('aria-label', 'Clear search');

    const clearSvg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    clearSvg.setAttribute('viewBox', '0 0 24 24');
    clearSvg.setAttribute('fill', 'currentColor');
    clearSvg.setAttribute('width', '20');
    clearSvg.setAttribute('height', '20');
    const clearPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    clearPath.setAttribute('d', 'M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z');
    clearSvg.appendChild(clearPath);
    clearBtn.appendChild(clearSvg);
    inner.appendChild(clearBtn);

    searchBar.appendChild(inner);
    wrapper.appendChild(searchBar);

    // Results container
    const results = document.createElement('div');
    results.id = 'search-results';
    wrapper.appendChild(results);

    content.appendChild(wrapper);

    // Search logic
    let searchTimeout = null;

    input.addEventListener('input', () => {
      const query = input.value.trim();
      clearBtn.classList.toggle('visible', query.length > 0);

      clearTimeout(searchTimeout);
      if (query.length >= 2) {
        searchTimeout = setTimeout(() => this._performSearch(query, results), 400);
      } else {
        while (results.firstChild) results.removeChild(results.firstChild);
      }
    });

    clearBtn.addEventListener('click', () => {
      input.value = '';
      clearBtn.classList.remove('visible');
      while (results.firstChild) results.removeChild(results.firstChild);
      input.focus();
    });

    // Auto-focus
    setTimeout(() => input.focus(), 300);
  },

  async _performSearch(query, container) {
    while (container.firstChild) container.removeChild(container.firstChild);
    container.appendChild(Skeleton.render(4));

    try {
      const response = await API.search(query);
      const videos = response?.videos || response || [];
      Feed.render(videos, container);
    } catch (err) {
      while (container.firstChild) container.removeChild(container.firstChild);

      const errDiv = document.createElement('div');
      errDiv.className = 'empty-state';

      const title = document.createElement('h3');
      title.className = 'empty-state__title';
      title.textContent = 'Search failed';
      errDiv.appendChild(title);

      const text = document.createElement('p');
      text.className = 'empty-state__text';
      text.textContent = err.message || 'Please try again.';
      errDiv.appendChild(text);

      container.appendChild(errDiv);
    }
  },

  // ---- Train Screen ----

  async _renderTrainScreen(content) {
    await SwipeTrainer.render(content);
  },

  // ---- Settings Screen ----

  async _renderSettingsScreen(content) {
    const wrapper = document.createElement('div');
    wrapper.className = 'settings-screen screen-enter';

    // Page header
    const header = document.createElement('div');
    header.className = 'page-header';
    const headerTitle = document.createElement('h1');
    headerTitle.className = 'page-header__title';
    headerTitle.textContent = 'Settings';
    header.appendChild(headerTitle);
    wrapper.appendChild(header);

    // --- Connection Section ---
    const connSection = document.createElement('div');
    connSection.className = 'settings-section';
    const connTitle = document.createElement('h3');
    connTitle.className = 'settings-section__title';
    connTitle.textContent = 'Connection';
    connSection.appendChild(connTitle);

    const connItem = document.createElement('div');
    connItem.className = 'settings-item';
    const connLabel = document.createElement('div');
    const connName = document.createElement('div');
    connName.className = 'settings-item__label';
    connName.textContent = 'Backend';
    connLabel.appendChild(connName);
    const connSub = document.createElement('div');
    connSub.className = 'settings-item__sublabel';
    connSub.textContent = API.baseUrl || 'Not configured';
    connLabel.appendChild(connSub);
    connItem.appendChild(connLabel);

    const connStatus = document.createElement('div');
    connStatus.className = 'settings-item__value';
    connStatus.id = 'settings-conn-status';
    connStatus.textContent = 'Checking...';
    connItem.appendChild(connStatus);
    connSection.appendChild(connItem);

    wrapper.appendChild(connSection);

    // --- Recommendations Section ---
    const recSection = document.createElement('div');
    recSection.className = 'settings-section';
    const recTitle = document.createElement('h3');
    recTitle.className = 'settings-section__title';
    recTitle.textContent = 'Recommendations';
    recSection.appendChild(recTitle);

    const recItem = document.createElement('div');
    recItem.className = 'settings-item';
    const recLabel = document.createElement('div');
    recLabel.className = 'settings-item__label';
    recLabel.textContent = 'Training Status';
    recItem.appendChild(recLabel);
    const recValue = document.createElement('div');
    recValue.className = 'settings-item__value';
    recValue.id = 'settings-rec-status';
    recValue.textContent = 'Loading...';
    recItem.appendChild(recValue);
    recSection.appendChild(recItem);

    wrapper.appendChild(recSection);

    // --- Cache Section ---
    const cacheSection = document.createElement('div');
    cacheSection.className = 'settings-section';
    const cacheTitle = document.createElement('h3');
    cacheTitle.className = 'settings-section__title';
    cacheTitle.textContent = 'Cache';
    cacheSection.appendChild(cacheTitle);

    const cacheItem = document.createElement('div');
    cacheItem.className = 'settings-item';
    const cacheLabel = document.createElement('div');
    cacheLabel.className = 'settings-item__label';
    cacheLabel.textContent = 'Disk Usage';
    cacheItem.appendChild(cacheLabel);
    const cacheValue = document.createElement('div');
    cacheValue.className = 'settings-item__value';
    cacheValue.id = 'settings-cache-status';
    cacheValue.textContent = 'Loading...';
    cacheItem.appendChild(cacheValue);
    cacheSection.appendChild(cacheItem);

    wrapper.appendChild(cacheSection);

    // --- Bandwidth Section ---
    const bwSection = document.createElement('div');
    bwSection.className = 'settings-section';
    const bwTitle = document.createElement('h3');
    bwTitle.className = 'settings-section__title';
    bwTitle.textContent = 'Bandwidth';
    bwSection.appendChild(bwTitle);

    const bwItem = document.createElement('div');
    bwItem.className = 'settings-item settings-item--column';

    const bwRow = document.createElement('div');
    bwRow.style.display = 'flex';
    bwRow.style.justifyContent = 'space-between';
    bwRow.style.alignItems = 'center';
    bwRow.style.width = '100%';

    const bwLabel = document.createElement('div');
    bwLabel.className = 'settings-item__label';
    bwLabel.textContent = 'Download Limit';
    bwRow.appendChild(bwLabel);

    const bwValue = document.createElement('div');
    bwValue.className = 'settings-item__value';
    bwValue.id = 'settings-bw-value';
    bwValue.textContent = '-- Mbps';
    bwRow.appendChild(bwValue);

    bwItem.appendChild(bwRow);

    const bwRange = document.createElement('input');
    bwRange.type = 'range';
    bwRange.className = 'settings-range';
    bwRange.id = 'settings-bw-range';
    bwRange.min = '1';
    bwRange.max = '100';
    bwRange.value = '50';
    bwItem.appendChild(bwRange);

    bwSection.appendChild(bwItem);
    wrapper.appendChild(bwSection);

    // --- About Section ---
    const aboutSection = document.createElement('div');
    aboutSection.className = 'settings-section';
    const aboutTitle = document.createElement('h3');
    aboutTitle.className = 'settings-section__title';
    aboutTitle.textContent = 'About';
    aboutSection.appendChild(aboutTitle);

    const aboutItem = document.createElement('div');
    aboutItem.className = 'settings-item';
    const aboutLabel = document.createElement('div');
    aboutLabel.className = 'settings-item__label';
    aboutLabel.textContent = 'ShieldTube Mobile';
    aboutItem.appendChild(aboutLabel);
    const aboutValue = document.createElement('div');
    aboutValue.className = 'settings-item__value';
    aboutValue.textContent = 'v1.0.0';
    aboutItem.appendChild(aboutValue);
    aboutSection.appendChild(aboutItem);

    wrapper.appendChild(aboutSection);

    // --- Disconnect Button ---
    const disconnectBtn = document.createElement('button');
    disconnectBtn.className = 'btn btn--danger';
    disconnectBtn.textContent = 'Disconnect';
    disconnectBtn.style.marginTop = 'var(--space-4)';
    disconnectBtn.addEventListener('click', () => {
      API.clearConfig();
      this._feedCache = {};
      this._showSetup();
    });
    wrapper.appendChild(disconnectBtn);

    content.appendChild(wrapper);

    // Async data loading
    this._loadSettingsData(bwRange);
  },

  async _loadSettingsData(bwRange) {
    // Connection test
    API.testConnection().then(ok => {
      const el = document.getElementById('settings-conn-status');
      if (!el) return;
      while (el.firstChild) el.removeChild(el.firstChild);

      const dot = document.createElement('span');
      dot.className = `connection-dot ${ok ? 'connection-dot--online' : 'connection-dot--offline'}`;
      el.appendChild(dot);
      el.appendChild(document.createTextNode(ok ? 'Online' : 'Offline'));
    });

    // Recommendations
    API.getRecommendationStatus().then(data => {
      const el = document.getElementById('settings-rec-status');
      if (el) el.textContent = data?.status || data?.videos_rated
        ? `${data.videos_rated || 0} rated`
        : 'Not available';
    }).catch(() => {
      const el = document.getElementById('settings-rec-status');
      if (el) el.textContent = 'Unavailable';
    });

    // Cache
    API.getCacheStatus().then(data => {
      const el = document.getElementById('settings-cache-status');
      if (el) {
        const used = data?.used_gb ?? data?.used ?? 0;
        const total = data?.total_gb ?? data?.total ?? 0;
        el.textContent = `${Number(used).toFixed(1)} / ${Number(total).toFixed(0)} GB`;
      }
    }).catch(() => {
      const el = document.getElementById('settings-cache-status');
      if (el) el.textContent = 'Unavailable';
    });

    // Bandwidth
    API.getBandwidth().then(data => {
      const rate = data?.rate_mbps ?? data?.rate ?? 50;
      const el = document.getElementById('settings-bw-value');
      if (el) el.textContent = `${rate} Mbps`;
      if (bwRange) bwRange.value = String(rate);
    }).catch(() => {});

    // Bandwidth change handler
    if (bwRange) {
      let bwTimeout = null;
      bwRange.addEventListener('input', () => {
        const val = Number(bwRange.value);
        const el = document.getElementById('settings-bw-value');
        if (el) el.textContent = `${val} Mbps`;

        clearTimeout(bwTimeout);
        bwTimeout = setTimeout(async () => {
          try {
            await API.setBandwidth(val);
            Toast.show(`Bandwidth set to ${val} Mbps`);
          } catch {
            Toast.show('Failed to set bandwidth', 3000, 'error');
          }
        }, 500);
      });
    }
  },
};


// ---- Boot ----
document.addEventListener('DOMContentLoaded', () => App.init());
