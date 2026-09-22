// GameSfxStudio 프론트엔드 (프레임워크 없이 순수 JS)
'use strict';

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

// ------------------------------------------------------------------ 상태
let schema = null; // /api/sfx/schema
let settings = { language: 'ko', sample_rate: 44100, preview_volume: 0.8, auto_preview: true, reset_browser_cache_on_next_launch: false, setup_seen: true };

const state = {
  spec: null,        // 지금 편집 중인 효과음
  category: '',      // 마지막으로 고른 프리셋 id
  loaded: null,      // 저장된 효과음을 편집 중이면 {project, id, name}
  project: null,     // 선택된 프로젝트 이름
  projects: [],
  sounds: [],        // 선택된 프로젝트의 저장된 효과음 목록
  buffer: null,      // 지금 소리의 AudioBuffer
  renderSeq: 0,
};
const collapsedLayers = new WeakSet();
const history = [];
let committed = null;

// ------------------------------------------------------------------ API
async function api(path, options = {}) {
  return fetch(path, { headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options });
}

async function errorMessage(res) {
  const data = await res.json().catch(() => ({}));
  if (typeof data.detail === 'string') return data.detail;
  if (Array.isArray(data.detail)) return data.detail.map((d) => d.msg).join(', ');
  return `HTTP ${res.status}`;
}

async function apiJson(path, options = {}) {
  const res = await api(path, options);
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

const post = (path, body) => apiJson(path, { method: 'POST', body: JSON.stringify(body) });
const enc = encodeURIComponent;
const clone = (obj) => JSON.parse(JSON.stringify(obj));

function formatBytes(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes, i = 0;
  while (value >= 1024 && i < units.length - 1) { value /= 1024; i++; }
  return `${value.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

// ------------------------------------------------------------------ 토스트 / 모달
let toastTimer = null;
function toast(message, isError = false) {
  const node = $('#toast');
  node.textContent = message;
  node.className = `toast show${isError ? ' error' : ''}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { node.className = 'toast'; }, isError ? 4500 : 2200);
}

function showError(err) { toast(t('error.generic', { message: err.message || err }), true); }

/** 입력창/확인창 겸용 모달. 입력 모드면 문자열(취소 시 null), 확인 모드면 true/false를 돌려준다. */
function modal({ title, body = '', input = null, ok = t('modal.ok'), cancel = t('modal.cancel'), danger = false }) {
  return new Promise((resolve) => {
    const root = $('#modal'), field = $('#modal-input'), okBtn = $('#modal-ok'), cancelBtn = $('#modal-cancel');
    $('#modal-title').textContent = title;
    $('#modal-body').textContent = body;
    okBtn.textContent = ok;
    okBtn.className = danger ? 'danger' : '';
    cancelBtn.textContent = cancel;
    field.style.display = input === null ? 'none' : 'block';
    if (input !== null) field.value = input;
    root.style.display = 'flex';
    if (input !== null) { field.focus(); field.select(); } else okBtn.focus();

    const finish = (accepted) => {
      root.style.display = 'none';
      okBtn.onclick = cancelBtn.onclick = root.onkeydown = null;
      resolve(input === null ? accepted : (accepted ? field.value.trim() : null));
    };
    okBtn.onclick = () => finish(true);
    cancelBtn.onclick = () => finish(false);
    root.onkeydown = (e) => {
      if (e.key === 'Escape') finish(false);
      else if (e.key === 'Enter' && e.target !== cancelBtn) { e.preventDefault(); finish(true); }
    };
  });
}

// ------------------------------------------------------------------ 오디오 재생
let audioCtx = null;
let currentSource = null;

function ctx() {
  if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  if (audioCtx.state === 'suspended') audioCtx.resume();
  return audioCtx;
}

function playBuffer(buffer) {
  if (!buffer) return;
  stopPlayback();
  const c = ctx();
  const src = c.createBufferSource();
  const gain = c.createGain();
  gain.gain.value = settings.preview_volume;
  src.buffer = buffer;
  src.connect(gain).connect(c.destination);
  src.start();
  currentSource = src;
  src.onended = () => { if (currentSource === src) currentSource = null; };
}

function stopPlayback() {
  if (currentSource) { try { currentSource.stop(); } catch (e) { /* 이미 끝남 */ } currentSource = null; }
}

async function fetchBuffer(spec) {
  const res = await api('/api/sfx/render', { method: 'POST', body: JSON.stringify({ spec }) });
  if (!res.ok) throw new Error(await errorMessage(res));
  const peakDb = parseFloat(res.headers.get('X-Peak-Db'));
  const buffer = await ctx().decodeAudioData(await res.arrayBuffer());
  buffer.peakDb = peakDb; // 파일의 실제 피크(디코딩 시 재샘플링 오차 제외)
  return buffer;
}

// ------------------------------------------------------------------ 시각화 (파형 + 스펙트로그램)
function fitCanvas(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const w = Math.round(canvas.clientWidth * dpr), h = Math.round(canvas.clientHeight * dpr);
  if (w === 0 || h === 0) return null;
  if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  return canvas.getContext('2d');
}

