"""AI·학습·샘플 레이어 UI 스모크(모의 AI 모드 서버 필요: GAMESFX_AI_MOCK=1).
테스트용 참고 음원은 이 스크립트가 직접 합성한 WAV이며 원작/외부 음원은 쓰지 않는다.

사용: uv run --with playwright --with numpy python tools/ui_ai_smoke.py <스크린샷 폴더> <임시 폴더>
"""
from __future__ import annotations

import io
import sys
import wave
from pathlib import Path

import numpy as np
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8878/"
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
TMP = Path(sys.argv[2]); TMP.mkdir(parents=True, exist_ok=True)
errors: list[str] = []
fails = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global fails
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    fails += 0 if cond else 1


def make_wav(path: Path, seed: int) -> None:
    """직접 합성한 총성 비슷한 참고 소리(감쇠 노이즈 + 저음 쿵 + 반사음)."""
    sr = 44100
    rng = np.random.default_rng(seed)
    t = np.arange(int(1.4 * sr)) / sr
    x = rng.standard_normal(len(t)) * np.exp(-t / 0.05) + 0.9 * np.sin(2 * np.pi * (60 + 70 * np.exp(-t / 0.03)) * t) * np.exp(-t / 0.12)
    ir = np.zeros(int(0.5 * sr)); ir[0] = 1
    for ms, a in [(11, .4), (23, -.3), (41, .25)]:
        ir[int(ms * sr / 1000)] = a
    x = np.convolve(x, ir)[: len(t)]
    x = x / np.max(np.abs(x)) * 0.8
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((x * 32767).astype("<i2").tobytes())


