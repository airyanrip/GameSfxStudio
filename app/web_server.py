"""로컬 PC 한 대에서만 쓰는 게임 효과음 제작 웹앱(FastAPI)."""
from __future__ import annotations

import math
import os
import subprocess
import threading
import time
import uuid
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import ai_manager
import ai_prompts
import cache_utils
import installer
from paths import bundled_resource, project_root
from project_store import ProjectStore, safe_filename
from settings_store import SettingsStore
from sfx import analysis, engine, presets, samples, variation
from user_presets import UserPresetStore

PROJECT_ROOT = project_root()
PROJECTS_DIR = PROJECT_ROOT / "projects"
DATA_DIR = PROJECT_ROOT / "data"
STATIC_DIR = bundled_resource("static")

store = ProjectStore(PROJECTS_DIR)
settings_store = SettingsStore(DATA_DIR / "settings.json")
samples.init(DATA_DIR / "samples")
user_presets = UserPresetStore(DATA_DIR / "user_presets.json")
installer.ensure_engine_files(PROJECT_ROOT / "engine" / "sao")  # exe 단독 배포: 번들된 워커/요구사항 파일을 풀어 둔다
ai = ai_manager.AIManager(PROJECT_ROOT / "engine" / "sao")
setup = installer.SetupManager(PROJECT_ROOT / "engine" / "sao")

app = FastAPI(title="GameSfxStudio")


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


def _sample_rate(requested: int | None) -> int:
    return requested if requested in engine.SAMPLE_RATES else settings_store.load()["sample_rate"]


# ---------------- 페이지 ----------------

@app.get("/")
def page_index():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


app.mount("/assets", StaticFiles(directory=str(STATIC_DIR)), name="assets")


# ---------------- 설정 ----------------

class UpdateSettingsPayload(BaseModel):
    language: str | None = None
    sample_rate: int | None = None
    preview_volume: float | None = None
    auto_preview: bool | None = None
    reset_browser_cache_on_next_launch: bool | None = None
    setup_seen: bool | None = None


@app.get("/api/settings")
def api_get_settings() -> dict:
    return settings_store.load()


@app.put("/api/settings")
def api_update_settings(payload: UpdateSettingsPayload):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    try:
        return settings_store.save(updates)
    except ValueError as exc:
        raise _bad_request(exc) from exc


@app.get("/api/settings/cache_info")
def api_cache_info() -> dict:
    return cache_utils.cache_info(DATA_DIR)


# ---------------- 합성 ----------------

class SpecPayload(BaseModel):
    spec: dict[str, Any]
    sample_rate: int | None = None


@app.get("/api/sfx/schema")
def api_schema() -> dict:
    return {**engine.schema(), "presets": presets.public_list()}


@app.post("/api/sfx/render")
def api_render(payload: SpecPayload):
    """spec을 WAV로 렌더해 바로 돌려준다(미리듣기·다운로드 공용)."""
    sr = _sample_rate(payload.sample_rate)
    audio = engine.render(payload.spec, sr)
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    # 브라우저가 디코딩(재샘플링)하면 피크가 달라 보일 수 있어, 실제 파일의 피크(dBFS)를 헤더로 알려준다
    peak_db = 20 * math.log10(peak) if peak > 1e-9 else -120.0
    return Response(content=engine.to_wav_bytes(audio, sr), media_type="audio/wav",
                    headers={"X-Duration": f"{len(audio) / sr:.3f}", "X-Peak-Db": f"{peak_db:.2f}",
                             "Cache-Control": "no-store"})


@app.post("/api/sfx/download")
def api_download(payload: SpecPayload, name: str = "sfx"):
    sr = _sample_rate(payload.sample_rate)
    wav, _ = engine.render_wav(payload.spec, sr)
    fname = safe_filename(name).encode("ascii", "ignore").decode() or "sfx"
    return Response(content=wav, media_type="audio/wav", headers={
        "Content-Disposition": f"attachment; filename=\"{fname}.wav\"; filename*=UTF-8''{_quote(safe_filename(name))}.wav"})


def _quote(s: str) -> str:
    from urllib.parse import quote
    return quote(s, safe="")


class RandomPayload(BaseModel):
    category: str | None = None
    seed: int | None = None
    amount: float = 0.6


@app.post("/api/sfx/randomize")
def api_randomize(payload: RandomPayload):
    category, spec = variation.randomize(payload.category, payload.seed, payload.amount)
    return {"category": category, "spec": spec}


class MutatePayload(BaseModel):
    spec: dict[str, Any]
    amount: float = 0.4
    count: int = Field(8, ge=1, le=24)


