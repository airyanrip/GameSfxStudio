"""첫 실행 설치 도우미 UI 점검 — 서버를 GAMESFX_SETUP_DRYRUN=nopython 으로 켜고(실제 설치 없음) 실행한다.

사용: uv run --with playwright python tools/ui_setup_smoke.py <스크린샷 폴더>
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8878/"
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
errors = []
fails = 0


def check(name, cond, extra=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    fails += 0 if cond else 1


with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True, args=["--autoplay-policy=no-user-gesture-required"])
    page = b.new_page(viewport={"width": 1320, "height": 1000})
    page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("response", lambda r: errors.append(f"HTTP {r.status}: {r.url}") if r.status >= 400 else None)
    install_requests = []
    page.on("request", lambda r: install_requests.append(r.url) if "install_engine" in r.url else None)

    page.request.put(URL + "api/settings", data={"language": "ko", "setup_seen": False})
    page.goto(URL)
    page.wait_for_selector("#setup-modal", state="visible", timeout=15000)
    check("wizard opens automatically on first run", page.locator("#setup-modal").is_visible())
    page.wait_for_selector(".setup-card")
    check("three sections shown (basics / engine / models)", page.locator(".setup-card").count() == 3)
    check("basics card says nothing to install", "추가 설치 없음" in page.locator(".setup-card").first.text_content())
    txt = page.locator("#setup-body").text_content()
    check("GPU line, Python line and disk line are present", "NVIDIA" in txt and "Python" in txt and "디스크 여유" in txt)
    check("missing python is explained with size + signature", "서명" in txt and "25MB" in txt)
    page.screenshot(path=str(OUT / "30_wizard_first_run.png"))

    # 동의 없이 설치 → 거부(요청 자체가 나가면 안 됨)
    page.click('#setup-body button:text-is("AI 엔진 설치")')
    page.wait_for_selector("#toast.error")
    check("install refused without python consent (toast)", "동의" in page.locator("#toast").text_content())
    check("no install request was sent", len(install_requests) == 0)

    # 동의 후 → 확인 창 → 취소
    page.check("#setup-allow-python")
    page.click('#setup-body button:text-is("AI 엔진 설치")')
    page.wait_for_selector("#modal", state="visible")
    body = page.locator("#modal-body").text_content()
    check("confirm dialog lists python + venv + torch + libraries",
          all(k in body for k in ("Python 3.11", "가상환경", "PyTorch", "diffusers", "취소할 수")), body[:120])
    page.screenshot(path=str(OUT / "31_wizard_confirm.png"))
    page.click("#modal-cancel")
    page.wait_for_timeout(300)
    check("cancelling the confirm dialog sends nothing", len(install_requests) == 0)

    # 진짜 시작 → 진행 표시 → 취소
    page.click('#setup-body button:text-is("AI 엔진 설치")')
    page.click("#modal-ok")
    page.wait_for_selector(".setup-card .progress", timeout=10000)
    page.wait_for_function("document.querySelector('.setup-log') && document.querySelector('.setup-log').textContent.includes('(시험)')", timeout=10000)
    check("progress bar, step label and live log are shown",
          "[" in page.locator("#setup-body").text_content() and page.locator(".setup-log").count() == 1)
    page.screenshot(path=str(OUT / "32_wizard_running.png"))
    page.click('#setup-body button:text-is("취소")')
    page.wait_for_function("document.querySelector('#setup-body').textContent.includes('취소했어요')", timeout=10000)
    check("cancel stops the install and offers retry", page.locator('#setup-body button:text-is("다시 시도")').count() == 1)

    # 재시도 → 완료
    if page.locator("#setup-allow-python").count():
        page.check("#setup-allow-python")
    page.click('#setup-body button:text-is("다시 시도")')
    page.click("#modal-ok")
    page.wait_for_function("document.querySelector('#setup-body').textContent.includes('설치가 끝났어요')", timeout=30000)
    done_text = page.locator("#setup-body").text_content()
    check("install completes; engine shown as installed; no install button",
          "AI 엔진이 설치되어 있습니다" in done_text and page.locator('#setup-body button:text-is("AI 엔진 설치")').count() == 0)
    page.screenshot(path=str(OUT / "33_wizard_done.png"))

    # 닫기 → 다시 자동으로 안 뜸, 설정에서 다시 열 수 있음
    page.click("#setup-close")
    check("wizard closes", not page.locator("#setup-modal").is_visible())
    page.reload()
    page.wait_for_selector(".preset-btn")
    page.wait_for_timeout(1500)
    check("wizard does not reopen on the next launch", not page.locator("#setup-modal").is_visible())
    page.click('[data-toptab="settings"]')
    page.click("#open-setup-btn")
    check("wizard can be reopened from Settings", page.locator("#setup-modal").is_visible())
    page.click("#setup-close")

    # English
    page.request.put(URL + "api/settings", data={"language": "en"})
    page.reload()
    page.wait_for_selector(".preset-btn")
    page.click('[data-toptab="settings"]')
    page.click("#open-setup-btn")
    page.wait_for_selector(".setup-card")
    check("english wizard", "First-run setup" in page.locator("#setup-modal .modal-title").text_content()
          and "nothing to install" in page.locator(".setup-card").first.text_content())
    page.click("#setup-close")
    page.request.put(URL + "api/settings", data={"language": "ko", "setup_seen": True})
    b.close()

print("--- console/network problems:")
for e in errors:
    print("  ", e)
print("FAILURES:", fails, "| console problems:", len(errors))
sys.exit(1 if fails or errors else 0)
