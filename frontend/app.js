/**
 * Hachimi Music - Frontend Application
 */

const API_BASE = window.location.port ? `${window.location.origin}/api` : 'http://localhost:8000/api';
let currentTaskId = null;
let pollInterval = null;
let currentProjectId = null;
let projects = [];

// ── Instrument Management ──────────────────────────────────

const instrumentEmojis = {
    piano: '🎹', violin: '🎻', cello: '🎻', viola: '🎻',
    flute: '🎵', clarinet: '🎵', oboe: '🎵', bassoon: '🎵',
    trumpet: '🎺', 'french horn': '🎺', trombone: '🎺', tuba: '🎺',
    'acoustic guitar': '🎸', 'electric guitar': '🎸', 'electric bass': '🎸',
    harp: '🎵', drums: '🥁', saxophone: '🎷', vibraphone: '🎵',
    'string ensemble': '🎻',
};

function getInstruments() {
    const tags = document.querySelectorAll('#instrument-tags .tag');
    return Array.from(tags).map(t => t.dataset.instrument);
}

function addInstrument(name) {
    if (!name) return;
    const existing = getInstruments();
    if (existing.includes(name)) return;

    const emoji = instrumentEmojis[name] || '🎵';
    const tag = document.createElement('span');
    tag.className = 'tag';
    tag.dataset.instrument = name;
    tag.innerHTML = `${emoji} ${name} <button class="tag-remove" onclick="this.parentElement.remove()">×</button>`;
    document.getElementById('instrument-tags').appendChild(tag);
}

// Instrument select handler
document.getElementById('add-instrument').addEventListener('change', function() {
    if (this.value) {
        addInstrument(this.value);
        this.value = '';
    }
});

// Range sliders
document.getElementById('tempo').addEventListener('input', function() {
    document.getElementById('tempo-value').textContent = this.value;
});

document.getElementById('measures').addEventListener('input', function() {
    document.getElementById('measures-value').textContent = this.value;
});

// ── API Calls ──────────────────────────────────────────────

// Style value → select option mapping (for setting the dropdown)
const styleMap = {
    classical: 'classical', pop: 'pop', jazz: 'jazz', rock: 'rock',
    electronic: 'electronic', folk: 'folk', blues: 'blues',
    latin: 'latin', ambient: 'ambient', cinematic: 'cinematic',
};

async function suggestParams() {
    const prompt = document.getElementById('prompt').value.trim();
    if (!prompt) {
        alert('请先输入音乐描述！');
        return;
    }

    const btn = document.getElementById('suggest-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> AI 分析中...';

    try {
        const res = await fetch(`${API_BASE}/suggest-params`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt }),
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || '获取推荐参数失败');
        }
        const params = await res.json();

        // Fill form fields
        if (params.style && styleMap[params.style]) {
            document.getElementById('style').value = params.style;
        }
        if (params.key) {
            const keySelect = document.getElementById('key');
            // Try exact match first
            const option = Array.from(keySelect.options).find(o => o.value === params.key);
            if (option) keySelect.value = params.key;
        }
        if (params.time_signature) {
            const tsSelect = document.getElementById('time-sig');
            const option = Array.from(tsSelect.options).find(o => o.value === params.time_signature);
            if (option) tsSelect.value = params.time_signature;
        }
        if (params.tempo) {
            const tempoSlider = document.getElementById('tempo');
            tempoSlider.value = params.tempo;
            document.getElementById('tempo-value').textContent = params.tempo;
        }
        if (params.measures) {
            const measuresSlider = document.getElementById('measures');
            measuresSlider.value = params.measures;
            document.getElementById('measures-value').textContent = params.measures;
        }
        if (params.instruments && params.instruments.length > 0) {
            // Clear existing instruments
            document.getElementById('instrument-tags').innerHTML = '';
            // Add suggested instruments
            for (const inst of params.instruments) {
                addInstrument(inst);
            }
        }

        btn.innerHTML = '✅ 已填充';
        setTimeout(() => { btn.innerHTML = '✨ AI 推荐参数'; }, 2000);
    } catch (e) {
        alert('推荐失败: ' + e.message);
        btn.innerHTML = '✨ AI 推荐参数';
    } finally {
        btn.disabled = false;
    }
}

async function generateMusic() {
    const prompt = document.getElementById('prompt').value.trim();
    if (!prompt) {
        alert('请输入音乐描述！');
        return;
    }

    const instruments = getInstruments();
    if (instruments.length === 0) {
        alert('请至少选择一种乐器！');
        return;
    }

    const request = {
        name: prompt.slice(0, 50),
        prompt: prompt,
        style: document.getElementById('style').value,
        key: document.getElementById('key').value,
        time_signature: document.getElementById('time-sig').value,
        tempo: parseInt(document.getElementById('tempo').value),
        measures: parseInt(document.getElementById('measures').value),
        instruments: instruments,
        output_format: document.getElementById('format').value,
    };

    // Reset UI
    const btn = document.getElementById('generate-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> 生成中...';

    showResultPanel();
    hideResultSections();
    showProgress('提交中...');

    try {
        // Create project first
        const createRes = await fetch(`${API_BASE}/projects`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(request),
        });
        if (!createRes.ok) {
            const err = await createRes.json();
            throw new Error(err.detail || '创建项目失败');
        }
        const proj = await createRes.json();
        currentProjectId = proj.project.id;

        // Start generation
        const genRes = await fetch(`${API_BASE}/projects/${currentProjectId}/generate`, {
            method: 'POST',
        });
        if (!genRes.ok) {
            const err = await genRes.json();
            throw new Error(err.detail || '启动生成失败');
        }

        // Start polling project status
        startProjectPolling(currentProjectId);
        loadProjectList();

    } catch (e) {
        showError(e.message);
        resetButton();
    }
}

