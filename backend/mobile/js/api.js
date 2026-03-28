/* ================================================
   ShieldTube API Client
   ================================================ */

const API = {
  baseUrl: '',
  secret: '',

  /** Load stored config from localStorage */
  loadConfig() {
    this.baseUrl = (localStorage.getItem('shieldtube_url') || '').replace(/\/+$/, '');
    this.secret = localStorage.getItem('shieldtube_secret') || '';
    return !!(this.baseUrl && this.secret);
  },

  /** Persist config to localStorage */
  saveConfig(url, secret) {
    const cleaned = url.replace(/\/+$/, '');
    localStorage.setItem('shieldtube_url', cleaned);
    localStorage.setItem('shieldtube_secret', secret);
    this.baseUrl = cleaned;
    this.secret = secret;
  },

  /** Clear stored config */
  clearConfig() {
    localStorage.removeItem('shieldtube_url');
    localStorage.removeItem('shieldtube_secret');
    this.baseUrl = '';
    this.secret = '';
  },

  /**
   * Core fetch wrapper with auth and error handling.
   * @param {string} path - API path (e.g., /api/feed/home)
   * @param {object} options - fetch options
   * @returns {Promise<any>} parsed JSON response
   */
  async request(path, options = {}) {
    const url = `${this.baseUrl}${path}`;

    const headers = {
      'X-ShieldTube-Secret': this.secret,
      'Accept': 'application/json',
      ...(options.headers || {}),
    };

    if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(options.body);
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), options.timeout || 15000);

    try {
      const response = await fetch(url, {
        ...options,
        headers,
        signal: controller.signal,
      });

      if (!response.ok) {
        const body = await response.text().catch(() => '');
        throw new ApiError(response.status, body || response.statusText, path);
      }

      const contentType = response.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        return await response.json();
      }
      return await response.text();
    } catch (err) {
      if (err instanceof ApiError) throw err;
      if (err.name === 'AbortError') {
        throw new ApiError(0, 'Request timed out', path);
      }
      throw new ApiError(0, err.message || 'Network error', path);
    } finally {
      clearTimeout(timeout);
    }
  },

  /**
   * Fetch a feed by type.
   * @param {'home'|'subscriptions'|'watch-later'|'recommended'|'history'} type
   */
  async getFeed(type) {
    const pathMap = {
      'home': '/api/feed/home',
      'subscriptions': '/api/feed/subscriptions',
      'history': '/api/feed/history',
      'watch-later': '/api/feed/watch-later',
      'recommended': '/api/feed/recommended',
    };
    const path = pathMap[type] || `/api/feed/${type}`;
    return this.request(path, { timeout: 30000 });
  },

  /**
   * Search videos.
   * @param {string} query
   */
  async search(query) {
    return this.request(`/api/search?q=${encodeURIComponent(query)}`);
  },

  /**
   * Get video metadata.
   * @param {string} id - YouTube video ID
   */
  async getVideoMeta(id) {
    return this.request(`/api/video/${encodeURIComponent(id)}/meta`);
  },

  /**
   * Get SponsorBlock segments.
   * @param {string} id - YouTube video ID
   */
  async getSponsorSegments(id) {
    return this.request(`/api/sponsorblock/${encodeURIComponent(id)}`);
  },

  /**
   * Cast video to Shield TV.
   * @param {string} id - YouTube video ID
   */
  async castToShield(id) {
    return this.request('/api/cast', {
      method: 'POST',
      body: { video_id: id },
    });
  },

  /**
   * Rate a video for training recommendations.
   * @param {string} id
   * @param {'interested'|'not_interested'|'love'} rating
   */
  async rateVideo(id, rating) {
    return this.request(`/api/video/${encodeURIComponent(id)}/rate`, {
      method: 'POST',
      body: { rating },
    });
  },

  /**
   * Report playback progress.
   * @param {string} id
   * @param {object} data - { position, duration, status }
   */
  async reportProgress(id, data) {
    return this.request(`/api/video/${encodeURIComponent(id)}/progress`, {
      method: 'POST',
      body: data,
    });
  },

  /** Get recommendation engine status */
  async getRecommendationStatus() {
    return this.request('/api/recommendations/status');
  },

  /** Get cache disk usage */
  async getCacheStatus() {
    return this.request('/api/cache/status');
  },

  /** Get current bandwidth setting */
  async getBandwidth() {
    return this.request('/api/download/bandwidth');
  },

  /**
   * Set bandwidth limit.
   * @param {number} rateMbps
   */
  async setBandwidth(rateMbps) {
    return this.request('/api/download/bandwidth', {
      method: 'PUT',
      body: { rate_mbps: rateMbps },
    });
  },

  /** Enqueue a single video for download. */
  async enqueueDownload(videoId, quality = 'auto') {
    return this.request('/api/download/enqueue', {
      method: 'POST',
      body: { video_id: videoId, quality },
    });
  },

  /** Get active downloads and queue state. */
  async getActiveDownloads() {
    return this.request('/api/download/active');
  },

  /** Get download library (all cached videos). */
  async getDownloadLibrary() {
    return this.request('/api/download/library');
  },

  /**
   * Test server connection.
   * @returns {Promise<boolean>}
   */
  async testConnection() {
    try {
      await this.request('/api/auth/status', { timeout: 8000 });
      return true;
    } catch {
      return false;
    }
  },
};


/** Custom error class for API errors */
class ApiError extends Error {
  constructor(status, message, path) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.path = path;
  }
}
