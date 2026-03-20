const API = '';

async function loadSystemStatus() {
    try {
        const resp = await fetch(`${API}/api/system/status`);
        const data = await resp.json();
        document.getElementById('system-status').textContent =
            `v${data.version} | Uptime: ${data.uptime} | Auth: ${data.auth_status} | Queue: ${data.download_queue_size}`;
    } catch (e) {
        document.getElementById('system-status').textContent = 'Status unavailable';
    }
}

function createStatCards(data) {
    const container = document.getElementById('cache-stats');
    container.innerHTML = '';

    const totalCard = document.createElement('div');
    totalCard.className = 'stat-card';
    totalCard.innerHTML = '<div class="label">Total Size</div>';
    const totalVal = document.createElement('div');
    totalVal.className = 'value';
    totalVal.textContent = data.total_size_human;
    totalCard.appendChild(totalVal);

    const countCard = document.createElement('div');
    countCard.className = 'stat-card';
    countCard.innerHTML = '<div class="label">Videos Cached</div>';
    const countVal = document.createElement('div');
    countVal.className = 'value';
    countVal.textContent = data.video_count;
    countCard.appendChild(countVal);

    container.appendChild(totalCard);
    container.appendChild(countCard);
}

function createVideoItem(v) {
    const item = document.createElement('div');
    item.className = 'video-item';

    const info = document.createElement('div');
    info.className = 'info';

    const title = document.createElement('div');
    title.className = 'title';
    title.textContent = v.title;

    const meta = document.createElement('div');
    meta.className = 'meta';
    meta.textContent = `${v.file_size_human} | ${v.cache_status}`;

    info.appendChild(title);
    info.appendChild(meta);

    const btn = document.createElement('button');
    btn.className = 'delete-btn';
    btn.textContent = 'Delete';
    btn.addEventListener('click', () => deleteVideo(v.id));

    item.appendChild(info);
    item.appendChild(btn);
    return item;
}

async function loadCacheStatus() {
    try {
        const resp = await fetch(`${API}/api/cache/status`);
        const data = await resp.json();

        createStatCards(data);

        const videosContainer = document.getElementById('cache-videos');
        videosContainer.innerHTML = '';
        data.videos.forEach(v => videosContainer.appendChild(createVideoItem(v)));
    } catch (e) {
        document.getElementById('cache-stats').textContent = 'Cache status unavailable';
    }
}

async function deleteVideo(videoId) {
    if (!confirm('Delete this cached video?')) return;
    await fetch(`${API}/api/cache/${videoId}`, { method: 'DELETE' });
    loadCacheStatus();
}

function createRuleItem(r, i) {
    const item = document.createElement('div');
    item.className = 'rule-item';

    const info = document.createElement('div');
    const strong = document.createElement('strong');
    strong.textContent = r.type;
    info.appendChild(strong);
    info.appendChild(document.createTextNode(
        `: ${r.channel_id || r.playlist_id || 'unknown'} (max ${r.max_videos || 5} videos, ${r.quality || 'auto'})`
    ));

    const btn = document.createElement('button');
    btn.className = 'delete-btn';
    btn.textContent = 'Remove';
    btn.addEventListener('click', () => deleteRule(i));

    item.appendChild(info);
    item.appendChild(btn);
    return item;
}

async function loadRules() {
    try {
        const resp = await fetch(`${API}/api/precache/rules`);
        const data = await resp.json();
        const rules = data.precache_rules || [];

        const container = document.getElementById('rules-list');
        container.innerHTML = '';

        if (rules.length === 0) {
            const p = document.createElement('p');
            p.style.color = '#888';
            p.textContent = 'No pre-cache rules configured.';
            container.appendChild(p);
        } else {
            rules.forEach((r, i) => container.appendChild(createRuleItem(r, i)));
        }
    } catch (e) {
        document.getElementById('rules-list').textContent = 'Rules unavailable';
    }
}

async function deleteRule(index) {
    const resp = await fetch(`${API}/api/precache/rules`);
    const data = await resp.json();
    const rules = data.precache_rules || [];
    rules.splice(index, 1);
    await fetch(`${API}/api/precache/rules`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ precache_rules: rules })
    });
    loadRules();
}

function addRule() {
    const channelId = prompt('Enter YouTube Channel ID:');
    if (!channelId) return;
    const maxVideos = parseInt(prompt('Max videos to cache (default 5):') || '5');

    fetch(`${API}/api/precache/rules`).then(r => r.json()).then(async data => {
        const rules = data.precache_rules || [];
        rules.push({ type: 'channel', channel_id: channelId, max_videos: maxVideos, quality: 'auto', trigger: 'on_upload' });
        await fetch(`${API}/api/precache/rules`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ precache_rules: rules })
        });
        loadRules();
    });
}

// Load everything on page load
loadSystemStatus();
loadCacheStatus();
loadRules();

// Auto-refresh every 30 seconds
setInterval(() => { loadSystemStatus(); loadCacheStatus(); }, 30000);