function startPolling(taskId) {
    if (pollInterval) clearInterval(pollInterval);

    const progressMap = {
        pending: 5,
        generating: 25,
        converting: 55,
        rendering: 75,
        postprocessing: 90,
        completed: 100,
    };

    pollInterval = setInterval(async () => {
        try {
            const res = await fetch(`${API_BASE}/status/${taskId}`);
            if (!res.ok) throw new Error('Status check failed');

            const data = await res.json();
            const pct = progressMap[data.status] || 0;
            updateProgress(pct, data.progress_message || data.status);

            if (data.status === 'completed') {
                clearInterval(pollInterval);
                pollInterval = null;
                await showResult(taskId);
                resetButton();
                addToHistory(taskId, data);
            } else if (data.status === 'failed') {
                clearInterval(pollInterval);
                pollInterval = null;
                showError(data.progress_message || 'Generation failed');
                resetButton();
                addToHistory(taskId, data);
            }
        } catch (e) {
            console.error('Polling error:', e);
        }
    }, 2000);
}

// ── Project Polling ────────────────────────────────────────

function startProjectPolling(projectId) {
    if (pollInterval) clearInterval(pollInterval);

    const progressMap = {
        pending: 5, generating: 25, converting: 55,
        rendering: 75, postprocessing: 90, completed: 100,
    };

    pollInterval = setInterval(async () => {
        try {
            const res = await fetch(`${API_BASE}/projects/${projectId}`);
            if (!res.ok) return;
            const data = await res.json();
            const p = data.project;
            const pct = progressMap[p.status] || 0;
            updateProgress(pct, p.checkpoint?.error_message || p.status);

            if (p.status === 'completed') {
                clearInterval(pollInterval);
                pollInterval = null;
                showProjectResult(p);
                resetButton();
                loadProjectList();
            } else if (p.status === 'failed') {
                clearInterval(pollInterval);
                pollInterval = null;
                showError(p.checkpoint?.error_message || '生成失败');
                // Restore previous score/audio if they still exist
                if (p.score) {
                    showProjectResult(p);
                }
                resetButton();
                loadProjectList();
            }
        } catch (e) {
            console.error('Project polling error:', e);
        }
    }, 2000);
}

function showProjectResult(project) {
    if (project.score) {
        // Cache instruments for studio panel
        _currentInstruments = project.score.instruments || [];
        showScore({
            title: project.score.title,
            description: project.score.description,
            key: project.score.key,
            time_signature: project.score.time_signature,
            tempo: project.score.tempo,
            instruments: project.score.instruments,
            abc_notation: project.score.abc_notation,
        });
    }
    if (project.audio_file) {
        const audioUrl = `${API_BASE}/projects/${project.id}/download/audio`;
        setupAudioPlayer(audioUrl);
        document.getElementById('download-link').href = audioUrl;
        document.getElementById('download-midi').href = `${API_BASE}/projects/${project.id}/download/midi`;
    }
    // Show action buttons
    document.getElementById('result-actions').style.display = 'flex';
}

async function showResult(taskId) {
    try {
        // Get score
        const scoreRes = await fetch(`${API_BASE}/score/${taskId}`);
        if (scoreRes.ok) {
            const score = await scoreRes.json();
            showScore(score);
        }

        // Get result
        const resultRes = await fetch(`${API_BASE}/result/${taskId}`);
        if (resultRes.ok) {
            const result = await resultRes.json();
            showAudio(taskId, result);
        }
    } catch (e) {
        console.error('Error loading result:', e);
    }
}

// ── UI Updates ─────────────────────────────────────────────

function showResultPanel() {
    document.getElementById('result-panel').style.display = 'block';
    document.getElementById('result-panel').scrollIntoView({ behavior: 'smooth' });
}

function hideResultSections() {
    document.getElementById('score-section').style.display = 'none';
    document.getElementById('audio-section').style.display = 'none';
    document.getElementById('error-section').style.display = 'none';
    document.getElementById('progress-section').style.display = 'block';
    document.getElementById('playback-controls').style.display = 'none';
    document.getElementById('studio-panel').style.display = 'none';
    document.getElementById('result-actions').style.display = 'none';
    stopPlayback();
}

function showProgress(text) {
    document.getElementById('progress-section').style.display = 'block';
    document.getElementById('progress-text').textContent = text;
    document.getElementById('progress-fill').style.width = '5%';
}

function updateProgress(pct, text) {
    document.getElementById('progress-fill').style.width = pct + '%';
    document.getElementById('progress-text').textContent = text;
}

// ── Score rendering & playback state ───────────────────────

let currentAbc = '';
let audioElement = null;
let timingCallbacks = null;
let isPlaying = false;
let currentAudioUrl = '';

function showScore(score) {
    document.getElementById('score-section').style.display = 'block';
    document.getElementById('score-title').textContent = score.title || 'Untitled';
    document.getElementById('score-description').textContent = score.description || '';

    // Meta tags
    const metaEl = document.getElementById('score-meta');
    const instruments = (score.instruments || []).map(i => i.instrument).join(', ');
    metaEl.innerHTML = `
        <span>🎼 ${score.key}</span>
        <span>⏱ ${score.time_signature}</span>
        <span>♩ ${score.tempo} BPM</span>
        <span>🎹 ${instruments}</span>
    `;

    currentAbc = score.abc_notation || '';

    // Render ABC notation using abcjs with cursor support
    if (currentAbc && typeof ABCJS !== 'undefined') {
        const visualObj = ABCJS.renderAbc('score-render', currentAbc, {
            responsive: 'resize',
            staffwidth: 800,
            paddingtop: 10,
            paddingbottom: 10,
            add_classes: true,
        });

        // Store visualObj for cursor sync
        window._currentVisualObj = visualObj && visualObj[0] ? visualObj[0] : null;
    }
}

function showAudio(taskId, result) {
    // Legacy path — not used for project-based flow
    setupAudioPlayer(`${API_BASE}/download/${taskId}`);
}