function drawWave(canvas, buffer, color = '#ff955f') {
  const g = fitCanvas(canvas);
  if (!g) return;
  const W = canvas.width, H = canvas.height;
  g.clearRect(0, 0, W, H);
  g.fillStyle = 'rgba(255,255,255,0.08)';
  g.fillRect(0, Math.floor(H / 2), W, 1);
  if (!buffer) return;
  const data = buffer.getChannelData(0);
  const per = data.length / W;
  g.fillStyle = color;
  for (let x = 0; x < W; x++) {
    let lo = 1, hi = -1;
    const start = Math.floor(x * per), end = Math.min(data.length, Math.max(start + 1, Math.floor((x + 1) * per)));
    for (let i = start; i < end; i++) { const v = data[i]; if (v < lo) lo = v; if (v > hi) hi = v; }
    const y1 = (1 - hi) * 0.5 * H, y2 = (1 - lo) * 0.5 * H;
    g.fillRect(x, y1, 1, Math.max(1, y2 - y1));
  }
}

function fftInPlace(re, im) {
  const n = re.length;
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) { [re[i], re[j]] = [re[j], re[i]]; [im[i], im[j]] = [im[j], im[i]]; }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const ang = -2 * Math.PI / len, wr = Math.cos(ang), wi = Math.sin(ang), half = len >> 1;
    for (let i = 0; i < n; i += len) {
      let cr = 1, ci = 0;
      for (let k = 0; k < half; k++) {
        const a = i + k, b = a + half;
        const tr = re[b] * cr - im[b] * ci, ti = re[b] * ci + im[b] * cr;
        re[b] = re[a] - tr; im[b] = im[a] - ti; re[a] += tr; im[a] += ti;
        const nr = cr * wr - ci * wi; ci = cr * wi + ci * wr; cr = nr;
      }
    }
  }
}

const SPEC_LUT = (() => {
  const stops = [[0, 13, 10, 20], [0.3, 74, 26, 107], [0.6, 209, 67, 106], [0.85, 255, 154, 61], [1, 255, 242, 192]];
  const lut = new Uint8ClampedArray(256 * 3);
  for (let i = 0; i < 256; i++) {
    const v = i / 255;
    let s = 0;
    while (s < stops.length - 2 && v > stops[s + 1][0]) s++;
    const [a, b] = [stops[s], stops[s + 1]];
    const f = Math.min(1, Math.max(0, (v - a[0]) / (b[0] - a[0])));
    for (let c = 0; c < 3; c++) lut[i * 3 + c] = a[c + 1] + (b[c + 1] - a[c + 1]) * f;
  }
  return lut;
})();

function drawSpectrogram(canvas, buffer) {
  const g = fitCanvas(canvas);
  if (!g) return;
  const W = canvas.width, H = canvas.height;
  g.fillStyle = '#0d0a14';
  g.fillRect(0, 0, W, H);
  if (!buffer) return;

  const data = buffer.getChannelData(0);
  const N = 512, half = N / 2, sr = buffer.sampleRate;
  const cols = Math.min(W, 320);
  const hop = Math.max(1, (data.length - N) / cols);
  const window_ = new Float64Array(N).map((_, i) => 0.5 - 0.5 * Math.cos(2 * Math.PI * i / (N - 1)));
  const mags = [];
  let maxDb = -200;
  const re = new Float64Array(N), im = new Float64Array(N);
  for (let c = 0; c < cols; c++) {
    const start = Math.floor(c * hop);
    for (let i = 0; i < N; i++) { re[i] = (data[start + i] || 0) * window_[i]; im[i] = 0; }
    fftInPlace(re, im);
    const col = new Float32Array(half);
    for (let k = 0; k < half; k++) {
      const db = 20 * Math.log10(Math.hypot(re[k], im[k]) + 1e-9);
      col[k] = db;
      if (db > maxDb) maxDb = db;
    }
    mags.push(col);
  }

  const maxFreq = Math.min(12000, sr / 2);
  const img = g.createImageData(W, H);
  for (let x = 0; x < W; x++) {
    const col = mags[Math.min(cols - 1, Math.floor(x * cols / W))];
    for (let y = 0; y < H; y++) {
      const f = 1 - y / H;                        // 0=아래(저음) … 1=위
      const bin = Math.max(1, Math.min(half - 1, Math.floor((maxFreq * f * f) / (sr / 2) * half))); // 0번(DC) 제외
      const v = Math.min(1, Math.max(0, (col[bin] - maxDb + 80) / 80));
      const li = Math.round(v * 255) * 3, o = (y * W + x) * 4;
      img.data[o] = SPEC_LUT[li]; img.data[o + 1] = SPEC_LUT[li + 1]; img.data[o + 2] = SPEC_LUT[li + 2]; img.data[o + 3] = 255;
    }
  }
  g.putImageData(img, 0, 0);
}

function drawViz() {
  drawWave($('#wave-canvas'), state.buffer);
  drawSpectrogram($('#spec-canvas'), state.buffer);
}

