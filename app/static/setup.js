// 첫 실행 설치 도우미 (app.js, ai.js 다음에 로드됨)
'use strict';

let setupStatus = null;
let setupPollTimer = null;

function setupOpen() { return $('#setup-modal').style.display !== 'none'; }

async function openSetup() {
  $('#setup-modal').style.display = 'flex';
  await refreshSetup();
}

async function closeSetup() {
  $('#setup-modal').style.display = 'none';
  clearTimeout(setupPollTimer);
  if (!settings.setup_seen) await setSetting({ setup_seen: true });  // 다시 자동으로 뜨지 않게
  if (typeof loadAiStatus === 'function') loadAiStatus();
}

async function refreshSetup() {
  try { setupStatus = await apiJson('/api/setup/status'); } catch (e) { return; }
  renderSetup();
  clearTimeout(setupPollTimer);
  if (setupOpen() && setupStatus.job.state === 'running') setupPollTimer = setTimeout(refreshSetup, 1200);
}

function setupRow(icon, text, cls = '') {
  const row = el('div', `setup-row ${cls}`);
  row.append(el('span', 'setup-ico', icon), el('span', null, text));
  return row;
}

function renderSetup() {
  const st = setupStatus;
  const body = $('#setup-body');
  const logBox = body.querySelector('.setup-log');
  const keepScroll = logBox && logBox.scrollTop + logBox.clientHeight >= logBox.scrollHeight - 8;
  body.innerHTML = '';
  body.appendChild(el('p', 'dim', t('setup.intro')));

  // ① 기본 기능 — 설치할 것이 없음을 분명히
  const basics = el('div', 'setup-card ok');
  basics.appendChild(el('strong', null, t('setup.basics')));
  basics.appendChild(el('div', 'dim', t('setup.basicsDesc')));
  body.appendChild(basics);

  // ② AI 엔진
  const eng = el('div', `setup-card ${st.engine.ok ? 'ok' : ''}`);
  eng.appendChild(el('strong', null, t('setup.engineTitle')));
  eng.appendChild(el('div', 'dim', t('setup.engineDesc')));
  if (!st.platform_ok) eng.appendChild(setupRow('⚠', t('setup.notWindows'), 'warn'));
  eng.appendChild(st.engine.ok
    ? setupRow('✅', t('setup.engineOk', { torch: st.engine.torch, cuda: st.engine.cuda ? 'CUDA' : 'CPU' }))
    : setupRow('⬜', t('setup.engineMissing')));
  if (!st.path.ok) eng.appendChild(setupRow('⛔', t('setup.pathTooLong', { n: st.path.len, max: st.path.max }), 'warn'));
  eng.appendChild(st.gpu
    ? setupRow('✅', t('setup.gpuFound', { name: st.gpu.name, gb: st.gpu.vram_gb }))
    : setupRow('⚠', t('setup.gpuNone'), 'warn'));
  eng.appendChild(st.python
    ? setupRow('✅', t('setup.pythonFound', { v: st.python.version, path: st.python.path }))
    : setupRow('⚠', t('setup.pythonMissing', { mb: st.python_installer.size_mb }), 'warn'));
  const low = st.disk_free_gb < st.needed_gb.models;
  eng.appendChild(setupRow(low ? '⚠' : '✅', t('setup.disk', { free: st.disk_free_gb, eng: st.needed_gb.engine, all: st.needed_gb.models }), low ? 'warn' : ''));

  const job = st.job;
  if (job.state === 'running') {
    const bar = el('div', 'progress'); const fill = el('div', 'progress-fill');
    fill.style.width = `${Math.round((job.step - 1 + 0.5) / job.steps * 100)}%`;
    bar.appendChild(fill);
    eng.append(bar, el('div', null, `${t('setup.running')} [${job.step}/${job.steps}] ${job.label}`));
    const cancel = el('button', 'small danger', t('setup.cancel'));
    cancel.onclick = async () => { await post('/api/setup/cancel', {}); refreshSetup(); };
    eng.appendChild(cancel);
  } else {
    if (job.state === 'done') eng.appendChild(setupRow('🎉', t('setup.done'), 'okrow'));
    if (job.state === 'error') eng.appendChild(setupRow('❌', t('setup.error', { message: job.error }), 'warn'));
    if (job.state === 'cancelled') eng.appendChild(setupRow('⏹', t('setup.cancelled')));
    if (!st.engine.ok && st.platform_ok && st.path.ok) {
      let allow = null;
      if (!st.python) {
        const wrap = el('label', 'inline-check');
        allow = document.createElement('input'); allow.type = 'checkbox'; allow.id = 'setup-allow-python';
        wrap.append(allow, el('span', null, t('setup.allowPython', { mb: st.python_installer.size_mb })));
        eng.appendChild(wrap);
      }
      const btn = el('button', null, job.state === 'error' || job.state === 'cancelled' ? t('setup.retry') : t('setup.install'));
      btn.onclick = () => confirmInstall(allow);
      eng.appendChild(btn);
    }
  }
  if (job.log && job.log.length) {
    const log = el('pre', 'setup-log');
    log.textContent = job.log.join('\n');
    eng.appendChild(log);
    requestAnimationFrame(() => { if (keepScroll || job.state === 'running') log.scrollTop = log.scrollHeight; });
  }
  body.appendChild(eng);

  // ③ 모델 안내
  const models = el('div', 'setup-card');
  models.appendChild(el('strong', null, t('setup.modelsTitle')));
  models.appendChild(el('div', 'dim', t('setup.modelsDesc')));
  const go = el('button', 'small secondary', t('setup.goModels'));
  go.onclick = async () => { await closeSetup(); switchTopTab('settings'); };
  models.appendChild(go);
  body.appendChild(models);
  if (st.dry_run) body.appendChild(el('p', 'dim', t('setup.dry')));
}

async function confirmInstall(allowBox) {
  const st = setupStatus;
  const needsPython = !st.python;
  if (needsPython && !(allowBox && allowBox.checked)) {
    toast(t('setup.needAllow'), true);
    return;
  }
  const body = t('setup.confirmBody', {
    python: needsPython ? t('setup.confirmPythonNew', { mb: st.python_installer.size_mb }) : t('setup.confirmPythonHave', { v: st.python.version }),
    torch: st.gpu ? t('setup.torchGpu') : t('setup.torchCpu'),
  });
  if (!await modal({ title: t('setup.confirmTitle'), body, ok: t('setup.confirmOk') })) return;
  try {
    await post('/api/setup/install_engine', { install_python: needsPython });
    refreshSetup();
  } catch (e) { showError(e); }
}

$('#setup-close').onclick = closeSetup;
$('#open-setup-btn').onclick = openSetup;

/** 첫 실행이면(아직 한 번도 안 봤으면) 자동으로 연다. */
function maybeOpenSetup() {
  if (!settings.setup_seen) openSetup();
}