function setupAudioPlayer(audioUrl) {
    currentAudioUrl = audioUrl;

    // Show download buttons
    document.getElementById('audio-section').style.display = 'block';
    document.getElementById('progress-section').style.display = 'none';

    // Show playback controls
    document.getElementById('playback-controls').style.display = 'flex';

    // Create or reuse audio element
    if (!audioElement) {
        audioElement = new Audio();
        audioElement.addEventListener('timeupdate', onAudioTimeUpdate);
        audioElement.addEventListener('ended', onAudioEnded);
        audioElement.addEventListener('loadedmetadata', onAudioLoaded);
        audioElement.addEventListener('error', (e) => {
            console.error('Audio load error:', e);
        });
    }

    audioElement.src = audioUrl;
    audioElement.volume = parseInt(document.getElementById('playback-volume').value) / 100;
    audioElement.load();

    // Reset UI
    isPlaying = false;
    document.getElementById('btn-play').textContent = '▶';
    document.getElementById('playback-seek').value = 0;
    document.getElementById('playback-time').textContent = '0:00 / 0:00';

    // Setup timing callbacks for cursor sync
    setupTimingCallbacks();
}

function setupTimingCallbacks() {
    if (timingCallbacks) {
        timingCallbacks.stop();
        timingCallbacks = null;
    }

    if (!window._currentVisualObj) return;

    try {
        timingCallbacks = new ABCJS.TimingCallbacks(window._currentVisualObj, {
            eventCallback: onBeatCallback,
        });
    } catch (e) {
        console.warn('TimingCallbacks not available:', e);
    }
}

function onBeatCallback(ev) {
    if (!ev) {
        // End of piece
        removeScoreCursor();
        return;
    }

    // Highlight the current note/beat on the score
    removeScoreCursor();

    if (ev.elements) {
        ev.elements.forEach(elArray => {
            elArray.forEach(el => {
                if (el.classList) {
                    el.classList.add('abcjs-cursor');
                }
            });
        });
    }
}

function removeScoreCursor() {
    const highlighted = document.querySelectorAll('#score-render .abcjs-cursor');
    highlighted.forEach(el => el.classList.remove('abcjs-cursor'));
}

function onAudioTimeUpdate() {
    if (!audioElement || !audioElement.duration) return;

    const current = audioElement.currentTime;
    const duration = audioElement.duration;
    const pct = (current / duration) * 100;

    document.getElementById('playback-seek').value = pct;
    document.getElementById('playback-time').textContent =
        `${formatTime(current)} / ${formatTime(duration)}`;

    // Sync cursor with audio time
    if (timingCallbacks && isPlaying) {
        try {
            timingCallbacks.setProgress(current / duration);
        } catch (e) {
            // ignore timing errors
        }
    }
}

function onAudioLoaded() {
    const duration = audioElement.duration;
    document.getElementById('playback-time').textContent = `0:00 / ${formatTime(duration)}`;
}

function onAudioEnded() {
    isPlaying = false;
    document.getElementById('btn-play').textContent = '▶';
    removeScoreCursor();
    if (timingCallbacks) {
        try { timingCallbacks.stop(); } catch(e) {}
    }
}

function togglePlayback() {
    if (!audioElement || !currentAudioUrl) return;

    if (isPlaying) {
        audioElement.pause();
        isPlaying = false;
        document.getElementById('btn-play').textContent = '▶';
        if (timingCallbacks) {
            try { timingCallbacks.pause(); } catch(e) {}
        }
    } else {
        audioElement.play().catch(e => console.error('Play failed:', e));
        isPlaying = true;
        document.getElementById('btn-play').textContent = '⏸';
        if (timingCallbacks) {
            try { timingCallbacks.start(); } catch(e) {}
        }
    }
}

function stopPlayback() {
    if (audioElement) {
        audioElement.pause();
        audioElement.currentTime = 0;
    }
    isPlaying = false;
    const btn = document.getElementById('btn-play');
    if (btn) btn.textContent = '▶';
    removeScoreCursor();
    if (timingCallbacks) {
        try { timingCallbacks.stop(); } catch(e) {}
    }
}

function seekPlayback(pct) {
    if (!audioElement || !audioElement.duration) return;
    audioElement.currentTime = (pct / 100) * audioElement.duration;
}

function setPlaybackVolume(val) {
    if (audioElement) {
        audioElement.volume = val / 100;
    }
}

function formatTime(seconds) {
    if (!seconds || isNaN(seconds)) return '0:00';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
}

function showError(message) {
    document.getElementById('error-section').style.display = 'block';
    document.getElementById('error-text').textContent = '❌ ' + message;
    document.getElementById('progress-section').style.display = 'none';
}

function resetButton() {
    const btn = document.getElementById('generate-btn');
    btn.disabled = false;
    btn.innerHTML = '🎵 生成音乐';
}

// ── Project List ───────────────────────────────────────────

async function loadProjectList() {
    try {
        const res = await fetch(`${API_BASE}/projects`);
        if (!res.ok) return;
        const data = await res.json();
        projects = data.projects;
        renderProjectList();
    } catch (e) {
        console.error('Failed to load projects:', e);
    }
}

function renderProjectList() {
    const list = document.getElementById('project-list');
    if (projects.length === 0) {
        list.innerHTML = '<p class="empty-state">暂无项目</p>';
        return;
    }
    const statusLabels = {
        pending: '⏳ 等待', generating: '🔄 生成中', converting: '🔄 转换中',
        rendering: '🔄 渲染中', postprocessing: '🔄 后处理', completed: '✅ 完成', failed: '❌ 失败',
    };
    list.innerHTML = projects.map(p => `
        <div class="project-item ${p.id === currentProjectId ? 'active' : ''}" onclick="openProject('${p.id}')">
            <div class="proj-name">${p.title || p.name}</div>
            <div class="proj-meta">
                <span>${statusLabels[p.status] || p.status}</span>
                <span>${new Date(p.updated_at).toLocaleDateString()}</span>
                <button class="proj-delete" onclick="event.stopPropagation();deleteProject('${p.id}')" title="删除">🗑️</button>
            </div>
        </div>
    `).join('');
}