files = []
for i in (1, 2):
    p = TMP / f"ref_{i}.wav"; make_wav(p, i); files.append(str(p))

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="msedge", headless=True, args=["--autoplay-policy=no-user-gesture-required"])
    page = browser.new_page(viewport={"width": 1320, "height": 1000})
    page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type in ("error", "warning") and "400" not in m.text else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    # 잘못된 토큰 형식을 일부러 보내는 요청(/api/ai/download → 400)은 정상 동작이므로 오류로 세지 않는다
    page.on("response", lambda r: errors.append(f"HTTP {r.status}: {r.url}") if r.status >= 400 and "/api/ai/download" not in r.url else None)

    page.request.put(URL + "api/settings", data={"language": "ko", "setup_seen": True})   # 언어 초기화 + 첫 실행 마법사 건너뜀
    page.goto(URL)
    page.wait_for_selector(".preset-btn")
    page.wait_for_function("document.querySelector('#sound-info').textContent.includes('Hz')")

    # --- 샘플 레이어 추가(작업실)
    n_before = page.locator(".layer-card").count()
    with page.expect_file_chooser() as fc:
        page.click("#add-sample-btn")
    fc.value.set_files(files[0])
    page.wait_for_function(f"document.querySelectorAll('.layer-card').length === {n_before + 1}")
    last = page.locator(".layer-card").last
    check("sample layer added with 'sample' wave", last.locator("select").first.input_value() == "sample")
    check("sample layer shows duration info", page.wait_for_function("document.querySelector('.sample-box .dim').textContent.includes('kHz')") is not None)
    check("sample layer hides synth-only params", last.locator("text=기본 음높이").count() == 0 and last.locator("text=소리 파일").count() == 1)
    page.wait_for_function("!document.querySelector('#sound-info').textContent.includes('undefined')")
    page.screenshot(path=str(OUT / "10_sample_layer.png"), full_page=False)

    # --- AI 탭(모의 모드)
    page.click('[data-toptab="ai"]')
    page.wait_for_selector("#ai-recipes .preset-btn")
    page.wait_for_function("document.querySelector('#ai-status').textContent.trim().length > 0")
    check("ai status banner shows mock warning", "모의" in page.locator("#ai-status").text_content())
    check("22 recipes listed", page.locator("#ai-recipes .preset-btn").count() == 22)
    check("env/distance selects populated", page.locator("#ai-env option").count() == 7 and page.locator("#ai-distance option").count() == 3)
    page.click('#ai-recipes .preset-btn[data-id="pistol"]')
    check("recipe click sets recommended length", page.input_value("#ai-seconds") == "2.5")
    page.select_option("#ai-env", "indoor"); page.select_option("#ai-quality", "40"); page.select_option("#ai-count", "2")
    page.fill("#ai-extra", "아주 날카로운")
    page.click("#ai-generate-btn")
    page.wait_for_selector("#ai-results .result-card", timeout=60000)
    page.wait_for_function("document.querySelectorAll('#ai-results .result-card').length === 2", timeout=60000)
    page.wait_for_function("document.querySelector('#ai-generate-btn').disabled === false", timeout=30000)
    used = page.locator("#ai-prompt-used").text_content()
    check("used prompt shown (translated + env)", "pistol gunshot" in used and "very sharp" in used and "concrete room" in used, used)
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / "11_ai_tab.png"), full_page=False)
    check("AI result canvas has waveform ink", page.evaluate("""() => { const c = document.querySelector('#ai-results canvas');
        const d = c.getContext('2d').getImageData(0,0,c.width,c.height).data; let n=0; for (let i=3;i<d.length;i+=4) if (d[i]>0) n++; return n>100; }"""))
    # AI 결과 → 작업실(합성 보강 포함)
    page.locator("#ai-results .result-card button", has_text="작업실로 보내기").first.click()
    page.wait_for_selector("#toptab-workshop.active")
    page.wait_for_function("document.querySelectorAll('.layer-card').length === 3")  # 샘플 + 보강 2
    waves = page.evaluate("Array.from(document.querySelectorAll('.layer-card')).map(c => c.querySelector('select').value)")
    check("AI result → sample layer + gun boost layers", waves == ["sample", "sine", "noise"], str(waves))

    # --- 모델 선택 + 비상업 라이선스 흐름
    page.click('[data-toptab="ai"]')
    opts = page.evaluate("Array.from(document.querySelectorAll('#ai-model option')).map(o => o.textContent)")
    check("model select lists both models with commercial status", len(opts) == 2 and "상업 이용 가능" in opts[0] and "비상업 전용" in opts[1], str(opts))
    check("commercial model shows green license note", "ok" in page.locator("#ai-license-note").get_attribute("class"))
    page.select_option("#ai-model", "audioldm2")
    check("non-commercial model shows red warning", "nc" in page.locator("#ai-license-note").get_attribute("class") and "출시" in page.locator("#ai-license-note").text_content())
    check("non-commercial model caps length input at 10s", page.get_attribute("#ai-seconds", "max") == "10")
    page.click("#new-project-btn"); page.fill("#modal-input", "__ui_nc__"); page.keyboard.press("Enter")
    page.wait_for_selector("#project-list li.selected")
    page.click('#ai-recipes .preset-btn[data-id="pistol"]'); page.select_option("#ai-quality", "40"); page.select_option("#ai-count", "1")
    page.fill("#ai-extra", ""); page.click("#ai-generate-btn")
    page.wait_for_selector("#ai-results .result-card", timeout=60000)
    page.wait_for_function("document.querySelector('#ai-generate-btn').disabled === false", timeout=30000)
    check("AI result card carries the non-commercial badge", page.locator("#ai-results .result-card .badge.nc").count() == 1)
    page.locator("#ai-results .result-card button", has_text="저장").click()
    page.wait_for_function("document.querySelector('#toast').textContent.includes('비상업')", timeout=15000)
    check("saving warns about non-commercial audio", "비상업" in page.locator("#toast").text_content())
    page.click('[data-toptab="library"]'); page.wait_for_selector(".sound-item")
    check("library item has the non-commercial badge", page.locator(".sound-item .badge.nc").count() == 1)
    page.click("#export-btn")
    page.wait_for_function("document.querySelector('#export-status').textContent.includes('비상업')", timeout=15000)
    check("export status warns about non-commercial sounds", "비상업" in page.locator("#export-status").text_content())
    page.click("#delete-project-btn"); page.click("#modal-ok"); page.wait_for_timeout(500)
    page.select_option("#ai-model", "sao") if page.locator("#toptab-ai.active").count() else None

    # --- 참고 음원 학습 (2개 → 그룹 프리셋)
    page.click('[data-toptab="ai"]')
    page.fill("#learn-group", "gun_test")
    page.select_option("#learn-budget", "10")
    with page.expect_file_chooser() as fc:
        page.click("#learn-btn")
    fc.value.set_files(files)
    page.wait_for_function("document.querySelectorAll('#learn-results .result-card').length === 2", timeout=120000)
    check("learn summary reports similarity gain", "유사도" in page.locator("#learn-results .result-card").first.text_content())
    page.screenshot(path=str(OUT / "12_learn.png"), full_page=False)
    for _ in range(2):
        page.locator("#learn-results .result-card button", has_text="내 프리셋 저장").first.click()
        page.wait_for_timeout(400)
    page.locator("#learn-results .result-card button", has_text="내 프리셋 저장").nth(1).click()
    page.wait_for_timeout(500)
    page.click('[data-toptab="workshop"]')
    page.wait_for_selector(".preset-btn.user")
    check("'my presets' section appears", page.locator(".preset-section-title", has_text="내 프리셋").count() == 1)
    check("group random button appears (>=2 in group)", page.locator(".preset-btn.user", has_text="gun_test 무작위").count() == 1)
    page.click(".preset-btn.user >> text=무작위")
    page.wait_for_timeout(600)
    check("group random loads a spec (layers present)", page.locator(".layer-card").count() >= 3)
    page.screenshot(path=str(OUT / "13_my_presets.png"), full_page=False)

    # --- 설정: AI 모델 카드 (모의 모드에서는 둘 다 설치됨 → 다운로드 버튼 없음, 라이선스 표시는 있음)
    page.click('[data-toptab="settings"]')
    page.wait_for_selector("#ai-models-list .ai-model-card")
    cards = page.locator("#ai-models-list .ai-model-card")
    check("settings shows one card per model", cards.count() == 2)
    check("non-commercial model card is styled as a warning", "nc" in cards.nth(1).get_attribute("class") and "비상업" in cards.nth(1).text_content())
    check("commercial model card shows its license", "Community License" in cards.nth(0).text_content())
    check("installed models have no download button (mock)", page.locator("#ai-models-list button").count() == 0)
    check("token box hidden when nothing needs a token", not page.locator("#ai-token-row").is_visible())

    # --- 정리: 내 프리셋 삭제, 언어 전환 후 AI 탭 텍스트
    page.click('#lang-picker [data-lang="en"]'); page.wait_for_timeout(400)
    page.click('[data-toptab="ai"]'); page.wait_for_timeout(300)
    check("english AI tab", "Make realistic sounds" in page.locator("#toptab-ai .card-title").first.text_content())
    page.request.put(URL + "api/settings", data={"language": "ko"})   # 다음 테스트를 위해 한국어로 복구
    browser.close()

print("--- console/network problems:")
for e in errors:
    print("  ", e)
print("FAILURES:", fails, "| console problems:", len(errors))
sys.exit(1 if fails or errors else 0)