function updateInfo() {
  const info = $('#sound-info');
  if (!state.buffer) { info.textContent = ''; return; }
  const db = state.buffer.peakDb;
  info.textContent = t('player.info', {
    sec: state.buffer.duration.toFixed(2),
    peak: Number.isFinite(db) && db > -100 ? db.toFixed(1) : '-∞',
    rate: settings.sample_rate,
  });
}

// ------------------------------------------------------------------ 소리 갱신
let renderTimer = null;

async function refreshSound(doPlay) {
  const seq = ++state.renderSeq;
  try {
    const buffer = await fetchBuffer(state.spec);
    if (seq !== state.renderSeq) return; // 더 최근 요청이 있음
    state.buffer = buffer;
    drawViz();
    updateInfo();
    if (doPlay) playBuffer(buffer);
  } catch (err) {
    if (seq === state.renderSeq) toast(t('player.renderError', { message: err.message }), true);
  }
}

/** 슬라이더를 끄는 동안 서버 요청이 폭주하지 않게 살짝 모아서 렌더한다. */
function scheduleRender() {
  clearTimeout(renderTimer);
  renderTimer = setTimeout(() => refreshSound(settings.auto_preview), 130);
}

// ------------------------------------------------------------------ 되돌리기
function snapshot() { return JSON.stringify({ spec: state.spec, category: state.category }); }

/** 변경이 적용된 '직후'에 호출. 직전 상태를 기록에 남긴다. */
function commit() {
  const now = snapshot();
  if (committed && committed !== now) {
    history.push(committed);
    if (history.length > 40) history.shift();
  }
  committed = now;
  $('#undo-btn').disabled = history.length === 0;
}

function undo() {
  const prev = history.pop();
  if (!prev) return;
  const obj = JSON.parse(prev);
  state.spec = obj.spec;
  state.category = obj.category;
  committed = prev;
  rebuildEditor();
  refreshSound(true);
  $('#undo-btn').disabled = history.length === 0;
}

// ------------------------------------------------------------------ 파라미터 컨트롤
function decimalsFor(step) { return step >= 1 ? 0 : Math.min(3, Math.ceil(-Math.log10(step))); }

function makeMapper(param) {
  const { min, max, step } = param;
  const dec = decimalsFor(step);
  const snap = (v) => {
    const q = Math.round(v / step) * step;
    return parseFloat(Math.min(max, Math.max(min, q)).toFixed(dec));
  };
  if (param.scale === 'log') {
    return { min: 0, max: 1000, step: 1, dec,
      toPos: (v) => Math.log(Math.max(v, min) / min) / Math.log(max / min) * 1000,
      fromPos: (p) => snap(min * Math.pow(max / min, p / 1000)) };
  }
  if (param.scale === 'pow') {
    return { min: 0, max: 1000, step: 1, dec,
      toPos: (v) => Math.sqrt(Math.max(0, (v - min) / (max - min))) * 1000,
      fromPos: (p) => snap(min + (max - min) * Math.pow(p / 1000, 2)) };
  }
  return { min, max, step, dec, toPos: (v) => v, fromPos: (p) => snap(p) };
}

/** 파라미터 하나의 컨트롤 한 줄. onChange(commit)는 값이 바뀔 때 호출(commit=true면 드래그를 놓은 순간). */
function buildParamRow(param, obj, onChange, rebuild) {
  const row = el('div', 'param-row');
  const label = el('label', null, t(`p.${param.id}`));
  label.title = t(`p.${param.id}.tip`) + (param.type === 'float' ? `  (${t('p.reset')})` : '');
  row.appendChild(label);

  const markChanged = () => row.classList.toggle('changed', obj[param.id] !== param.default);
  markChanged();

  if (param.type === 'asset') return buildSampleRow(param, obj, onChange, rebuild);

  if (param.type === 'bool') {
    const wrap = el('label', 'inline-check check');
    const box = document.createElement('input');
    box.type = 'checkbox';
    box.checked = !!obj[param.id];
    box.onchange = () => { obj[param.id] = box.checked; markChanged(); onChange(true); };
    wrap.append(box);
    row.appendChild(wrap);
    return row;
  }

  if (param.type === 'enum') {
    const select = document.createElement('select');
    param.options.forEach((opt) => {
      const o = el('option', null, t(`wave.${opt}`));
      o.value = opt;
      select.appendChild(o);
    });
    select.value = obj[param.id];
    select.onchange = () => { obj[param.id] = select.value; markChanged(); onChange(true); if (rebuild) rebuild(); };
    row.appendChild(select);
    return row;
  }

  const map = makeMapper(param);
  const range = document.createElement('input');
  range.type = 'range';
  range.min = map.min; range.max = map.max; range.step = map.step;
  range.value = map.toPos(obj[param.id]);
  const val = el('span', 'val');
  const show = () => {
    const v = obj[param.id];
    val.textContent = v.toFixed(map.dec);
    if (param.unit) val.appendChild(el('small', null, param.unit));
  };
  show();
  range.oninput = () => { obj[param.id] = map.fromPos(parseFloat(range.value)); show(); markChanged(); onChange(false); };
  range.onchange = () => onChange(true);
  label.ondblclick = () => {
    obj[param.id] = param.default;
    range.value = map.toPos(param.default);
    show(); markChanged(); onChange(true);
  };
  row.append(range, val);
  return row;
}