@app.post("/api/sfx/mutate")
def api_mutate(payload: MutatePayload):
    return {"spec": variation.mutate(payload.spec, payload.amount)}


@app.post("/api/sfx/variations")
def api_variations(payload: MutatePayload):
    return {"specs": variation.variations(payload.spec, payload.count, payload.amount)}


class TextPayload(BaseModel):
    text: str


@app.post("/api/sfx/from_text")
def api_from_text(payload: TextPayload):
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="만들고 싶은 소리를 설명해주세요. 예: 큰 폭발음")
    return variation.from_text(payload.text)


# ---------------- 프로젝트 ----------------

class CreateProjectPayload(BaseModel):
    name: str
    description: str = ""


class UpdateProjectPayload(BaseModel):
    description: str | None = None
    export_dir: str | None = None


@app.get("/api/projects")
def api_list_projects():
    return store.list_projects()


@app.post("/api/projects")
def api_create_project(payload: CreateProjectPayload):
    try:
        return store.create_project(payload.name, payload.description)
    except ValueError as exc:
        raise _bad_request(exc) from exc


@app.get("/api/projects/{name}")
def api_get_project(name: str):
    try:
        return store.load_project(name)
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc


@app.put("/api/projects/{name}")
def api_update_project(name: str, payload: UpdateProjectPayload):
    try:
        return store.update_project(name, payload.description, payload.export_dir)
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc


@app.delete("/api/projects/{name}")
def api_delete_project(name: str):
    try:
        store.delete_project(name)
    except ValueError as exc:
        raise _bad_request(exc) from exc
    return {"ok": True}


# ---------------- 저장된 효과음 ----------------

class SaveSoundPayload(BaseModel):
    name: str
    spec: dict[str, Any]
    category: str = ""
    tags: list[str] = []
    sound_id: str | None = None  # 있으면 덮어쓰기


class RenamePayload(BaseModel):
    name: str


@app.get("/api/projects/{name}/sounds")
def api_list_sounds(name: str):
    try:
        return store.list_sounds(name)
    except ValueError as exc:
        raise _bad_request(exc) from exc


@app.post("/api/projects/{name}/sounds")
def api_save_sound(name: str, payload: SaveSoundPayload):
    try:
        return store.save_sound(name, payload.name, payload.spec, settings_store.load()["sample_rate"],
                                payload.category, payload.tags, payload.sound_id)
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc


@app.get("/api/projects/{name}/sounds/{sound_id}")
def api_get_sound(name: str, sound_id: str):
    try:
        return store.get_sound(name, sound_id)
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc


@app.put("/api/projects/{name}/sounds/{sound_id}")
def api_rename_sound(name: str, sound_id: str, payload: RenamePayload):
    try:
        return store.rename_sound(name, sound_id, payload.name)
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc


@app.delete("/api/projects/{name}/sounds/{sound_id}")
def api_delete_sound(name: str, sound_id: str):
    try:
        store.delete_sound(name, sound_id)
    except ValueError as exc:
        raise _bad_request(exc) from exc
    return {"ok": True}


@app.get("/api/projects/{name}/sounds/{sound_id}/audio")
def api_sound_audio(name: str, sound_id: str):
    try:
        path = store.sound_wav_path(name, sound_id)
    except ValueError as exc:
        raise _bad_request(exc) from exc
    if not path.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    return FileResponse(path, media_type="audio/wav")


# ---------------- 내보내기 ----------------

class ExportPayload(BaseModel):
    dir: str | None = None


@app.post("/api/projects/{name}/export")
def api_export(name: str, payload: ExportPayload):
    """저장된 효과음을 '효과음 이름.wav'로 폴더에 복사한다(Unity Assets 등에 바로 넣기 좋게)."""
    try:
        result = store.export_to_folder(name, payload.dir)
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except (ValueError, OSError) as exc:
        raise _bad_request(exc) from exc
    if payload.dir is not None and payload.dir.strip():
        store.update_project(name, export_dir=payload.dir)
    return result


@app.get("/api/projects/{name}/export.zip")
def api_export_zip(name: str):
    try:
        data = store.export_zip(name)
    except (FileNotFoundError, ValueError) as exc:
        raise _bad_request(exc) from exc
    return Response(content=data, media_type="application/zip", headers={
        "Content-Disposition": f"attachment; filename=\"sfx_pack.zip\"; filename*=UTF-8''{_quote(safe_filename(name))}.zip"})


class OpenFolderPayload(BaseModel):
    dir: str | None = None


