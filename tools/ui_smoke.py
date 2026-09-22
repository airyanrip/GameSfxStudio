"""브라우저(Edge) 스모크 테스트: 실제 UI를 조작하며 콘솔 오류를 수집하고 스크린샷을 남긴다.

사용: uv run --with playwright python tools/ui_smoke.py <스크린샷 폴더>
서버(127.0.0.1:8878)가 켜져 있어야 한다. 임시 프로젝트를 만들고 끝에 지운다.
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8878/"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
OUT.mkdir(parents=True, exist_ok=True)
errors: list[str] = []
fails = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global fails
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    fails += 0 if cond else 1


with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="msedge", headless=True, args=["--autoplay-policy=no-user-gesture-required"])
    page = browser.new_page(viewport={"width": 1320, "height": 900})
    page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("requestfailed", lambda r: errors.append(f"requestfailed: {r.url}"))
    page.on("response", lambda r: errors.append(f"HTTP {r.status}: {r.url}") if r.status >= 400 else None)

    page.request.put(URL + "api/settings", data={"language": "ko", "setup_seen": True})  # 첫 실행 마법사가 가리지 않게
    page.goto(URL)
    page.wait_for_selector(".preset-btn")
    page.wait_for_function("document.querySelector('#sound-info').textContent.includes('Hz')")
    check("presets rendered (36)", page.locator("#preset-grid .preset-btn:not(.user)").count() == 36)
    check("layers rendered", page.locator(".layer-card").count() >= 1)
    check("waveform canvas has ink", page.evaluate("""() => {
        const c = document.querySelector('#wave-canvas'); const d = c.getContext('2d').getImageData(0,0,c.width,c.height).data;
        let n = 0; for (let i = 3; i < d.length; i += 4) if (d[i] > 0) n++; return n > 200; }"""))
    check("spectrogram has colour", page.evaluate("""() => {
        const c = document.querySelector('#spec-canvas'); const d = c.getContext('2d').getImageData(0,0,c.width,c.height).data;
        let bright = 0; for (let i = 0; i < d.length; i += 4) if (d[i] > 150) bright++; return bright > 100; }"""))
    page.screenshot(path=str(OUT / "01_workshop_coin.png"))

    # 프리셋 전환 → 렌더 갱신
    before = page.locator("#sound-info").text_content()
    page.click('.preset-btn[data-id="explosion"]')
    page.wait_for_function("(b) => document.querySelector('#sound-info').textContent !== b", arg=before)
    check("explosion preset has 3 layers", page.locator(".layer-card").count() == 3)
    check("explosion preset highlighted", page.locator('#preset-grid .preset-btn.active').get_attribute("data-id") == "explosion")

    # 슬라이더 조작 → 값 표시/렌더 변화
    info = page.locator("#sound-info").text_content()
    first_range = page.locator(".layer-card").first.locator("input[type=range]").first
    first_range.evaluate("(el) => { el.value = 900; el.dispatchEvent(new Event('input', {bubbles:true})); el.dispatchEvent(new Event('change', {bubbles:true})); }")
    page.wait_for_timeout(500)
    check("slider marks row as changed", page.locator(".layer-card").first.locator(".param-row.changed").count() >= 1)
    check("undo enabled after edits", not page.locator("#undo-btn").is_disabled())
    page.click("#undo-btn")
    page.wait_for_timeout(500)

    # 파형을 noise로 바꾸면 pitch 그룹이 사라지고 noise_color가 나타남
    layer = page.locator(".layer-card").nth(1)
    layer.locator("select").first.select_option("sine")
    check("sine layer shows FM depth", layer.locator("text=FM 깊이").count() == 1 or page.locator(".layer-card").nth(1).locator("text=FM").count() >= 1)
    page.locator(".layer-card").nth(1).locator("select").first.select_option("noise")
    check("noise layer hides pitch group", page.locator(".layer-card").nth(1).locator(".param-group-title", has_text="음높이").count() == 0)

    # 설명으로 만들기
    page.fill("#prompt-text", "큰 폭발음 동굴에서")
    page.click("#prompt-btn")
    page.wait_for_function("document.querySelector('#prompt-note').textContent.includes('폭발')")
    check("prompt note names matched preset", "폭발" in page.locator("#prompt-note").text_content())

    # 랜덤 / 변형 / 변형 8개
    page.click("#random-btn")
    page.wait_for_timeout(400)
    page.click("#mutate-btn")
    page.wait_for_timeout(400)
    page.click("#variations-btn")
    page.wait_for_selector(".var-card")
    page.wait_for_timeout(800)
    check("8 variation cards", page.locator(".var-card").count() == 8)
    page.screenshot(path=str(OUT / "02_variations.png"), full_page=False)

    # 프로젝트 없이 저장 → 안내 토스트
    page.click("#save-new-btn")
    check("save without project shows hint", "프로젝트" in page.locator("#toast").text_content())

    # 프로젝트 생성(모달) → 저장 → 라이브러리
    page.click("#new-project-btn")
    page.fill("#modal-input", "__ui_selftest__")
    page.keyboard.press("Enter")
    page.wait_for_selector("#project-list li.selected")
    page.click('.preset-btn[data-id="coin"]')
    page.wait_for_timeout(300)
    check("default name coin_01", page.input_value("#sfx-name") == "coin_01")
    page.click("#save-new-btn")
    page.wait_for_function("document.querySelector('#toast').textContent.includes('coin_01')")
    page.wait_for_selector("#save-over-btn", state="visible", timeout=10000)
    check("overwrite button appears after save", page.locator("#save-over-btn").is_visible())
    page.click("#save-over-btn")
    page.wait_for_timeout(400)
    page.click('.preset-btn[data-id="coin"]')
    page.wait_for_timeout(300)
    check("next default name coin_02", page.input_value("#sfx-name") == "coin_02")

    page.click('[data-toptab="library"]')
    page.wait_for_selector(".sound-item")
    check("library lists 1 sound", page.locator(".sound-item").count() == 1)
    page.screenshot(path=str(OUT / "03_library.png"))
    page.locator(".sound-item button", has_text="이름 변경").click()
    page.fill("#modal-input", "coin_big")
    page.keyboard.press("Enter")
    page.wait_for_function("document.querySelector('.s-name').textContent === 'coin_big'")
    page.locator(".sound-item button", has_text="편집").click()
    page.wait_for_selector("#toptab-workshop.active")
    check("edit loads sound into workshop", page.input_value("#sfx-name") == "coin_big")

    # 설정 / 언어 전환
    page.click('[data-toptab="settings"]')
    page.click('#lang-picker [data-lang="en"]')
    page.wait_for_timeout(300)
    check("english UI", "Sound workshop" in page.locator('[data-toptab="workshop"]').text_content())
    page.screenshot(path=str(OUT / "04_settings_en.png"))
    page.click('[data-toptab="workshop"]')
    page.wait_for_timeout(300)
    check("english layer titles", "Layer 1" in page.locator(".layer-title").first.text_content())
    page.screenshot(path=str(OUT / "05_workshop_en.png"), full_page=True)
    page.click('[data-toptab="settings"]')
    page.click('#lang-picker [data-lang="ko"]')

    # 정리: 프로젝트 삭제
    page.click("#delete-project-btn")
    page.click("#modal-ok")
    page.wait_for_timeout(500)
    check("project deleted from sidebar", page.locator("#project-list li.selected").count() == 0)

    browser.close()

print("--- console/network problems:")
for e in errors:
    print("  ", e)
print("FAILURES:", fails, "| console problems:", len(errors))
sys.exit(1 if fails or errors else 0)