function paramVisible(param, layer) {
  const w = layer.wave;
  const isSample = w === 'sample';
  if (param.group === 'sample') return isSample;                 // 샘플 그룹은 샘플 레이어에만
  if (isSample) {                                                // 샘플 레이어는 합성용 항목을 숨김
    return !['freq', 'slide', 'slide_accel', 'arp_semitones', 'arp_time', 'vibrato_depth', 'vibrato_rate', 'duty',
      'duty_sweep', 'fm_ratio', 'fm_depth', 'noise_color', 'spread', 'sustain', 'punch'].includes(param.id);
  }
  switch (param.id) {
    case 'duty': case 'duty_sweep': return w === 'square';
    case 'fm_ratio': case 'fm_depth': return w !== 'noise' && w !== 'metal';
    case 'noise_color': return w === 'noise';
    case 'spread': return w === 'metal';
    case 'freq': case 'slide': case 'slide_accel': case 'arp_semitones': case 'arp_time':
    case 'vibrato_depth': case 'vibrato_rate': return w !== 'noise';
    default: return true;
  }
}

function buildParamGroups(params, obj, onChange, rebuild, filter) {
  const wrap = el('div', 'param-groups');
  const groups = [];
  params.forEach((p) => {
    if (p.id === 'enabled' || (filter && !filter(p))) return;
    let g = groups.find((x) => x.id === p.group);
    if (!g) { g = { id: p.group, params: [] }; groups.push(g); }
    g.params.push(p);
  });
  groups.forEach((g) => {
    const box = el('div', 'param-group');
    box.appendChild(el('div', 'param-group-title', t(`g.${g.id}`)));
    g.params.forEach((p) => box.appendChild(buildParamRow(p, obj, onChange, rebuild)));
    wrap.appendChild(box);
  });
  return wrap;
}

const onParamChange = (commitNow) => {
  if (commitNow) commit();
  scheduleRender();
};

// ------------------------------------------------------------------ 레이어 UI
function waveShort(w) { return t(`wave.${w}`).split(' ')[0]; }

function buildLayerCard(layer, index) {
  const card = el('div', 'layer-card');
  card.classList.toggle('off', !layer.enabled);
  card.classList.toggle('collapsed', collapsedLayers.has(layer));

  const head = el('div', 'layer-head');
  head.appendChild(el('span', 'layer-num', String(index + 1)));
  const title = el('span', 'layer-title', t('layers.name', { n: index + 1 }));
  title.appendChild(el('span', 'layer-sub', waveShort(layer.wave)));
  head.appendChild(title);

  const action = (icon, tip, fn) => {
    const b = el('button', 'secondary icon', icon);
    b.title = tip;
    b.onclick = (e) => { e.stopPropagation(); fn(); };
    head.appendChild(b);
  };
  action(layer.enabled ? '🔊' : '🔇', t('layers.mute'), () => {
    layer.enabled = !layer.enabled; commit(); rebuildLayers(); refreshSound(true);
  });
  action('⧉', t('layers.duplicate'), () => {
    if (state.spec.layers.length >= schema.max_layers) return toast(t('layers.max', { max: schema.max_layers }), true);
    state.spec.layers.splice(index + 1, 0, clone(layer));
    commit(); rebuildLayers(); refreshSound(true);
  });
  action('✕', t('layers.remove'), () => {
    if (state.spec.layers.length <= 1) return toast(t('layers.lastOne'), true);
    state.spec.layers.splice(index, 1);
    commit(); rebuildLayers(); refreshSound(true);
  });
  head.onclick = () => {
    if (collapsedLayers.has(layer)) collapsedLayers.delete(layer); else collapsedLayers.add(layer);
    card.classList.toggle('collapsed');
  };
  card.appendChild(head);

  const body = el('div', 'layer-body');
  const rebuild = () => { card.replaceWith(buildLayerCard(layer, index)); };
  body.appendChild(buildParamGroups(schema.layer, layer, onParamChange, rebuild, (p) => paramVisible(p, layer)));
  card.appendChild(body);
  return card;
}

function rebuildLayers() {
  const box = $('#layers');
  box.innerHTML = '';
  state.spec.layers.forEach((layer, i) => box.appendChild(buildLayerCard(layer, i)));
}

function rebuildMaster() {
  const box = $('#master-params');
  box.innerHTML = '';
  box.appendChild(buildParamGroups(schema.master, state.spec.master, onParamChange, null));
}

function rebuildEditor() {
  rebuildLayers();
  rebuildMaster();
  highlightPreset();
  updateLoadedNote();
}

$('#add-layer-btn').onclick = () => {
  if (state.spec.layers.length >= schema.max_layers) return toast(t('layers.max', { max: schema.max_layers }), true);
  const layer = Object.fromEntries(schema.layer.map((p) => [p.id, p.default]));
  Object.assign(layer, { wave: 'sine', freq: 440, gain: 0.6, attack: 0.005, sustain: 0.1, decay: 0.3 });
  state.spec.layers.push(layer);
  commit(); rebuildLayers(); refreshSound(true);
};