@app.post("/api/projects/{name}/open_folder")
def api_open_folder(name: str, payload: OpenFolderPayload):
    try:
        proj = store.load_project(name)
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc
    target = (payload.dir or proj.get("export_dir") or "").strip()
    folder = target and os.path.isdir(target) and target or str(store.project_dir(name) / "sounds")
    subprocess.Popen(["explorer", os.path.normpath(folder)])
    return {"dir": folder}


# ---------------- 샘플(녹음 조각) ----------------

MAX_UPLOAD_BYTES = 40 * 1024 * 1024


@app.post("/api/samples")
async def api_upload_sample(request: Request):
    """브라우저가 디코딩해 보낸 모노 WAV를 저장한다(mp3/mp4/ogg 등은 화면에서 WAV로 변환해 올린다)."""
    data = await request.body()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="파일이 너무 큽니다(최대 40MB).")
    try:
        return samples.save(data)
    except ValueError as exc:
        raise _bad_request(exc) from exc


@app.get("/api/samples/{sample_id}/info")
def api_sample_info(sample_id: str):
    info = samples.info(sample_id) if samples.valid_id(sample_id) else None
    if info is None:
        raise HTTPException(status_code=404, detail="샘플을 찾을 수 없습니다.")
    return info


@app.get("/api/samples/{sample_id}")
def api_get_sample(sample_id: str):
    if not samples.valid_id(sample_id) or samples.info(sample_id) is None:
        raise HTTPException(status_code=404, detail="샘플을 찾을 수 없습니다.")
    return FileResponse(DATA_DIR / "samples" / f"{sample_id}.wav", media_type="audio/wav")


# ---------------- 참고 음원에서 배우기 ----------------

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


class LearnPayload(BaseModel):
    sample_id: str
    budget: float = Field(20.0, ge=3, le=90)
    seed: int = 1


def _run_learn(job_id: str, sample_id: str, budget: float, seed: int) -> None:
    job = _jobs[job_id]
    try:
        got = samples.get(sample_id)
        if got is None:
            raise ValueError("샘플을 찾을 수 없습니다.")
        x, sr = got

        def progress(frac: float, loss: float) -> None:
            job["progress"], job["loss"] = round(frac, 3), round(loss, 4)

        result = analysis.fit(x, sr, budget_s=budget, seed=seed, progress=progress)
        job.update(status="done", progress=1.0, result=result)
    except Exception as exc:  # noqa: BLE001 - 작업 실패는 화면에 메시지로 전달
        job.update(status="error", error=str(exc))