async function openProject(projectId) {
    currentProjectId = projectId;
    renderProjectList();
    try {
        const res = await fetch(`${API_BASE}/projects/${projectId}`);
        if (!res.ok) throw new Error('加载失败');
        const data = await res.json();
        const p = data.project;

        showResultPanel();
        hideResultSections();

        if (p.status === 'completed') {
            showProjectResult(p);
        } else if (p.status === 'failed') {
            showError(p.checkpoint?.error_message || '生成失败');
            document.getElementById('result-actions').style.display = 'flex';
        } else if (['generating', 'converting', 'rendering', 'postprocessing'].includes(p.status)) {
            showProgress(p.status + '...');
            startProjectPolling(projectId);
        } else {
            document.getElementById('result-panel').style.display = 'none';
        }
    } catch (e) {
        showError(e.message);
    }
}

function showCreateProject() {
    // Just scroll to input panel
    document.querySelector('.input-panel').scrollIntoView({ behavior: 'smooth' });
    document.getElementById('prompt').focus();
}

async function deleteProject(projectId) {
    if (!confirm('确定删除此项目？')) return;
    try {
        await fetch(`${API_BASE}/projects/${projectId}`, { method: 'DELETE' });
        if (projectId === currentProjectId) {
            currentProjectId = null;
            document.getElementById('result-panel').style.display = 'none';
        }
        loadProjectList();
    } catch (e) {
        alert('删除失败: ' + e.message);
    }
}

// ── Settings ───────────────────────────────────────────────

function toggleSettings() {
    const panel = document.getElementById('settings-panel');
    const isHidden = panel.style.display === 'none';
    panel.style.display = isHidden ? 'block' : 'none';
    if (isHidden) {
        loadSettings();
        panel.scrollIntoView({ behavior: 'smooth' });
    }
}

function toggleApiKeyVisibility() {
    const input = document.getElementById('cfg-apikey');
    input.type = input.type === 'password' ? 'text' : 'password';
}

async function loadSettings() {
    try {
        const res = await fetch(`${API_BASE}/settings`);
        if (!res.ok) return;
        const data = await res.json();

        // AI settings
        document.getElementById('cfg-baseurl').value = data.ai.base_url;
        document.getElementById('cfg-temperature').value = data.ai.temperature;
        document.getElementById('cfg-temperature-value').textContent = data.ai.temperature;

        // Set model — keep current select value or add it as option
        const modelSelect = document.getElementById('cfg-model');
        const currentModel = data.ai.model;
        let found = false;
        for (const opt of modelSelect.options) {
            if (opt.value === currentModel) { opt.selected = true; found = true; break; }
        }
        if (!found && currentModel) {
            const opt = document.createElement('option');
            opt.value = currentModel;
            opt.textContent = currentModel;
            opt.selected = true;
            modelSelect.prepend(opt);
        }

        const hint = document.getElementById('cfg-apikey-hint');
        if (data.ai.api_key_set) {
            hint.textContent = `✅ 已配置: ${data.ai.api_key_masked}`;
            hint.className = 'field-hint success';
            document.getElementById('cfg-apikey').placeholder = '已设置，留空保持不变';
        } else {
            hint.textContent = '⚠️ 未配置 API Key';
            hint.className = 'field-hint';
        }

        // Synthesis
        const sfSelect = document.getElementById('cfg-soundfont');
        sfSelect.innerHTML = '';
        if (data.synthesis.available_soundfonts.length > 0) {
            data.synthesis.available_soundfonts.forEach(sf => {
                const opt = document.createElement('option');
                opt.value = 'soundfonts/' + sf;
                opt.textContent = sf;
                if (data.synthesis.soundfont.endsWith(sf)) opt.selected = true;
                sfSelect.appendChild(opt);
            });
        } else {
            const opt = document.createElement('option');
            opt.value = '';
            opt.textContent = '⚠️ 未找到 SoundFont 文件';
            sfSelect.appendChild(opt);
        }
        document.getElementById('cfg-samplerate').value = data.synthesis.sample_rate;

        // Postprocess
        document.getElementById('cfg-reverb').checked = data.postprocess.reverb;
        document.getElementById('cfg-reverb-size').value = data.postprocess.reverb_room_size;
        document.getElementById('cfg-reverb-size-value').textContent = data.postprocess.reverb_room_size;
        document.getElementById('cfg-normalize').checked = data.postprocess.normalize;

    } catch (e) {
        console.error('Failed to load settings:', e);
    }
}

async function saveSettings() {
    const apiKey = document.getElementById('cfg-apikey').value.trim();

    const payload = {
        ai: {
            base_url: document.getElementById('cfg-baseurl').value.trim(),
            model: document.getElementById('cfg-model').value,
            temperature: parseFloat(document.getElementById('cfg-temperature').value),
        },
        synthesis: {
            soundfont: document.getElementById('cfg-soundfont').value,
            sample_rate: parseInt(document.getElementById('cfg-samplerate').value),
        },
        postprocess: {
            reverb: document.getElementById('cfg-reverb').checked,
            reverb_room_size: parseFloat(document.getElementById('cfg-reverb-size').value),
            normalize: document.getElementById('cfg-normalize').checked,
        },
    };

    // Only send API key if user typed something
    if (apiKey) {
        payload.ai.api_key = apiKey;
    }

    try {
        const res = await fetch(`${API_BASE}/settings`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        if (!res.ok) throw new Error('保存失败');

        const status = document.getElementById('save-status');
        status.textContent = '✅ 设置已保存';
        status.classList.add('visible');
        setTimeout(() => status.classList.remove('visible'), 3000);

        // Clear API key input and refresh hint
        document.getElementById('cfg-apikey').value = '';
        await loadSettings();

    } catch (e) {
        const status = document.getElementById('save-status');
        status.textContent = '❌ ' + e.message;
        status.style.color = 'var(--error)';
        status.classList.add('visible');
        setTimeout(() => {
            status.classList.remove('visible');
            status.style.color = '';
        }, 3000);
    }
}

// Range slider live updates for settings
document.getElementById('cfg-temperature').addEventListener('input', function() {
    document.getElementById('cfg-temperature-value').textContent = this.value;
});

document.getElementById('cfg-reverb-size').addEventListener('input', function() {
    document.getElementById('cfg-reverb-size-value').textContent = this.value;
});

async function fetchModels() {
    const btn = document.getElementById('btn-fetch-models');
    const hint = document.getElementById('cfg-model-hint');
    const select = document.getElementById('cfg-model');
    const prevModel = select.value;

    btn.disabled = true;
    btn.textContent = '⏳';
    hint.textContent = '正在获取模型列表...';
    hint.className = 'field-hint';

    try {
        const res = await fetch(`${API_BASE}/models`);
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || '请求失败');
        }

        const data = await res.json();
        select.innerHTML = '';

        if (data.models.length === 0) {
            const opt = document.createElement('option');
            opt.value = '';
            opt.textContent = '⚠️ 未找到可用模型';
            select.appendChild(opt);
            hint.textContent = 'API 返回了空的模型列表';
            return;
        }

        data.models.forEach(m => {
            const opt = document.createElement('option');
            opt.value = m.id;
            opt.textContent = m.owned_by ? `${m.id}  (${m.owned_by})` : m.id;
            if (m.id === prevModel) opt.selected = true;
            select.appendChild(opt);
        });

        hint.textContent = `✅ 已加载 ${data.count} 个模型`;
        hint.className = 'field-hint success';

    } catch (e) {
        hint.textContent = '❌ ' + e.message;
        hint.className = 'field-hint';
        // Restore previous option
        if (select.options.length === 0 && prevModel) {
            const opt = document.createElement('option');
            opt.value = prevModel;
            opt.textContent = prevModel;
            select.appendChild(opt);
        }
    } finally {
        btn.disabled = false;
        btn.textContent = '🔄';
    }
}