// ------------------------------------------------------------------ 프리셋 / 빠른 만들기
function presetLabel(id) {
  const p = schema.presets.find((x) => x.id === id);
  return p ? (currentLang === 'ko' ? p.ko : p.en) : id;
}

function buildPresetGrid() {
  const grid = $('#preset-grid');
  grid.innerHTML = '';
  [['hq', 'quick.hq'], ['retro', 'quick.retro']].forEach(([style, titleKey]) => {
    const presets = schema.presets.filter((p) => (p.style || 'retro') === style);
    if (!presets.length) return;
    grid.appendChild(el('div', 'preset-section-title', t(titleKey)));
    const row = el('div', 'preset-row');
    presets.forEach((p) => {
      const b = el('button', 'preset-btn');
      b.dataset.id = p.id;
      b.append(el('span', 'ico', p.icon), el('span', null, currentLang === 'ko' ? p.ko : p.en));
      b.onclick = () => loadPreset(p.id);
      row.appendChild(b);
    });
    grid.appendChild(row);
  });
  if (typeof appendUserPresets === 'function') appendUserPresets(grid);
  highlightPreset();
}

function highlightPreset() {
  $$('#preset-grid .preset-btn').forEach((b) => b.classList.toggle('active', b.dataset.id === state.category));
}

function nextDefaultName(base) {
  const re = new RegExp(`^${base}_(\\d+)$`);
  let max = 0;
  state.sounds.forEach((s) => { const m = re.exec(s.name); if (m) max = Math.max(max, parseInt(m[1], 10)); });
  return `${base}_${String(max + 1).padStart(2, '0')}`;
}

/** 새 소리로 시작(저장된 소리 편집 상태는 해제). */
function setNewSpec(spec, category, { play = true } = {}) {
  state.spec = clone(spec);
  state.category = category || '';
  state.loaded = null;
  $('#sfx-name').value = nextDefaultName(state.category || 'sfx');
  commit();
  rebuildEditor();
  refreshSound(play);
}

function loadPreset(id, opts) {
  const p = schema.presets.find((x) => x.id === id);
  if (p) setNewSpec(p.spec, id, opts);
}

$('#prompt-btn').onclick = async () => {
  const text = $('#prompt-text').value.trim();
  if (!text) return $('#prompt-text').focus();
  try {
    const r = await post('/api/sfx/from_text', { text });
    setNewSpec(r.spec, r.category);
    const mods = r.modifiers.length ? t('quick.mods', { list: r.modifiers.map((m) => t(`mod.${m}`)).join(', ') }) : '';
    $('#prompt-note').textContent = r.matched
      ? t('quick.promptMatched', { category: presetLabel(r.category), mods })
      : t('quick.promptGuess');
  } catch (err) { showError(err); }
};
$('#prompt-text').addEventListener('keydown', (e) => { if (e.key === 'Enter') $('#prompt-btn').click(); });

$('#random-btn').onclick = async () => {
  try {
    const r = await post('/api/sfx/randomize', { amount: 0.6 });
    setNewSpec(r.spec, r.category);
  } catch (err) { showError(err); }
};

const mutateAmount = () => parseInt($('#mutate-amount').value, 10) / 100;
$('#mutate-amount').oninput = () => { $('#mutate-amount-value').textContent = `${$('#mutate-amount').value}%`; };

$('#mutate-btn').onclick = async () => {
  try {
    const r = await post('/api/sfx/mutate', { spec: state.spec, amount: mutateAmount() });
    state.spec = r.spec;
    commit(); rebuildEditor(); refreshSound(true);
  } catch (err) { showError(err); }
};

$('#undo-btn').onclick = undo;

