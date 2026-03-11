/**
 * EvacuAI Frontend — Simulation Controller
 */

import { GeminiClient } from './gemini-client.js';

// ── State ──────────────────────────────────────────────────────────────
let client = null;
let isConnected = false;
let simStarted = false;
let simPaused = false;
let simComplete = false;

// ── DOM ────────────────────────────────────────────────────────────────
const connStatus    = document.getElementById('conn-status');
const btnConnect    = document.getElementById('btn-connect');
const btnApply      = document.getElementById('btn-apply');
const btnStart      = document.getElementById('btn-start');
const btnPause      = document.getElementById('btn-pause');
const btnReset      = document.getElementById('btn-reset');
const btnRandomize  = document.getElementById('btn-randomize');

const slBuildings   = document.getElementById('sl-buildings');
const slExits       = document.getElementById('sl-exits');
const slPop         = document.getElementById('sl-pop');
const slHw          = document.getElementById('sl-hw');
const valBuildings  = document.getElementById('val-buildings');
const valExits      = document.getElementById('val-exits');
const valPop        = document.getElementById('val-pop');
const valHw         = document.getElementById('val-hw');

const simCanvas     = document.getElementById('sim-canvas');
const simPlaceholder= document.getElementById('sim-placeholder');
const mapsCanvas    = document.getElementById('maps-canvas');
const mapsPlaceholder = document.getElementById('maps-placeholder');
const decisionsLog  = document.getElementById('decisions-log');

const statEvac      = document.getElementById('stat-evac');
const statPct       = document.getElementById('stat-pct');
const statTime      = document.getElementById('stat-time');
const statTransit   = document.getElementById('stat-transit');
const statHw        = document.getElementById('stat-hw');
const progressFill  = document.getElementById('evac-progress-fill');

const aiText        = document.getElementById('ai-text');
const aiSend        = document.getElementById('ai-send');

// ── Slider bindings ────────────────────────────────────────────────────
function bindSlider(slider, label) {
    label.textContent = slider.value;
    slider.addEventListener('input', () => { label.textContent = slider.value; });
}
bindSlider(slBuildings, valBuildings);
bindSlider(slExits, valExits);
bindSlider(slPop, valPop);
bindSlider(slHw, valHw);

// ── Config helpers ─────────────────────────────────────────────────────
function getConfig() {
    return {
        buildings:   parseInt(slBuildings.value),
        exits:       parseInt(slExits.value),
        avg_pop:     parseInt(slPop.value),
        highway_out: parseInt(slHw.value),
    };
}

function applyRandom() {
    slBuildings.value = randInt(2, 10);
    slExits.value     = randInt(2, 6);
    slPop.value       = randInt(2, 20) * 10;  // 20-200 step 10
    slHw.value        = randInt(1, 20) * 5;   // 5-100 step 5
    [slBuildings, slExits, slPop, slHw].forEach(sl => sl.dispatchEvent(new Event('input')));
}

function randInt(min, max) {
    return Math.floor(Math.random() * (max - min + 1)) + min;
}

// ── Connection ─────────────────────────────────────────────────────────
function connect() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host  = location.hostname || 'localhost';
    const port  = location.port || '8080';
    const url   = `${proto}//${host}:${port}/ws`;

    client = new GeminiClient(url);

    client.on('connected',    onConnected);
    client.on('disconnected', onDisconnected);
    client.on('error',        onError);
    client.on('status',       onStatus);
    client.on('sim_frame',    onSimFrame);
    client.on('maps_frame',   onMapsFrame);
    client.on('sim_state',    onSimState);
    client.on('decision',     onDecision);
    client.on('action',       onAction);
    client.on('alert',        onAlert);

    setStatus('Connecting…');
    client.connect();
}

function disconnect() {
    client?.disconnect();
    client = null;
    isConnected = false;
    simStarted = false;
    simPaused = false;
    updateButtons();
}

// ── Event handlers ─────────────────────────────────────────────────────
function onConnected() {
    isConnected = true;
    setStatus('Connected', 'ok');
    addCard('system', 'Connected to EvacuAI backend. Apply config to initialize simulation.');
    updateButtons();
    btnConnect.textContent = 'Disconnect';
    btnConnect.className = 'btn-danger';
}

function onDisconnected() {
    isConnected = false;
    simStarted = false;
    simPaused = false;
    setStatus('Disconnected', 'err');
    updateButtons();
    btnConnect.textContent = 'Connect';
    btnConnect.className = 'btn-primary';
}

function onError(err) {
    setStatus('Error', 'err');
    addCard('alert', `Connection error: ${err?.message || JSON.stringify(err)}`);
}

function onStatus(data) {
    if (data?.connected) {
        addCard('system', `Gemini Live API ready — model: ${data.model}`);
    }
}

function onSimFrame(b64) {
    simPlaceholder.style.display = 'none';
    drawToCanvas(simCanvas, b64);
}

function onMapsFrame(b64) {
    if (mapsPlaceholder) mapsPlaceholder.style.display = 'none';
    drawToCanvas(mapsCanvas, b64);
}

function drawToCanvas(canvas, b64) {
    const img = new Image();
    img.onload = () => {
        canvas.width  = img.naturalWidth;
        canvas.height = img.naturalHeight;
        canvas.getContext('2d').drawImage(img, 0, 0);
    };
    img.src = 'data:image/jpeg;base64,' + b64;
}

