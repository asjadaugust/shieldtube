# ShieldTube Chrome Extension — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chrome extension that adds a download button to YouTube video pages, sending the video ID to the ShieldTube backend for server-side download.

**Architecture:** Manifest V3 Chrome extension with a content script injected on youtube.com. The content script adds a download button next to YouTube's existing action buttons (like/dislike/share). Clicking it calls the ShieldTube backend API. A popup page handles initial setup (backend URL + API secret).

**Tech Stack:** Vanilla JS, Chrome Extension Manifest V3, fetch API.

---

## File Structure

```
shieldtube-chrome-ext/
├── manifest.json           # Extension manifest V3
├── popup.html              # Setup/status popup
├── popup.js                # Popup logic (save config to chrome.storage)
├── popup.css               # Popup styling (NVIDIA theme)
├── content.js              # Injected into youtube.com — adds download button
├── content.css             # Styles for the injected button
├── background.js           # Service worker — handles API calls from content script
└── icons/
    ├── icon-16.png
    ├── icon-48.png
    └── icon-128.png
```

---

## Task 1: Extension Scaffold + Manifest

**Files:** Create all files in `shieldtube-chrome-ext/`

- [ ] **Step 1: Create manifest.json**

```json
{
  "manifest_version": 3,
  "name": "ShieldTube Downloader",
  "version": "1.0.0",
  "description": "Download YouTube videos to your ShieldTube server",
  "permissions": ["storage", "activeTab"],
  "host_permissions": ["https://*.youtube.com/*"],
  "background": {
    "service_worker": "background.js"
  },
  "content_scripts": [{
    "matches": ["https://www.youtube.com/*"],
    "js": ["content.js"],
    "css": ["content.css"],
    "run_at": "document_idle"
  }],
  "action": {
    "default_popup": "popup.html",
    "default_icon": {
      "16": "icons/icon-16.png",
      "48": "icons/icon-48.png",
      "128": "icons/icon-128.png"
    }
  },
  "icons": {
    "16": "icons/icon-16.png",
    "48": "icons/icon-48.png",
    "128": "icons/icon-128.png"
  }
}
```

- [ ] **Step 2: Generate icons from shield_mask_1.png**

Resize existing `shield_mask_1.png` to 16x16, 48x48, 128x128.

- [ ] **Step 3: Commit scaffold**

---

## Task 2: Popup (Setup Page)

- [ ] **Step 1: Create popup.html + popup.css + popup.js**

Simple form: Backend URL, API Secret, Save button. Reads/writes `chrome.storage.sync`. Shows connection status (green/red dot). NVIDIA dark theme (#121212 bg, #76B900 accents).

- [ ] **Step 2: Commit**

---

## Task 3: Background Service Worker

- [ ] **Step 1: Create background.js**

Listens for messages from content script. On `DOWNLOAD` message type:
- Reads `backendUrl` and `apiSecret` from `chrome.storage.sync`
- POSTs to `{backendUrl}/api/download/enqueue` with `X-ShieldTube-Secret` header
- Returns response to content script via `sendResponse`
- Uses `return true` for async response pattern

- [ ] **Step 2: Commit**

---

## Task 4: Content Script (YouTube Injection)

- [ ] **Step 1: Create content.js**

Observes YouTube's SPA navigation (URL changes via `yt-navigate-finish` event). On each video page (`/watch?v=`):
1. Extract video ID from URL params
2. Wait for YouTube's action buttons to load (MutationObserver on `#top-level-buttons-computed`)
3. Inject a "ShieldTube" download button using safe DOM APIs (createElement, textContent — no innerHTML)
4. On click: send message to background worker via `chrome.runtime.sendMessage`, update button text to show status

Use MutationObserver + `yt-navigate-finish` event to handle YouTube's SPA routing.

- [ ] **Step 2: Create content.css**

Style the button to match YouTube's action button style but with NVIDIA green (#76B900) accent. Dark background, rounded, consistent with YouTube's UI.

- [ ] **Step 3: Commit**

---

## Task 5: Test + Package

- [ ] **Step 1: Load unpacked extension in Chrome**

`chrome://extensions` → Developer mode → Load unpacked → select `shieldtube-chrome-ext/`

- [ ] **Step 2: Test flow**

1. Click extension icon → enter backend URL + secret → save
2. Navigate to a YouTube video
3. See ShieldTube download button next to like/share
4. Click it → shows queuing status → shows success/failure
5. Check server: video appears in download queue

- [ ] **Step 3: Final commit**

---

## Verification

1. Extension loads without errors in `chrome://extensions`
2. Button appears on YouTube video pages
3. Button survives YouTube SPA navigation (watch → watch)
4. Download request reaches ShieldTube backend
5. Video appears in Downloads tab of phone app / PWA
