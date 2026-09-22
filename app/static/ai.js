// AI 생성 · 참고 음원 학습 · 샘플 레이어 · 내 프리셋 (app.js 다음에 로드됨)
'use strict';

// ------------------------------------------------------------------ 오디오 파일 → 모노 WAV → 업로드
function encodeWav16(samples, sampleRate) {
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buf);
  const str = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  str(0, 'RIFF'); v.setUint32(4, 36 + samples.length * 2, true); str(8, 'WAVE'); str(12, 'fmt ');
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, sampleRate, true); v.setUint32(28, sampleRate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  str(36, 'data'); v.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buf], { type: 'audio/wav' });
}

/** wav/mp3/ogg/flac/mp4 등 브라우저가 디코딩할 수 있는 파일을 30초 이내 모노 WAV로 바꿔 서버에 저장한다. */
async function uploadSample(file) {
  let decoded;
  try { decoded = await ctx().decodeAudioData(await file.arrayBuffer()); }
  catch (e) { throw new Error(t('sample.decodeFail', { name: file.name })); }
  const n = Math.min(decoded.length, Math.floor(30 * decoded.sampleRate));
  const mono = new Float32Array(n);
  for (let c = 0; c < decoded.numberOfChannels; c++) {
    const d = decoded.getChannelData(c);
    for (let i = 0; i < n; i++) mono[i] += d[i] / decoded.numberOfChannels;
  }
  if (decoded.length > n) toast(t('sample.trimmed', { name: file.name }));
  const res = await fetch('/api/samples', { method: 'POST', headers: { 'Content-Type': 'audio/wav' }, body: encodeWav16(mono, decoded.sampleRate) });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

function pickAudioFile(onFile) {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = 'audio/*,video/*,.wav,.mp3,.ogg,.flac,.m4a,.mp4,.m4v';
  input.onchange = () => { if (input.files[0]) onFile(input.files[0]); };
  input.click();
}

const sampleBuffers = new Map();
async function getSampleBuffer(id) {
  if (!sampleBuffers.has(id)) {
    const res = await fetch(`/api/samples/${id}`);
    if (!res.ok) throw new Error(await errorMessage(res));
    sampleBuffers.set(id, await ctx().decodeAudioData(await res.arrayBuffer()));
  }
  return sampleBuffers.get(id);
}

function newLayerFromSchema(overrides) {
  const layer = Object.fromEntries(schema.layer.map((p) => [p.id, p.default]));
  return Object.assign(layer, overrides);
}

function sampleLayer(id, extra = {}) {
  return newLayerFromSchema({ wave: 'sample', sample: id, gain: 0.9, attack: 0.001, sustain: 0, decay: 0.05, ...extra });
}

// ------------------------------------------------------------------ 레이어의 '샘플' 행 (app.js의 buildParamRow가 호출)
function buildSampleRow(param, obj, onChange, rebuild) {
  const row = el('div', 'param-row sample-row');
  const label = el('label', null, t('p.sample'));
  label.title = t('p.sample.tip');
  const box = el('div', 'sample-box');
  const info = el('span', 'dim', obj.sample ? '…' : t('sample.none'));
  const play = el('button', 'small secondary', '▶');
  play.onclick = async () => { try { if (obj.sample) playBuffer(await getSampleBuffer(obj.sample)); } catch (e) { showError(e); } };
  const pick = el('button', 'small secondary', t('sample.replace'));
  pick.onclick = () => pickAudioFile(async (file) => {
    try { obj.sample = (await uploadSample(file)).id; onChange(true); rebuild(); } catch (e) { showError(e); }
  });
  box.append(play, info, pick);
  row.append(label, box);
  if (obj.sample) {
    apiJson(`/api/samples/${obj.sample}/info`)
      .then((i) => {
        info.textContent = `${i.duration.toFixed(2)}s · ${i.sample_rate / 1000}kHz`;
        if (i.noncommercial) box.appendChild(el('span', 'badge nc', t('ai.ncBadge')));
      })
      .catch(() => { info.textContent = t('sample.missing'); });
  }
  return row;
}

$('#add-sample-btn').onclick = () => pickAudioFile(async (file) => {
  try {
    if (state.spec.layers.length >= schema.max_layers) return toast(t('layers.max', { max: schema.max_layers }), true);
    const info = await uploadSample(file);
    state.spec.layers.push(sampleLayer(info.id));
    commit(); rebuildLayers(); refreshSound(true);
  } catch (e) { showError(e); }
});

// ------------------------------------------------------------------ 내 프리셋 (배운 소리)
state.userPresets = [];

async function loadUserPresets() {
  try { state.userPresets = await apiJson('/api/user_presets'); } catch (e) { state.userPresets = []; }
}

/** app.js의 프리셋 그리드 맨 아래에 '내 프리셋' 섹션을 붙인다. */
function appendUserPresets(grid) {
  if (!state.userPresets.length) return;
  grid.appendChild(el('div', 'preset-section-title', t('quick.mine')));
  const row = el('div', 'preset-row');
  const groups = {};
  state.userPresets.forEach((p) => {
    (groups[p.group || ''] = groups[p.group || ''] || []).push(p);
    const b = el('button', 'preset-btn user');
    b.append(el('span', 'ico', '⭐'), el('span', null, p.name));
    const del = el('span', 'preset-del', '×');
    del.title = t('library.remove');
    del.onclick = async (e) => {
      e.stopPropagation();
      if (!await modal({ title: t('library.remove'), body: t('mine.removeConfirm', { name: p.name }), danger: true, ok: t('library.remove') })) return;
      await apiJson(`/api/user_presets/${p.id}`, { method: 'DELETE' });
      await loadUserPresets(); buildPresetGrid();
    };
    b.appendChild(del);
    b.onclick = () => setNewSpec(p.spec, '');
    row.appendChild(b);
  });
  Object.entries(groups).forEach(([name, list]) => {
    if (!name || list.length < 2) return;
    const b = el('button', 'preset-btn user');
    b.append(el('span', 'ico', '🎲'), el('span', null, t('mine.groupRandom', { group: name, n: list.length })));
    b.onclick = async () => {
      const pick = list[Math.floor(Math.random() * list.length)];
      try { setNewSpec((await post('/api/sfx/mutate', { spec: pick.spec, amount: 0.15 })).spec, ''); } catch (e) { showError(e); }
    };
    row.appendChild(b);
  });
  grid.appendChild(row);
}

// ------------------------------------------------------------------ AI 상태 / 모델 선택 (AI 탭 + 설정 탭)
let aiState = null;
let aiRecipes = null;
let aiSelected = '';
let aiPollTimer = null;
let modelSelectBuilt = false;

const aiModel = (id) => (aiState ? aiState.models.find((m) => m.id === id) : null);
const selectedModelId = () => $('#ai-model').value || 'sao';

async function loadAiStatus() {
  try { aiState = await apiJson('/api/ai/status'); } catch (e) { return; }
  renderAiStatus();
  if (aiState.download.state === 'running') { clearTimeout(aiPollTimer); aiPollTimer = setTimeout(loadAiStatus, 1500); }
}

/** 모델 선택 상자: 상업 이용 가능 여부를 이름 옆에 항상 함께 보여준다. */
function buildModelSelect() {
  const sel = $('#ai-model');
  let keep = sel.value;
  if (!keep) { try { keep = localStorage.getItem('sfx.aimodel') || ''; } catch (e) { keep = ''; } }
  sel.innerHTML = '';
  aiState.models.forEach((m) => {
    const o = el('option', null, `${m.name} · ${m.commercial ? t('ai.commercialOk') : t('ai.ncOnly')}${m.ready ? '' : ` · ${t('ai.notDownloaded')}`}`);
    o.value = m.id;
    sel.appendChild(o);
  });
  const firstReadyCommercial = aiState.models.find((m) => m.ready && m.commercial);
  const firstReady = aiState.models.find((m) => m.ready);
  sel.value = aiModel(keep) ? keep : (firstReadyCommercial || firstReady || aiState.models[0]).id;
}

$('#ai-model').onchange = () => {
  try { localStorage.setItem('sfx.aimodel', selectedModelId()); } catch (e) { /* 무시 */ }
  renderAiStatus();
};

function renderAiStatus() {
  const st = aiState;
  if (!st) return;
  if (!modelSelectBuilt) { buildModelSelect(); modelSelectBuilt = true; }
  const m = aiModel(selectedModelId());
  const banner = $('#ai-status');
  let cls = 'ok', text = '';
  if (!st.installed) { cls = 'warn'; text = t('ai.notInstalled'); }
  else if (!m.ready) { cls = 'warn'; text = t('ai.modelNotReady', { name: m.name }); }
  else if (st.mock) { cls = 'warn'; text = t('ai.mock'); }
  else text = st.worker_running ? t('ai.readyOn', { device: st.worker.device }) : t('ai.readyOff');
  banner.className = `ai-status ${cls}`;
  banner.textContent = text;
  if (!st.installed) {
    const open = el('button', 'small', t('setup.open'));
    open.onclick = openSetup;
    banner.appendChild(open);
  }
  if (st.installed && !m.ready) {
    const go = el('button', 'small', t('ai.goSettings'));
    go.onclick = () => switchTopTab('settings');
    banner.appendChild(go);
  }
  // 라이선스 안내: 상업 이용 가능은 초록, 비상업 전용은 빨간 경고
  const note = $('#ai-license-note');
  note.className = `ai-license-note ${m.commercial ? 'ok' : 'nc'}`;
  note.textContent = m.commercial ? t('ai.noteCommercial') : t('ai.noteNc');
  const secInput = $('#ai-seconds');
  secInput.max = m.max_seconds;
  if (parseFloat(secInput.value) > m.max_seconds) secInput.value = m.max_seconds;
  $('#ai-generate-btn').disabled = !(st.installed && m.ready);
  $('#ai-stop-btn').disabled = !st.worker_running;
  renderModelList();
}

/** 설정 탭: 모델별 카드(상태·용량·라이선스·내려받기). */
function renderModelList() {
  const st = aiState;
  const box = $('#ai-models-list');
  box.innerHTML = '';
  const dl = st.download;
  st.models.forEach((m) => {
    const card = el('div', `ai-model-card ${m.commercial ? 'ok' : 'nc'}`);
    const head = el('div', 'ai-model-head');
    head.append(el('strong', null, m.name),
      el('span', `badge ${m.commercial ? '' : 'nc'}`, m.commercial ? t('ai.commercialOk') : t('ai.ncOnly')),
      el('span', 'dim', m.ready ? t('settings.aiReady') : t('settings.aiMissing', { gb: m.size_gb })));
    card.appendChild(head);
    card.appendChild(el('div', 'dim', `${m.license}`));
    card.appendChild(el('div', 'dim', m.note));
    const row = el('div', 'btn-row');
    const link = el('a', 'dim', t('settings.aiLicensePage'));
    link.href = m.license_url; link.target = '_blank'; link.rel = 'noopener';
    if (!m.ready && st.installed) {
      const btn = el('button', 'small', t('settings.aiDownload'));
      btn.disabled = dl.state === 'running';
      btn.onclick = async () => {
        try {
          await post('/api/ai/download', { model: m.id, token: m.needs_token ? $('#ai-token').value : '' });
          $('#ai-token').value = '';
          loadAiStatus();
        } catch (e) { showError(e); }
      };
      row.appendChild(btn);
    }
    row.appendChild(link);
    card.appendChild(row);
    if (dl.model === m.id && dl.state !== 'idle') {
      const bar = el('div', 'progress'); bar.style.display = dl.state === 'running' ? 'block' : 'none';
      const fill = el('div', 'progress-fill'); fill.style.width = dl.total ? `${Math.min(100, dl.done / dl.total * 100)}%` : '0%';
      bar.appendChild(fill);
      card.appendChild(bar);
      card.appendChild(el('div', 'dim', dl.state === 'running' ? `${dl.message} ${formatBytes(dl.done)} / ${formatBytes(dl.total)}`
        : dl.state === 'error' ? `⚠ ${dl.message}` : t('settings.aiDownloadDone')));
    }
    box.appendChild(card);
  });
  $('#ai-token-row').style.display = st.models.some((m) => m.needs_token && !m.ready) ? 'block' : 'none';
}

$('#ai-stop-btn').onclick = async () => { await post('/api/ai/stop', {}); await loadAiStatus(); toast(t('ai.stopped')); };

// ------------------------------------------------------------------ AI 생성 화면
function buildAiRecipeGrid() {
  const grid = $('#ai-recipes');
  grid.innerHTML = '';
  aiRecipes.recipes.forEach((r) => {
    const b = el('button', 'preset-btn');
    b.dataset.id = r.id;
    b.append(el('span', 'ico', r.icon), el('span', null, currentLang === 'ko' ? r.ko : r.en));
    b.onclick = () => {
      aiSelected = r.id;
      $('#ai-seconds').value = r.seconds;
      $$('#ai-recipes .preset-btn').forEach((x) => x.classList.toggle('active', x === b));
    };
    if (r.id === aiSelected) b.classList.add('active');
    grid.appendChild(b);
  });
  const fill = (sel, values, prefix) => {
    const cur = sel.value;
    sel.innerHTML = '';
    values.forEach((v) => { const o = el('option', null, t(`${prefix}.${v || 'none'}`)); o.value = v; sel.appendChild(o); });
    sel.value = cur;
  };
  fill($('#ai-env'), aiRecipes.environments, 'env');
  fill($('#ai-distance'), aiRecipes.distances, 'dist');
}

async function initAiTab() {
  try { aiRecipes = await apiJson('/api/ai/recipes'); buildAiRecipeGrid(); } catch (e) { showError(e); }
  loadAiStatus();
}

const BOOST_LAYERS = {
  gun: () => [newLayerFromSchema({ wave: 'sine', freq: 75, slide: -4, attack: 0, sustain: 0.01, decay: 0.16, decay_curve: 1.8, gain: 0.45 }),
              newLayerFromSchema({ wave: 'noise', hp_cutoff: 2500, attack: 0, sustain: 0.001, decay: 0.02, gain: 0.25 })],
  explosion: () => [newLayerFromSchema({ wave: 'sine', freq: 45, slide: -0.6, attack: 0.004, sustain: 0.05, decay: 1.4, decay_curve: 1.8, gain: 0.8 }),
                    newLayerFromSchema({ wave: 'noise', noise_color: 2, lp_cutoff: 200, delay: 0.02, attack: 0.03, sustain: 0.2, decay: 1.6, gain: 0.5 })],
  impact: () => [newLayerFromSchema({ wave: 'sine', freq: 100, slide: -3, attack: 0, sustain: 0.01, decay: 0.14, gain: 0.6 })],
};

function specFromSample(id, boostKind) {
  const layers = [sampleLayer(id, { gain: 1.0 })];
  if ($('#ai-boost').checked && BOOST_LAYERS[boostKind]) layers.push(...BOOST_LAYERS[boostKind]());
  return { seed: 1, layers, master: { ...Object.fromEntries(schema.master.map((p) => [p.id, p.default])), comp: 0.25 } };
}

async function drawSampleCanvas(canvas, id) {
  try { drawWave(canvas, await getSampleBuffer(id)); } catch (e) { /* 무시 */ }
}

let aiBusy = false;
$('#ai-generate-btn').onclick = async () => {
  if (aiBusy) return;
  const body = {
    model: selectedModelId(), recipe: aiSelected, env: $('#ai-env').value, distance: $('#ai-distance').value, extra: $('#ai-extra').value,
    prompt: $('#ai-prompt').value, seconds: parseFloat($('#ai-seconds').value) || 3, steps: parseInt($('#ai-quality').value, 10),
    count: parseInt($('#ai-count').value, 10), seed: 0,
  };
  aiBusy = true;
  $('#ai-generate-btn').disabled = true;
  $('#ai-results').innerHTML = '';
  const bar = $('#ai-progress'), fill = $('#ai-progress-fill'), text = $('#ai-progress-text');
  try {
    const { job_id } = await post('/api/ai/generate', body);
    bar.style.display = 'block';
    for (;;) {
      await new Promise((r) => setTimeout(r, 700));
      const job = await apiJson(`/api/ai/jobs/${job_id}`);
      const w = job.worker || {};
      const within = w.busy && w.steps ? w.step / w.steps : 0;
      fill.style.width = `${Math.min(100, (job.results.length + within) / job.count * 100)}%`;
      text.textContent = t('ai.progress', { i: Math.min(job.results.length + 1, job.count), n: job.count, step: w.step || 0, steps: w.steps || 0 });
      if (job.prompt) $('#ai-prompt-used').textContent = `${t('ai.promptUsed')}: ${job.prompt}`;
      renderAiResults(job.results, body.recipe);
      if (job.status === 'error') throw new Error(job.error);
      if (job.status === 'done') break;
    }
    toast(t('ai.done'));
  } catch (e) { showError(e); }
  finally {
    aiBusy = false; bar.style.display = 'none'; text.textContent = '';
    loadAiStatus();
  }
};

function renderAiResults(results, recipeId) {
  const box = $('#ai-results');
  if (box.children.length === results.length) return;
  const meta = aiRecipes.recipes.find((r) => r.id === recipeId);
  for (let i = box.children.length; i < results.length; i++) {
    const res = results[i];
    const card = el('div', 'result-card');
    const canvas = document.createElement('canvas');
    canvas.onclick = async () => playBuffer(await getSampleBuffer(res.id));
    const head = el('div', 'dim', `#${i + 1} · ${res.duration.toFixed(2)}s · seed ${res.seed}`);
    if (res.noncommercial) head.appendChild(el('span', 'badge nc', t('ai.ncBadge')));
    const edit = el('button', 'small', t('ai.toWorkshop'));
    edit.onclick = () => { setNewSpec(specFromSample(res.id, meta ? meta.boost : ''), recipeId); switchTopTab('workshop'); };
    const save = el('button', 'small secondary', t('var.save'));
    save.onclick = () => saveSound({ spec: specFromSample(res.id, meta ? meta.boost : ''), name: nextDefaultName(recipeId || 'ai'), adopt: false });
    const row = el('div', 'var-actions');
    row.append(edit, save);
    card.append(canvas, head, row);
    box.appendChild(card);
    drawSampleCanvas(canvas, res.id);
  }
}

// ------------------------------------------------------------------ 참고 음원에서 배우기
$('#learn-btn').onclick = () => $('#learn-files').click();
$('#learn-files').onchange = async (e) => {
  const files = Array.from(e.target.files);
  e.target.value = '';
  $('#learn-btn').disabled = true;
  for (const file of files) {
    try { await learnOne(file); } catch (err) { showError(err); }
  }
  $('#learn-btn').disabled = false;
  $('#learn-status').textContent = '';
  $('#learn-progress').style.display = 'none';
};

async function learnOne(file) {
  const status = $('#learn-status'), bar = $('#learn-progress'), fill = $('#learn-progress-fill');
  status.textContent = t('learn.uploading', { name: file.name });
  const info = await uploadSample(file);
  const { job_id } = await post('/api/learn', { sample_id: info.id, budget: parseInt($('#learn-budget').value, 10) });
  bar.style.display = 'block';
  for (;;) {
    await new Promise((r) => setTimeout(r, 600));
    const job = await apiJson(`/api/learn/${job_id}`);
    fill.style.width = `${Math.round((job.progress || 0) * 100)}%`;
    status.textContent = t('learn.running', { name: file.name, pct: Math.round((job.progress || 0) * 100) });
    if (job.status === 'error') throw new Error(job.error);
    if (job.status === 'done') { renderLearnResult(file.name, info, job.result); return; }
  }
}

function renderLearnResult(fileName, info, result) {
  const card = el('div', 'result-card learn');
  const baseName = fileName.replace(/\.[^.]+$/, '').slice(0, 40);
  const gain = Math.round((1 - result.loss / result.loss0) * 100);
  const f = result.features;
  card.appendChild(el('div', null, baseName));
  card.appendChild(el('div', 'dim', t('learn.summary', { gain, attack: (f.attack * 1000).toFixed(0), decay: f.decay40.toFixed(2), low: f.low_hz || '-', rt60: f.rt60 })));
  const row = el('div', 'var-actions');
  const orig = el('button', 'small secondary', t('learn.playOrig'));
  orig.onclick = async () => playBuffer(await getSampleBuffer(info.id));
  const fitted = el('button', 'small secondary', t('learn.playFit'));
  fitted.onclick = async () => playBuffer(await fetchBuffer(result.spec));
  const edit = el('button', 'small', t('ai.toWorkshop'));
  edit.onclick = () => { setNewSpec(result.spec, ''); $('#sfx-name').value = `${baseName}_fit`; switchTopTab('workshop'); };
  const layered = el('button', 'small secondary', t('learn.withOrig'));
  layered.title = t('learn.withOrigTip');
  layered.onclick = () => {
    const spec = clone(result.spec);
    spec.layers.push(sampleLayer(info.id, { gain: 0.8 }));
    setNewSpec(spec, ''); $('#sfx-name').value = `${baseName}_layered`; switchTopTab('workshop');
  };
  const mine = el('button', 'small', t('learn.saveMine'));
  mine.onclick = async () => {
    try {
      await post('/api/user_presets', { name: baseName, spec: result.spec, group: $('#learn-group').value.trim(), note: `learned ${gain}%` });
      await loadUserPresets(); buildPresetGrid(); toast(t('learn.savedMine', { name: baseName }));
    } catch (e) { showError(e); }
  };
  row.append(orig, fitted, edit, layered, mine);
  card.appendChild(row);
  $('#learn-results').prepend(card);
}

// ------------------------------------------------------------------ 언어 전환 / 시작
function rerenderAiTexts() {
  if (aiRecipes) buildAiRecipeGrid();
  if (aiState) buildModelSelect();  // 언어가 바뀌면 모델 이름 옆 라벨도 다시 만든다(선택값은 유지)
  renderAiStatus();
}

async function initAi() {
  await loadUserPresets();
  buildPresetGrid();
  initAiTab();
}