// ------------------------------------------------------------------ 변형 후보
$('#variations-btn').onclick = async () => {
  try {
    const r = await post('/api/sfx/variations', { spec: state.spec, count: 8, amount: Math.max(0.15, mutateAmount() * 0.8) });
    const grid = $('#variations-grid');
    grid.innerHTML = '';
    $('#variations-card').style.display = 'block';
    const cards = r.specs.map((spec, i) => {
      const card = el('div', 'var-card');
      const canvas = document.createElement('canvas');
      const actions = el('div', 'var-actions');
      actions.appendChild(el('span', 'num', `#${i + 1}`));
      const edit = el('button', 'small secondary', t('var.edit'));
      const save = el('button', 'small', t('var.save'));
      actions.append(edit, save);
      card.append(canvas, actions);
      grid.appendChild(card);
      const entry = { spec, canvas, buffer: null };
      canvas.onclick = () => entry.buffer && playBuffer(entry.buffer);
      edit.onclick = () => setNewSpec(spec, state.category);
      save.onclick = () => saveSound({ spec, name: nextDefaultName(state.category || 'sfx'), adopt: false });
      return entry;
    });
    await Promise.all(cards.map(async (c) => {
      c.buffer = await fetchBuffer(c.spec);
      drawWave(c.canvas, c.buffer, '#ff955f');
    }));
    grid.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (err) { showError(err); }
};
$('#variations-close').onclick = () => { $('#variations-card').style.display = 'none'; };

// ------------------------------------------------------------------ 플레이어 / 저장
$('#play-btn').onclick = () => (state.buffer ? playBuffer(state.buffer) : refreshSound(true));
$('#stop-btn').onclick = stopPlayback;
$('#wave-canvas').onclick = () => playBuffer(state.buffer);
$('#spec-canvas').onclick = () => playBuffer(state.buffer);

function updateLoadedNote() {
  const note = $('#loaded-note'), over = $('#save-over-btn');
  const active = state.loaded && state.loaded.project === state.project;
  over.style.display = active ? '' : 'none';
  note.style.display = active ? 'block' : 'none';
  if (active) note.textContent = t('player.loaded', { name: state.loaded.name });
}

function needProject() {
  toast(t('player.needProject'), true);
  const side = $('.sidebar');
  side.classList.remove('flash');
  void side.offsetWidth;
  side.classList.add('flash');
}

/** adopt=true면 저장한 소리를 '편집 중인 소리'로 삼는다(변형 후보를 바로 저장할 땐 false). */
async function saveSound({ spec = state.spec, name = '', overwrite = false, adopt = true } = {}) {
  if (!state.project) return needProject();
  name = (name || $('#sfx-name').value).trim() || nextDefaultName(state.category || 'sfx');
  try {
    const rec = await post(`/api/projects/${enc(state.project)}/sounds`, {
      name, spec, category: state.category,
      sound_id: overwrite && state.loaded ? state.loaded.id : null,
    });
    if (adopt) {
      state.loaded = { project: state.project, id: rec.id, name: rec.name };
      $('#sfx-name').value = rec.name;
      updateLoadedNote();  // 토스트/목록 갱신을 기다리지 않고 '덮어쓰기' 버튼을 바로 보여준다
    }
    toast(rec.noncommercial ? t('player.savedNc', { name: rec.name }) : t('player.saved', { name: rec.name }), !!rec.noncommercial);
    await refreshProjectData();
  } catch (err) { showError(err); }
  updateLoadedNote();
}

$('#save-new-btn').onclick = () => saveSound({ overwrite: false });
$('#save-over-btn').onclick = () => saveSound({ overwrite: true });

$('#download-btn').onclick = async () => {
  try {
    const name = $('#sfx-name').value.trim() || 'sfx';
    const res = await api(`/api/sfx/download?name=${enc(name)}`, { method: 'POST', body: JSON.stringify({ spec: state.spec }) });
    if (!res.ok) throw new Error(await errorMessage(res));
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement('a');
    a.href = url; a.download = `${name}.wav`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  } catch (err) { showError(err); }
};

$('#auto-preview').onchange = (e) => setSetting({ auto_preview: e.target.checked });

// ------------------------------------------------------------------ 프로젝트 (사이드바)
function avatarColor(name) {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.codePointAt(0)) % 360;
  return `hsl(${h}, 55%, 45%)`;
}

function renderProjectList() {
  const list = $('#project-list');
  list.innerHTML = '';
  if (!state.projects.length) {
    list.appendChild(el('li', 'empty', t('sidebar.none')));
    return;
  }
  state.projects.forEach((p) => {
    const li = el('li', p.name === state.project ? 'selected' : '');
    const av = el('span', 'project-avatar', [...p.name][0].toUpperCase());
    av.style.background = avatarColor(p.name);
    li.append(av, el('span', 'project-name-label', p.name), el('span', 'project-count', t('sidebar.count', { count: p.count })));
    li.onclick = () => selectProject(p.name);
    list.appendChild(li);
  });
}

async function loadProjects() {
  state.projects = await apiJson('/api/projects');
  renderProjectList();
}

async function refreshProjectData() {
  await loadProjects();
  if (state.project) await loadSounds();
}

async function selectProject(name) {
  state.project = name;
  try { localStorage.setItem('sfx.project', name || ''); } catch (e) { /* 무시 */ }
  renderProjectList();
  $('#library-empty').style.display = name ? 'none' : 'flex';
  $('#library-panel').style.display = name ? 'block' : 'none';
  if (!name) { state.sounds = []; updateLoadedNote(); return; }
  try {
    const proj = await apiJson(`/api/projects/${enc(name)}`);
    $('#library-title').textContent = t('library.title', { name });
    $('#project-description').value = proj.description || '';
    $('#project-export-dir').value = proj.export_dir || '';
    $('#export-zip-link').href = `/api/projects/${enc(name)}/export.zip`;
    $('#export-status').textContent = '';
    await loadSounds();
  } catch (err) { showError(err); }
  updateLoadedNote();
}

$('#new-project-btn').onclick = async () => {
  const name = await modal({ title: t('project.newTitle'), body: t('project.namePrompt'), input: '' });
  if (!name) return;
  try {
    await post('/api/projects', { name });
    await loadProjects();
    await selectProject(name);
  } catch (err) { showError(err); }
};