// ── Retry / Studio / Setup ─────────────────────────────────

async function retryProject() {
    if (!currentProjectId) { alert('请先选择一个项目'); return; }
    try {
        const res = await fetch(`${API_BASE}/projects/${currentProjectId}/retry`, { method: 'POST' });
        if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
        showResultPanel();
        hideResultSections();
        showProgress('从断点重试中...');
        startProjectPolling(currentProjectId);
    } catch (e) {
        alert('重试失败: ' + e.message);
    }
}

// ── Studio Panel ───────────────────────────────────────────

let _currentInstruments = []; // cached from score

function toggleStudio() {
    if (!currentProjectId) { alert('请先选择一个项目'); return; }
    const panel = document.getElementById('studio-panel');
    const isHidden = panel.style.display === 'none';
    panel.style.display = isHidden ? 'block' : 'none';
    if (isHidden) {
        populateStudio();
        panel.scrollIntoView({ behavior: 'smooth' });
    }
}

function populateStudio() {
    // Populate tempo slider from current ABC
    const tempoMatch = currentAbc.match(/Q:\s*\d+\/\d+=(\d+)/);
    const currentTempo = tempoMatch ? parseInt(tempoMatch[1]) : 120;
    const slider = document.getElementById('studio-tempo');
    slider.value = currentTempo;
    document.getElementById('studio-tempo-val').textContent = currentTempo;

    // Populate instrument tracks
    renderTrackList();

    // Load ABC into advanced editor
    document.getElementById('abc-editor').value = currentAbc;
    previewScoreEdit();
}

function renderTrackList() {
    const container = document.getElementById('studio-tracks');
    if (!_currentInstruments || _currentInstruments.length === 0) {
        container.innerHTML = '<p class="empty-state">暂无乐器信息</p>';
        return;
    }
    container.innerHTML = _currentInstruments.map((inst, i) => {
        const emoji = instrumentEmojis[inst.instrument?.toLowerCase()] || '🎵';
        const detail = inst.voice_name ? `Voice ${inst.voice_id} · ${inst.voice_name}` : `Voice ${inst.voice_id}`;
        return `
            <div class="track-card">
                <span class="track-icon">${emoji}</span>
                <div class="track-info">
                    <div class="track-name">${inst.instrument || 'Unknown'}</div>
                    <div class="track-detail">${detail}${inst.gm_program != null ? ' · GM ' + inst.gm_program : ''}</div>
                </div>
                <div class="track-actions">
                    <button class="track-btn"
                        onclick="quickRefine('请只修改 ${inst.instrument} (Voice ${inst.voice_id}) 的部分，让它更有表现力，增加一些装饰音或变奏')">
                        ✏️ AI 改编
                    </button>
                </div>
            </div>`;
    }).join('');
}

// ── Quick Refine (presets & per-instrument) ─────────────────

async function quickRefine(prompt) {
    if (!currentProjectId) return;
    // Disable all preset buttons to prevent spam
    const btns = document.querySelectorAll('.preset-btn, .track-btn');
    btns.forEach(b => b.disabled = true);

    try {
        const res = await fetch(`${API_BASE}/projects/${currentProjectId}/refine`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ modification_prompt: prompt, section: null }),
        });
        if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
        document.getElementById('studio-panel').style.display = 'none';
        showResultPanel();
        hideResultSections();
        showProgress('AI 修改中...');
        startProjectPolling(currentProjectId);
    } catch (e) {
        alert('修改失败: ' + e.message);
        btns.forEach(b => b.disabled = false);
    }
}

// ── Tempo Adjustment (deterministic) ────────────────────────

function studioAdjustTempo(delta) {
    const slider = document.getElementById('studio-tempo');
    let val = parseInt(slider.value) + delta;
    val = Math.max(30, Math.min(300, val));
    slider.value = val;
    document.getElementById('studio-tempo-val').textContent = val;
}

function applyTempoChange() {
    if (!currentProjectId || !currentAbc) return;
    const newTempo = parseInt(document.getElementById('studio-tempo').value);

    // Replace Q: line in ABC
    let modified = currentAbc;
    const qMatch = modified.match(/Q:\s*(\d+\/\d+=)\d+/);
    if (qMatch) {
        modified = modified.replace(/Q:\s*\d+\/\d+=\d+/, `Q:${qMatch[1]}${newTempo}`);
    } else {
        // Try simpler Q:120 format
        const qSimple = modified.match(/Q:\s*\d+/);
        if (qSimple) {
            modified = modified.replace(/Q:\s*\d+/, `Q:${newTempo}`);
        } else {
            // Add Q: after first M: line
            modified = modified.replace(/(M:\s*\S+)/, `$1\nQ:1/4=${newTempo}`);
        }
    }

    // Save via score edit endpoint
    saveModifiedAbc(modified, `速度调整: ${newTempo} BPM`);
}