function onSimState(state) {
    if (!state?.stats) return;
    const s = state.stats;

    statEvac.textContent    = `${s.evacuated} / ${s.total}`;
    statPct.textContent     = `${s.percent_complete}%`;
    statTime.textContent    = `${s.elapsed_seconds}s`;
    if (statTransit) statTransit.textContent = `${s.in_transit ?? '—'} ppl`;

    const hw = state.highway || {};
    statHw.textContent = `${hw.congestion || '—'} (Q:${hw.queue ?? '—'})`;
    statHw.className = 'stat-value ' + congestionClass(hw.congestion);

    progressFill.style.width = s.percent_complete + '%';
    progressFill.style.background =
        s.percent_complete > 80 ? 'var(--success)' :
        s.percent_complete > 40 ? 'var(--accent)' : 'var(--warning)';

    // Detect completion
    if (!state.running && simStarted && s.percent_complete >= 100) {
        simStarted = false;
        simComplete = true;
        updateButtons();
    }
}

function onDecision(data) {
    if (data?.text) {
        addCard('decision', `🤖 ${data.text}`);
    }
}

function onAction(data) {
    if (!data?.tool) return;
    const tool = data.tool;
    const args = data.args || {};
    const result = data.result || {};

    let msg = '';
    if (tool === 'control_exit') {
        const icon = args.action === 'open' ? '🟢' : '🔴';
        msg = `${icon} ${args.action?.toUpperCase()} ${args.exit_id} — ${args.reason || ''}`;
    } else if (tool === 'control_highway') {
        msg = `🛣 Highway: ${args.action} ${args.capacity ? `→ ${args.capacity}/s` : ''} — ${args.reason || ''}`;
    } else if (tool === 'redirect_building') {
        msg = `↗ Redirect ${args.building_id} → ${args.exit_id} — ${args.reason || ''}`;
    } else if (tool === 'get_status') {
        msg = `📊 Status check: ${result.percent_complete ?? '?'}% evacuated`;
    } else {
        msg = `⚙ ${tool}(${JSON.stringify(args)})`;
    }

    if (result?.error) msg += ` ⚠ ${result.error}`;
    addCard('action', msg);
}

function onAlert(data) {
    if (data?.message) {
        addCard('alert', `⚠ ${data.message}`);
    }
}

// ── Button handlers ────────────────────────────────────────────────────
btnConnect.addEventListener('click', () => {
    if (isConnected) disconnect();
    else connect();
});

btnRandomize.addEventListener('click', applyRandom);

btnApply.addEventListener('click', () => {
    if (!isConnected || !client) return;
    const cfg = getConfig();
    client.sendMessage({ type: 'config', data: cfg });
    simStarted = false;
    simPaused  = false;
    simComplete = false;
    updateButtons();
    addCard('system', `Config applied: ${cfg.buildings} buildings, ${cfg.exits} exits, ${cfg.avg_pop} ppl/bldg, ${cfg.highway_out} ppl/s highway`);
});

btnStart.addEventListener('click', () => {
    if (!isConnected) return;
    client.sendMessage({ type: 'start' });
    simStarted = true;
    simPaused  = false;
    updateButtons();
});

btnPause.addEventListener('click', () => {
    if (!isConnected || !simStarted) return;
    client.sendMessage({ type: 'pause' });
    simPaused = !simPaused;
    btnPause.textContent = simPaused ? 'Resume' : 'Pause';
});

btnReset.addEventListener('click', () => {
    if (!isConnected) return;
    client.sendMessage({ type: 'reset' });
    simStarted = false;
    simPaused  = false;
    simComplete = false;
    updateButtons();
    addCard('system', 'Simulation reset.');
});

aiSend.addEventListener('click', sendAiText);
aiText.addEventListener('keydown', e => { if (e.key === 'Enter') sendAiText(); });

function sendAiText() {
    const text = aiText.value.trim();
    if (!text || !isConnected) return;
    client.sendMessage({ type: 'text', data: text });
    addCard('system', `You: ${text}`);
    aiText.value = '';
}

// ── UI helpers ─────────────────────────────────────────────────────────
function updateButtons() {
    btnApply.disabled  = !isConnected;
    btnStart.disabled  = !isConnected || simStarted;
    btnPause.disabled  = !isConnected || !simStarted;
    btnReset.disabled  = !isConnected;
    aiText.disabled    = !isConnected;
    aiSend.disabled    = !isConnected;
    if (!simStarted) {
        btnPause.textContent = 'Pause';
        simPaused = false;
    }
}

function setStatus(label, cls = '') {
    connStatus.textContent = label;
    connStatus.className = cls;
}

function addCard(type, text) {
    const card = document.createElement('div');
    card.className = `decision-card ${type}`;

    const body = document.createElement('div');
    body.textContent = text;
    card.appendChild(body);

    const time = document.createElement('div');
    time.className = 'card-time';
    time.textContent = new Date().toLocaleTimeString();
    card.appendChild(time);

    decisionsLog.appendChild(card);
    decisionsLog.scrollTop = decisionsLog.scrollHeight;

    // Keep log from growing too large
    while (decisionsLog.children.length > 80) {
        decisionsLog.removeChild(decisionsLog.firstChild);
    }
}

function congestionClass(level) {
    if (level === 'clear')    return 'ok';
    if (level === 'moderate') return 'warn';
    if (level === 'heavy')    return 'bad';
    return '';
}

// ── Init ────────────────────────────────────────────────────────────────
updateButtons();