@app.post("/api/learn")
def api_learn(payload: LearnPayload):
    if not samples.valid_id(payload.sample_id) or samples.info(payload.sample_id) is None:
        raise HTTPException(status_code=404, detail="샘플을 찾을 수 없습니다.")
    job_id = uuid.uuid4().hex[:10]
    with _jobs_lock:
        for jid in [j for j, v in _jobs.items() if time.time() - v["started"] > 3600]:
            _jobs.pop(jid, None)  # 오래된 작업 정리
        _jobs[job_id] = {"status": "running", "progress": 0.0, "loss": None, "started": time.time()}
    threading.Thread(target=_run_learn, args=(job_id, payload.sample_id, payload.budget, payload.seed),
                     daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/learn/{job_id}")
def api_learn_status(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return {k: v for k, v in job.items() if k != "started"}


# ---------------- 내 프리셋 ----------------

class UserPresetPayload(BaseModel):
    name: str
    spec: dict[str, Any]
    group: str = ""
    note: str = ""


@app.get("/api/user_presets")
def api_list_user_presets():
    return user_presets.list()


@app.post("/api/user_presets")
def api_add_user_preset(payload: UserPresetPayload):
    try:
        return user_presets.add(payload.name, payload.spec, payload.group, payload.note)
    except ValueError as exc:
        raise _bad_request(exc) from exc


@app.delete("/api/user_presets/{preset_id}")
def api_delete_user_preset(preset_id: str):
    user_presets.delete(preset_id)
    return {"ok": True}


# ---------------- AI 효과음 생성 (Stable Audio Open) ----------------

_ai_jobs: dict[str, dict] = {}


@app.on_event("shutdown")
def _on_shutdown() -> None:
    ai.stop_worker()  # VRAM 반환


@app.get("/api/ai/status")
def api_ai_status():
    return ai.status()


@app.get("/api/ai/recipes")
def api_ai_recipes():
    return ai_prompts.public_recipes()


class AIDownloadPayload(BaseModel):
    model: str = "sao"
    token: str = ""


@app.post("/api/ai/download")
def api_ai_download(payload: AIDownloadPayload):
    try:
        ai.start_download(payload.model, payload.token)
    except ai_manager.AIError as exc:
        raise _bad_request(exc) from exc
    return {"ok": True}


@app.post("/api/ai/stop")
def api_ai_stop():
    ai.stop_worker()
    return {"ok": True}


class AIGeneratePayload(BaseModel):
    model: str = "sao"
    recipe: str = ""
    env: str = ""
    distance: str = ""
    extra: str = Field("", max_length=300)
    prompt: str = Field("", max_length=400)      # 직접 쓴 영어 프롬프트(있으면 recipe/extra 대신 사용)
    seconds: float = Field(3.0, ge=0.5, le=12.0)
    steps: int = Field(80, ge=10, le=200)
    guidance: float = Field(0.0, ge=0.0, le=15.0)  # 0이면 모델 권장값
    seed: int = 0                                 # 0이면 무작위
    count: int = Field(2, ge=1, le=4)


def _run_ai_job(job_id: str, req: AIGeneratePayload) -> None:
    job = _ai_jobs[job_id]
    try:
        prompt = req.prompt.strip() or ai_prompts.build_prompt(req.recipe, req.env, req.distance, req.extra)
        job["prompt"] = prompt
        model_info = ai_manager.MODELS[req.model]
        seconds = min(req.seconds, model_info["max_seconds"])
        base_seed = req.seed or int(time.time()) % 1_000_000
        for i in range(req.count):
            job["index"] = i
            seed = base_seed + i
            wav = ai.generate(req.model, prompt, ai_prompts.NEGATIVE, seconds, req.steps, req.guidance, seed)
            audio, sr = samples.decode_stereo(wav)
            audio = ai_manager.trim_generated(audio, sr)
            mono = audio.mean(axis=1) if audio.ndim == 2 else audio
            peak = float(np.max(np.abs(mono))) or 1.0
            # 비상업 모델의 결과물은 샘플에 nc(비상업) 표시를 남겨, 이후 이 샘플을 쓴 효과음까지 자동으로 표시된다
            info = samples.save(samples.encode_wav(mono / peak * 0.9, sr), {
                "source": "ai", "model": req.model, "license": "sao-community" if model_info["commercial"] else "nc"})
            job["results"].append({**info, "seed": seed})
        job["status"] = "done"
    except ai_manager.AIError as exc:
        job.update(status="error", error=str(exc))
    except Exception as exc:  # noqa: BLE001
        job.update(status="error", error=f"예상하지 못한 오류: {exc}")


@app.post("/api/ai/generate")
def api_ai_generate(payload: AIGeneratePayload):
    st = ai.status()
    if payload.model not in ai_manager.MODELS:
        raise HTTPException(status_code=400, detail=f"알 수 없는 모델입니다: {payload.model}")
    if not st["installed"]:
        raise HTTPException(status_code=409, detail="AI 엔진이 설치되지 않았습니다. engine\sao\setup_ai.bat 을 실행하세요.")
    if not ai.model_ready(payload.model):
        raise HTTPException(status_code=409, detail=f"{ai_manager.MODELS[payload.model]['name']} 모델이 아직 없습니다. 설정 탭에서 내려받으세요.")
    if not (payload.recipe or payload.prompt.strip() or payload.extra.strip()):
        raise HTTPException(status_code=400, detail="만들 소리의 종류를 고르거나 설명을 적어주세요.")
    if any(j["status"] == "running" for j in _ai_jobs.values()):
        raise HTTPException(status_code=409, detail="이미 생성 중입니다. 끝난 뒤 다시 시도하세요.")
    job_id = uuid.uuid4().hex[:10]
    _ai_jobs[job_id] = {"status": "running", "model": payload.model, "index": 0, "count": payload.count,
                        "results": [], "prompt": "", "noncommercial": not ai_manager.MODELS[payload.model]["commercial"]}
    threading.Thread(target=_run_ai_job, args=(job_id, payload), daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/ai/jobs/{job_id}")
def api_ai_job(job_id: str):
    job = _ai_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return {**job, "worker": ai.progress()}


# ---------------- 설치 도우미 (첫 실행) ----------------

@app.get("/api/setup/status")
def api_setup_status():
    return setup.status()


class SetupInstallPayload(BaseModel):
    install_python: bool = False  # Python이 없을 때 자동 설치에 동의했는가


@app.post("/api/setup/install_engine")
def api_setup_install_engine(payload: SetupInstallPayload):
    """AI 엔진 설치 시작. 화면에서 사용자가 확인 창에서 동의한 뒤에만 호출된다."""
    try:
        setup.start_engine_install(payload.install_python)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True}


@app.post("/api/setup/cancel")
def api_setup_cancel():
    setup.cancel()
    return {"ok": True}