async function saveModifiedAbc(abc, message) {
    try {
        const res = await fetch(`${API_BASE}/projects/${currentProjectId}/score`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ abc_notation: abc, message: message || null }),
        });
        if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
        document.getElementById('studio-panel').style.display = 'none';
        showResultPanel();
        hideResultSections();
        showProgress('重新生成音频...');
        startProjectPolling(currentProjectId);
    } catch (e) {
        alert('保存失败: ' + e.message);
    }
}

// ── Studio Free Text Refine ─────────────────────────────────

async function studioRefine() {
    if (!currentProjectId) return;
    const prompt = document.getElementById('studio-refine-prompt').value.trim();
    if (!prompt) { alert('请输入修改描述'); return; }
    const section = document.getElementById('studio-refine-section').value.trim() || null;

    try {
        const res = await fetch(`${API_BASE}/projects/${currentProjectId}/refine`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ modification_prompt: prompt, section }),
        });
        if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
        document.getElementById('studio-panel').style.display = 'none';
        showResultPanel();
        hideResultSections();
        showProgress('AI 修改中...');
        startProjectPolling(currentProjectId);
    } catch (e) {
        alert('修改失败: ' + e.message);
    }
}

// ── AI Audio Feedback ───────────────────────────────────────

async function requestAudioFeedback() {
    if (!currentProjectId) { alert('请先选择一个项目'); return; }

    const btn = document.getElementById('btn-audio-feedback');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> AI 正在听音分析...';
    document.getElementById('feedback-result').style.display = 'none';

    try {
        const res = await fetch(`${API_BASE}/projects/${currentProjectId}/audio-feedback`, {
            method: 'POST',
        });
        if (!res.ok) {
            const e = await res.json();
            throw new Error(e.detail || '请求失败');
        }
        const feedback = await res.json();
        renderFeedback(feedback);
    } catch (e) {
        alert('AI 听音失败: ' + e.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '🎧 AI 听音诊断';
    }
}

function renderFeedback(feedback) {
    const container = document.getElementById('feedback-result');
    container.style.display = 'block';

    // Analysis mode badge
    const isAudio = feedback.audio_analyzed === true;
    const modeBadge = isAudio
        ? '<span class="mode-badge mode-audio">🎧 已听音分析</span>'
        : '<span class="mode-badge mode-score">📄 仅谱面分析</span>';

    // Rating with stars
    const rating = feedback.overall_rating || 5;
    const stars = '★'.repeat(Math.round(rating / 2)) + '☆'.repeat(5 - Math.round(rating / 2));
    document.getElementById('feedback-rating').innerHTML =
        `${modeBadge} <strong>${rating}/10</strong> ${stars}`;

    let comment = feedback.overall_comment || '';
    if (!isAudio) {
        comment += ' （提示：当前模型不支持音频输入，仅根据谱面推断。使用 Gemini 2.5/3 系列可启用真正的听音分析）';
    }
    document.getElementById('feedback-comment').textContent = comment;

    // Suggestions
    const suggestionsEl = document.getElementById('feedback-suggestions');
    const suggestions = feedback.suggestions || [];

    if (suggestions.length === 0) {
        suggestionsEl.innerHTML = '<p class="empty-state">没有具体改进建议</p>';
        return;
    }

    const severityEmoji = {
        critical: '🔴', major: '🟠', minor: '🔵', suggestion: '💡',
    };

    suggestionsEl.innerHTML = suggestions.map((s, i) => `
        <div class="suggestion-card severity-${s.severity || 'suggestion'}">
            <span title="${s.severity || 'suggestion'}">${severityEmoji[s.severity] || '💡'}</span>
            <div class="suggestion-body">
                <div class="suggestion-location">${s.location || ''}</div>
                <div class="suggestion-desc">${s.description || ''}</div>
            </div>
            <button class="suggestion-apply" onclick="applySuggestion(${i})" title="让 AI 自动修改">
                ⚡ 应用
            </button>
        </div>
    `).join('');

    // Store suggestions for later use
    window._feedbackSuggestions = suggestions;
}

async function applySuggestion(index) {
    const suggestions = window._feedbackSuggestions;
    if (!suggestions || !suggestions[index]) return;

    const s = suggestions[index];
    const prompt = s.auto_fix_prompt || s.description;

    // Use quickRefine to apply the suggestion
    await quickRefine(prompt);
}

// ── Version History ─────────────────────────────────────────

let _currentVersionId = null;       // tracks which version is "active"
let _branchFromVersionId = null;    // used by branch dialog

function toggleVersionPanel() {
    if (!currentProjectId) { alert('请先选择一个项目'); return; }
    const panel = document.getElementById('version-panel');
    const isHidden = panel.style.display === 'none';
    panel.style.display = isHidden ? 'block' : 'none';
    if (isHidden) {
        loadVersions();
        panel.scrollIntoView({ behavior: 'smooth' });
    }
}

async function loadVersions() {
    if (!currentProjectId) return;
    const container = document.getElementById('version-list');
    container.innerHTML = '<p class="empty-state">加载中...</p>';
    try {
        const res = await fetch(`${API_BASE}/projects/${currentProjectId}/versions`);
        if (!res.ok) throw new Error('获取版本列表失败');
        const data = await res.json();
        _currentVersionId = data.current_version_id;
        container.innerHTML = renderVersionGraph(data.versions, _currentVersionId);
    } catch (e) {
        container.innerHTML = `<p class="empty-state" style="color:var(--error)">加载失败: ${e.message}</p>`;
    }
}

/**
 * Build an SVG git-graph + version entry list.
 *
 * Layout:
 *   [SVG rail (fixed-width)]  [version cards (flex:1)]
 *
 * Each row is NODE_H px tall; SVG circle centers match row midpoints.
 */
function renderVersionGraph(versions, currentVersionId) {
    if (!versions || versions.length === 0) {
        return '<p class="empty-state">还没有版本记录。<br>生成音乐后版本历史会自动保存在这里。</p>';
    }

    const NODE_H = 88;
    const LANE_W = 26;
    const NODE_R = 7;
    const BRANCH_COLORS = ['#7c5bf5', '#22c55e', '#f59e0b', '#38bdf8', '#ef4444', '#ec4899'];

    // Assign lanes + colors, in chronological order (oldest first)
    const branchInfo = {};
    let nextLane = 0;
    [...versions].reverse().forEach(v => {
        if (!branchInfo[v.branch_name]) {
            branchInfo[v.branch_name] = {
                color: BRANCH_COLORS[nextLane % BRANCH_COLORS.length],
                lane: nextLane++,
            };
        }
    });

    const laneCount = Math.max(1, Object.keys(branchInfo).length);
    const svgW = laneCount * LANE_W + 16;
    const svgH = versions.length * NODE_H;

    // Index map: id → row index (newest = 0)
    const idxMap = {};
    versions.forEach((v, i) => { idxMap[v.id] = i; });

    // ── SVG edges ──────────────────────────────────────────
    let svgEdges = '';
    versions.forEach((v, i) => {
        if (!v.parent_id || idxMap[v.parent_id] === undefined) return;
        const pIdx = idxMap[v.parent_id];
        const cb = branchInfo[v.branch_name];
        const pb = branchInfo[versions[pIdx].branch_name];
        const x1 = cb.lane * LANE_W + 13;
        const y1 = i * NODE_H + NODE_H / 2;
        const x2 = pb.lane * LANE_W + 13;
        const y2 = pIdx * NODE_H + NODE_H / 2;

        if (x1 === x2) {
            svgEdges += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"
                stroke="${cb.color}" stroke-width="2" opacity="0.55"/>`;
        } else {
            const mx = x1, my = (y1 + y2) / 2;
            svgEdges += `<path d="M${x1} ${y1} C${mx} ${my} ${x2} ${my} ${x2} ${y2}"
                stroke="${cb.color}" stroke-width="2" fill="none" opacity="0.55"/>`;
        }
    });

    // ── SVG nodes ──────────────────────────────────────────
    let svgNodes = '';
    versions.forEach((v, i) => {
        const b = branchInfo[v.branch_name];
        const cx = b.lane * LANE_W + 13;
        const cy = i * NODE_H + NODE_H / 2;
        const isCurr = v.id === currentVersionId;
        if (isCurr) {
            svgNodes += `<circle cx="${cx}" cy="${cy}" r="${NODE_R + 4}"
                fill="${b.color}22" stroke="${b.color}" stroke-width="1.5"/>`;
        }
        svgNodes += `<circle cx="${cx}" cy="${cy}" r="${NODE_R}"
            fill="${b.color}" stroke="${isCurr ? '#fff' : 'transparent'}" stroke-width="2.5"/>`;
        if (isCurr) {
            svgNodes += `<circle cx="${cx}" cy="${cy}" r="3" fill="#fff"/>`;
        }
    });

    const svg = `<svg width="${svgW}" height="${svgH}" class="vg-svg"
        style="min-width:${svgW}px">${svgEdges}${svgNodes}</svg>`;

    // Source label map
    const srcLabel = {
        initial:     '🌱 初始生成',
        refine:      '🤖 AI修改',
        manual_edit: '✏️ 手动编辑',
        tempo_change:'⏱ 速度调整',
        branch:      '🌿 分叉',
        manual:      '📸 快照',
    };

    // ── Version entry rows ──────────────────────────────────
    const entries = versions.map((v, i) => {
        const b = branchInfo[v.branch_name];
        const isCurr = v.id === currentVersionId;
        const dt = new Date(v.created_at);
        const dateStr = `${(dt.getMonth()+1).toString().padStart(2,'0')}-${dt.getDate().toString().padStart(2,'0')} ${dt.getHours().toString().padStart(2,'0')}:${dt.getMinutes().toString().padStart(2,'0')}`;

        return `
        <div class="vg-entry${isCurr ? ' vg-entry-current' : ''}" style="height:${NODE_H}px">
            <div class="vg-entry-body">
                <div class="vg-entry-row1">
                    <span class="vg-branch-tag" style="--bc:${b.color}">${v.branch_name}</span>
                    <span class="vg-vnum">v${v.version_number}</span>
                    <span class="vg-msg">${escHtml(v.message)}</span>
                    ${isCurr ? '<span class="vg-curr-badge">● 当前</span>' : ''}
                </div>
                <div class="vg-entry-row2">
                    <span class="vg-src-tag">${srcLabel[v.source] || v.source}</span>
                    <span class="vg-date">${dateStr}</span>
                </div>
            </div>
            <div class="vg-entry-acts">
                <button class="btn btn-sm${isCurr ? ' btn-secondary' : ' btn-primary'}"
                    onclick="${isCurr ? '' : `checkoutVersion('${v.id}')`}"
                    ${isCurr ? 'disabled' : ''}>
                    ${isCurr ? '当前' : '⏪ 回退'}
                </button>
                <button class="btn btn-sm btn-secondary vg-btn-branch"
                    onclick="showBranchDialog('${v.id}', ${v.version_number})"
                    title="从此版本创建分支">🌿</button>
                <button class="btn btn-sm btn-danger vg-btn-del"
                    onclick="deleteVersion('${v.id}')"
                    ${isCurr ? 'disabled' : ''}
                    title="删除此版本">🗑</button>
            </div>
        </div>`;
    }).join('');

    return `
    <div class="vg-wrap">
        <div class="vg-rail">${svg}</div>
        <div class="vg-entries">${entries}</div>
    </div>`;
}

function escHtml(s) {
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

async function saveVersionSnapshot() {
    if (!currentProjectId) return;
    const msg = prompt('为此快照写一个说明（可留空）：', '');
    if (msg === null) return; // cancelled
    try {
        const res = await fetch(`${API_BASE}/projects/${currentProjectId}/versions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: msg || '手动快照', source: 'manual' }),
        });
        if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
        await loadVersions();
    } catch (e) {
        alert('保存失败: ' + e.message);
    }
}