$('#delete-project-btn').onclick = async () => {
  if (!state.project) return toast(t('project.selectFirst'), true);
  const name = state.project;
  if (!await modal({ title: t('sidebar.delete'), body: t('project.deleteConfirm', { name }), danger: true, ok: t('sidebar.delete') })) return;
  try {
    await apiJson(`/api/projects/${enc(name)}`, { method: 'DELETE' });
    if (state.loaded && state.loaded.project === name) state.loaded = null;
    await loadProjects();
    await selectProject(null);
  } catch (err) { showError(err); }
};

// ------------------------------------------------------------------ 라이브러리
const soundBufferCache = new Map();

async function loadSounds() {
  state.sounds = await apiJson(`/api/projects/${enc(state.project)}/sounds`);
  renderSoundList();
}

function renderSoundList() {
  const list = $('#sound-list');
  list.innerHTML = '';
  if (!state.sounds.length) {
    list.appendChild(el('li', 'dim', t('library.noSounds')));
    return;
  }
  state.sounds.forEach((s) => {
    const li = el('li', 'sound-item');
    const play = el('button', 'small', '▶');
    play.onclick = async () => {
      try {
        const key = `${s.id}:${s.updated_at}`;
        if (!soundBufferCache.has(key)) {
          const res = await fetch(`/api/projects/${enc(state.project)}/sounds/${s.id}/audio`);
          if (!res.ok) throw new Error(await errorMessage(res));
          soundBufferCache.set(key, await ctx().decodeAudioData(await res.arrayBuffer()));
        }
        playBuffer(soundBufferCache.get(key));
      } catch (err) { showError(err); }
    };
    const meta = el('span', 's-meta');
    if (s.noncommercial) meta.appendChild(el('span', 'badge nc', t('ai.ncBadge')));
    if (s.category) meta.appendChild(el('span', 'badge', presetLabel(s.category)));
    meta.appendChild(el('span', null, t('library.duration', { sec: s.duration.toFixed(2) })));
    meta.appendChild(el('span', null, `${s.sample_rate / 1000} kHz`));

    const edit = el('button', 'small secondary', t('library.edit'));
    edit.onclick = async () => {
      try {
        const full = await apiJson(`/api/projects/${enc(state.project)}/sounds/${s.id}`);
        state.spec = full.spec;
        state.category = full.category || '';
        state.loaded = { project: state.project, id: full.id, name: full.name };
        $('#sfx-name').value = full.name;
        commit(); rebuildEditor();
        switchTopTab('workshop');
        refreshSound(true);
      } catch (err) { showError(err); }
    };
    const rename = el('button', 'small secondary', t('library.rename'));
    rename.onclick = async () => {
      const name = await modal({ title: t('library.rename'), body: t('library.renamePrompt'), input: s.name });
      if (!name || name === s.name) return;
      try {
        await apiJson(`/api/projects/${enc(state.project)}/sounds/${s.id}`, { method: 'PUT', body: JSON.stringify({ name }) });
        if (state.loaded && state.loaded.id === s.id) { state.loaded.name = name; updateLoadedNote(); }
        await loadSounds();
      } catch (err) { showError(err); }
    };
    const remove = el('button', 'small danger', t('library.remove'));
    remove.onclick = async () => {
      if (!await modal({ title: t('library.remove'), body: t('library.removeConfirm', { name: s.name }), danger: true, ok: t('library.remove') })) return;
      try {
        await apiJson(`/api/projects/${enc(state.project)}/sounds/${s.id}`, { method: 'DELETE' });
        if (state.loaded && state.loaded.id === s.id) { state.loaded = null; updateLoadedNote(); }
        await refreshProjectData();
      } catch (err) { showError(err); }
    };
    li.append(play, el('span', 's-name', s.name), meta, edit, rename, remove);
    list.appendChild(li);
  });
}

$('#project-description').onchange = async (e) => {
  try { await apiJson(`/api/projects/${enc(state.project)}`, { method: 'PUT', body: JSON.stringify({ description: e.target.value }) }); }
  catch (err) { showError(err); }
};
$('#project-export-dir').onchange = async (e) => {
  try { await apiJson(`/api/projects/${enc(state.project)}`, { method: 'PUT', body: JSON.stringify({ export_dir: e.target.value }) }); }
  catch (err) { showError(err); e.target.value = ''; }
};

$('#export-btn').onclick = async () => {
  try {
    const dir = $('#project-export-dir').value.trim();
    const r = await post(`/api/projects/${enc(state.project)}/export`, { dir: dir || null });
    const msg = t('library.exported', r) + (r.noncommercial ? ' — ' + t('library.exportedNc', { n: r.noncommercial }) : '');
    $('#export-status').textContent = msg;
    toast(msg, !!r.noncommercial);
  } catch (err) { showError(err); }
};
$('#open-folder-btn').onclick = async () => {
  try { await post(`/api/projects/${enc(state.project)}/open_folder`, { dir: $('#project-export-dir').value.trim() || null }); }
  catch (err) { showError(err); }
};

// ------------------------------------------------------------------ 설정
async function setSetting(updates) {
  try {
    settings = await apiJson('/api/settings', { method: 'PUT', body: JSON.stringify(updates) });
    syncSettingsUi();
  } catch (err) { showError(err); }
}

function syncSettingsUi() {
  $$('#lang-picker .lang-btn').forEach((b) => b.classList.toggle('active', b.dataset.lang === settings.language));
  $$('#rate-picker .lang-btn').forEach((b) => b.classList.toggle('active', parseInt(b.dataset.rate, 10) === settings.sample_rate));
  $('#preview-volume-slider').value = settings.preview_volume;
  $('#preview-volume-value').textContent = `${Math.round(settings.preview_volume * 100)}%`;
  $('#auto-preview').checked = settings.auto_preview;
  $('#auto-preview-setting').checked = settings.auto_preview;
}

$$('#lang-picker .lang-btn').forEach((b) => {
  b.onclick = async () => {
    await setSetting({ language: b.dataset.lang });
    setLanguage(settings.language);
    rerenderTexts();
  };
});

function buildRatePicker() {
  const box = $('#rate-picker');
  box.innerHTML = '';
  schema.sample_rates.forEach((rate) => {
    const b = el('button', 'lang-btn', `${rate / 1000} kHz`);
    b.type = 'button';
    b.dataset.rate = rate;
    b.onclick = async () => { await setSetting({ sample_rate: rate }); refreshSound(false); };
    box.appendChild(b);
  });
}

$('#preview-volume-slider').oninput = (e) => {
  settings.preview_volume = parseFloat(e.target.value);
  $('#preview-volume-value').textContent = `${Math.round(settings.preview_volume * 100)}%`;
};
$('#preview-volume-slider').onchange = (e) => setSetting({ preview_volume: parseFloat(e.target.value) });
$('#auto-preview-setting').onchange = (e) => setSetting({ auto_preview: e.target.checked });

async function refreshCacheInfo() {
  try {
    const info = await apiJson('/api/settings/cache_info');
    $('#browser-cache-info').textContent = t('settings.browserCacheInfo', { size: formatBytes(info.browser_cache_bytes) });
  } catch (err) { /* 무시 */ }
}

$('#reset-browser-cache-btn').onclick = async () => {
  await setSetting({ reset_browser_cache_on_next_launch: true });
  toast(t('settings.resetScheduled'));
};

// ------------------------------------------------------------------ 탭 / 언어 갱신 / 단축키
function switchTopTab(name) {
  $$('.top-tabs .tab-btn').forEach((b) => b.classList.toggle('active', b.dataset.toptab === name));
  $$('.toptab-panel').forEach((p) => p.classList.toggle('active', p.id === `toptab-${name}`));
  if (name === 'settings') refreshCacheInfo();
  if ((name === 'settings' || name === 'ai') && typeof loadAiStatus === 'function') loadAiStatus();
  if (name === 'workshop') requestAnimationFrame(drawViz);
}
$$('.top-tabs .tab-btn').forEach((b) => { b.onclick = () => switchTopTab(b.dataset.toptab); });

/** 언어가 바뀌면 JS가 그린 텍스트도 다시 만든다. */
function rerenderTexts() {
  buildPresetGrid();
  rebuildEditor();
  renderProjectList();
  renderSoundList();
  if (state.project) $('#library-title').textContent = t('library.title', { name: state.project });
  $('#mutate-amount').title = t('quick.mutateTip');
  $('#prompt-note').textContent = t('quick.promptHint');
  updateInfo();
  refreshCacheInfo();
  if (typeof rerenderAiTexts === 'function') rerenderAiTexts();
}

document.addEventListener('keydown', (e) => {
  const tag = e.target.tagName;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z' && tag !== 'TEXTAREA' && !(tag === 'INPUT' && e.target.type === 'text')) {
    e.preventDefault();
    undo();
  } else if (e.code === 'Space' && tag !== 'BUTTON' && tag !== 'SELECT' && (tag !== 'INPUT' || e.target.type === 'range')
      && $('#toptab-workshop').classList.contains('active') && $('#modal').style.display === 'none') {
    e.preventDefault();
    playBuffer(state.buffer);
  }
});

window.addEventListener('resize', () => { if ($('#toptab-workshop').classList.contains('active')) drawViz(); });

// ------------------------------------------------------------------ 시작
async function init() {
  try {
    settings = await apiJson('/api/settings');
    setLanguage(settings.language);
    $('#mutate-amount').title = t('quick.mutateTip');
    schema = await apiJson('/api/sfx/schema');
    buildRatePicker();
    syncSettingsUi();
    buildPresetGrid();
    loadPreset('hq_sword_swing', { play: false });   // 빈 화면 대신 바로 만져볼 수 있는 소리로 시작
    await loadProjects();
    let last = null;
    try { last = localStorage.getItem('sfx.project'); } catch (e) { /* 무시 */ }
    const target = state.projects.find((p) => p.name === last) || state.projects[0];
    await selectProject(target ? target.name : null);
    $('#sfx-name').value = nextDefaultName(state.category || 'sfx');
    if (typeof initAi === 'function') await initAi();
    if (typeof maybeOpenSetup === 'function') maybeOpenSetup();
  } catch (err) {
    showError(err);
  }
}

init();