async function checkoutVersion(versionId) {
    if (!currentProjectId) return;
    if (!confirm('确定回退到此版本？当前音频将重新生成。')) return;

    try {
        const res = await fetch(
            `${API_BASE}/projects/${currentProjectId}/versions/${versionId}/checkout`,
            { method: 'POST' }
        );
        if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
        // Close version panel, show progress
        document.getElementById('version-panel').style.display = 'none';
        showResultPanel();
        hideResultSections();
        showProgress('正在回退并重新生成音频...');
        startProjectPolling(currentProjectId);
    } catch (e) {
        alert('回退失败: ' + e.message);
    }
}

function showBranchDialog(versionId, versionNum) {
    _branchFromVersionId = versionId;
    document.getElementById('branch-dialog-source').textContent =
        `从 v${versionNum} 分叉的新分支将独立演变，不影响原始历史。`;
    document.getElementById('branch-name-input').value = '';
    document.getElementById('branch-dialog').style.display = 'flex';
    document.getElementById('branch-name-input').focus();
}

function closeBranchDialog() {
    document.getElementById('branch-dialog').style.display = 'none';
    _branchFromVersionId = null;
}

async function confirmCreateBranch() {
    if (!_branchFromVersionId || !currentProjectId) return;
    const name = document.getElementById('branch-name-input').value.trim();
    if (!name) { alert('请输入分支名称'); return; }

    try {
        const res = await fetch(
            `${API_BASE}/projects/${currentProjectId}/versions/${_branchFromVersionId}/branch`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ branch_name: name }),
            }
        );
        if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
        closeBranchDialog();
        await loadVersions();
    } catch (e) {
        alert('创建分支失败: ' + e.message);
    }
}

async function deleteVersion(versionId) {
    if (!confirm('确定删除此版本？如果有子版本则无法删除。')) return;
    try {
        const res = await fetch(
            `${API_BASE}/projects/${currentProjectId}/versions/${versionId}`,
            { method: 'DELETE' }
        );
        if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
        await loadVersions();
    } catch (e) {
        alert('删除失败: ' + e.message);
    }
}

// Also refresh versions panel when generation/refine completes
const _origShowProjectResult = showProjectResult;
function showProjectResult(project) {
    _origShowProjectResult(project);
    // Reload version history if the version panel is visible
    const vp = document.getElementById('version-panel');
    if (vp && vp.style.display !== 'none') {
        loadVersions();
    }
}
// ── Advanced ABC Editor ─────────────────────────────────────

let editorDebounce = null;

function onEditorInput() {
    if (editorDebounce) clearTimeout(editorDebounce);
    editorDebounce = setTimeout(previewScoreEdit, 300);
}

function previewScoreEdit() {
    const abc = document.getElementById('abc-editor').value;
    if (abc && typeof ABCJS !== 'undefined') {
        ABCJS.renderAbc('editor-score-render', abc, {
            responsive: 'resize',
            staffwidth: 700,
            paddingtop: 10,
            paddingbottom: 10,
        });
    }
}

async function saveScoreEdit() {
    if (!currentProjectId) return;
    const abc = document.getElementById('abc-editor').value.trim();
    if (!abc) { alert('谱子不能为空'); return; }
    await saveModifiedAbc(abc);
}

function showSetupPanel() {
    const panel = document.getElementById('setup-panel');
    const isHidden = panel.style.display === 'none';
    panel.style.display = isHidden ? 'block' : 'none';
    if (isHidden) {
        checkFluidSynth();
        loadSoundFonts();
        panel.scrollIntoView({ behavior: 'smooth' });
    }
}

async function checkFluidSynth() {
    try {
        const res = await fetch(`${API_BASE}/setup/fluidsynth`);
        const data = await res.json();
        const el = document.getElementById('fluidsynth-status');
        const btn = document.getElementById('btn-install-fluidsynth');
        if (data.installed) {
            el.innerHTML = `<span style="color:var(--success)">✅ 已安装</span> (${data.path})`;
            btn.style.display = 'none';
        } else {
            el.innerHTML = '<span style="color:var(--error)">❌ 未安装</span>';
            btn.style.display = 'inline-flex';
        }
    } catch (e) {
        document.getElementById('fluidsynth-status').textContent = '检测失败';
    }
}

async function installFluidSynth() {
    const btn = document.getElementById('btn-install-fluidsynth');
    btn.disabled = true;
    btn.textContent = '安装中...';
    try {
        const res = await fetch(`${API_BASE}/setup/fluidsynth`, { method: 'POST' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail);
        alert(data.message);
        checkFluidSynth();
    } catch (e) {
        alert('安装失败: ' + e.message);
    } finally {
        btn.disabled = false;
        btn.textContent = '安装 FluidSynth';
    }
}

async function loadSoundFonts() {
    try {
        const res = await fetch(`${API_BASE}/setup/soundfonts`);
        const data = await res.json();
        const el = document.getElementById('soundfont-list');
        if (data.soundfonts.length === 0) {
            el.innerHTML = '<p style="color:var(--text-dim)">未找到 SoundFont 文件</p>';
        } else {
            el.innerHTML = data.soundfonts.map(sf =>
                `<div style="padding:4px 0;font-size:0.9rem;">${sf.name} (${sf.size_mb} MB)</div>`
            ).join('');
        }
    } catch (e) {
        document.getElementById('soundfont-list').textContent = '加载失败';
    }
}

async function downloadSoundFont(choice) {
    if (!confirm(`下载 ${choice}？文件较大，可能需要几分钟。`)) return;
    try {
        const res = await fetch(`${API_BASE}/setup/soundfonts`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ choice }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail);
        alert(data.message);
        loadSoundFonts();
    } catch (e) {
        alert('下载失败: ' + e.message);
    }
}

// ── Init ───────────────────────────────────────────────────

loadProjectList();
console.log('🎵 Hachimi Music Frontend loaded');
