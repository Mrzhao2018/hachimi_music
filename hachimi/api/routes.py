"""API route handlers."""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from hachimi.core.config import get_config, save_config
from hachimi.core.pipeline import MusicPipeline
from hachimi.core.project import ProjectManager
from hachimi.core.schemas import (
    AudioResult,
    MusicRequest,
    MusicStyle,
    OutputFormat,
    TaskInfo,
    TaskStatus,
)
from hachimi.core.version import VersionManager

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory task store (use Redis/DB for production)
_tasks: dict[str, TaskInfo] = {}
_results: dict[str, AudioResult] = {}
_executor = ThreadPoolExecutor(max_workers=2)
_project_mgr = ProjectManager()
_version_mgr = VersionManager()


# ── Request/Response Models ───────────────────────────────────────────────

class GenerateRequest(BaseModel):
    """API request to generate music."""
    prompt: str = Field(..., min_length=1, max_length=2000)
    style: MusicStyle = MusicStyle.CLASSICAL
    key: str = "C"
    time_signature: str = "4/4"
    tempo: int = Field(default=120, ge=30, le=300)
    measures: int = Field(default=16, ge=4, le=64)
    instruments: list[str] = Field(default_factory=lambda: ["piano"])
    output_format: OutputFormat = OutputFormat.MP3


class GenerateResponse(BaseModel):
    """Response after submitting a generation request."""
    task_id: str
    status: TaskStatus
    message: str


class TaskStatusResponse(BaseModel):
    """Task status query response."""
    task_id: str
    status: TaskStatus
    progress_message: str = ""
    result: Optional[AudioResult] = None


# ── Background Task Runner ────────────────────────────────────────────────

def _run_pipeline(task_id: str, request: MusicRequest):
    """Run the music pipeline in a background thread."""
    config = get_config()
    pipeline = MusicPipeline(config)

    def progress_callback(status: TaskStatus, message: str):
        if task_id in _tasks:
            _tasks[task_id].status = status
            _tasks[task_id].progress_message = message

    result = pipeline.generate(
        request=request,
        task_id=task_id,
        progress_callback=progress_callback,
    )

    _results[task_id] = result
    if task_id in _tasks:
        _tasks[task_id].status = result.status
        _tasks[task_id].result = result
        if result.error_message:
            _tasks[task_id].progress_message = f"Error: {result.error_message}"


# ── Routes ────────────────────────────────────────────────────────────────

@router.post("/suggest-params")
async def suggest_params(body: dict):
    """Use AI to suggest musical parameters based on a description."""
    prompt = body.get("prompt", "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    try:
        from hachimi.generation.llm_generator import LLMGenerator
        gen = LLMGenerator()
        params = gen.suggest_params(prompt)
        return params
    except Exception as e:
        logger.error("suggest_params failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate", response_model=GenerateResponse)
async def generate_music(
    req: GenerateRequest,
    background_tasks: BackgroundTasks,
):
    """
    Submit a music generation request.

    Returns a task_id that can be used to check progress and retrieve results.
    """
    music_request = MusicRequest(
        prompt=req.prompt,
        style=req.style,
        key=req.key,
        time_signature=req.time_signature,
        tempo=req.tempo,
        measures=req.measures,
        instruments=req.instruments,
        output_format=req.output_format,
    )

    import uuid
    from datetime import datetime

    task_id = str(uuid.uuid4())
    task_info = TaskInfo(
        task_id=task_id,
        status=TaskStatus.PENDING,
        created_at=datetime.now(),
        progress_message="Task submitted, waiting to start...",
    )
    _tasks[task_id] = task_info

    # Run pipeline in background
    loop = asyncio.get_event_loop()
    loop.run_in_executor(_executor, _run_pipeline, task_id, music_request)

    return GenerateResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        message="Music generation started. Use /api/status/{task_id} to check progress.",
    )


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """Check the status of a generation task."""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = _tasks[task_id]
    return TaskStatusResponse(
        task_id=task.task_id,
        status=task.status,
        progress_message=task.progress_message,
        result=task.result,
    )


@router.get("/result/{task_id}")
async def get_result(task_id: str):
    """Get the completed result of a generation task."""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = _tasks[task_id]
    if task.status == TaskStatus.FAILED:
        raise HTTPException(
            status_code=500,
            detail=f"Task failed: {task.progress_message}",
        )
    if task.status != TaskStatus.COMPLETED:
        raise HTTPException(
            status_code=202,
            detail=f"Task still in progress: {task.status.value}",
        )

    result = _results.get(task_id)
    if not result or not result.audio_path:
        raise HTTPException(status_code=500, detail="Result not available")

    return result


@router.get("/download/{task_id}")
async def download_audio(task_id: str):
    """Download the generated audio file."""
    if task_id not in _results:
        raise HTTPException(status_code=404, detail="Result not found")

    result = _results[task_id]
    if not result.audio_path:
        raise HTTPException(status_code=404, detail="Audio file not found")

    from pathlib import Path
    audio_path = Path(result.audio_path)
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found on disk")

    media_type = "audio/mpeg" if audio_path.suffix == ".mp3" else "audio/wav"
    filename = f"{result.score.title if result.score else 'music'}{audio_path.suffix}"

    return FileResponse(
        path=str(audio_path),
        media_type=media_type,
        filename=filename,
    )


@router.get("/score/{task_id}")
async def get_score(task_id: str):
    """Get the ABC notation score for a completed task."""
    if task_id not in _results:
        raise HTTPException(status_code=404, detail="Result not found")

    result = _results[task_id]
    if not result.score:
        raise HTTPException(status_code=404, detail="Score not available")

    return {
        "task_id": task_id,
        "title": result.score.title,
        "abc_notation": result.score.abc_notation,
        "instruments": [inst.model_dump() for inst in result.score.instruments],
        "key": result.score.key,
        "time_signature": result.score.time_signature,
        "tempo": result.score.tempo,
        "description": result.score.description,
    }


@router.get("/tasks")
async def list_tasks():
    """List all tasks (most recent first)."""
    tasks = sorted(
        _tasks.values(),
        key=lambda t: t.created_at,
        reverse=True,
    )
    return [
        {
            "task_id": t.task_id,
            "status": t.status,
            "created_at": t.created_at.isoformat(),
            "progress_message": t.progress_message,
        }
        for t in tasks[:50]
    ]


# ── Settings / Config Routes ─────────────────────────────────────────────


@router.get("/models")
async def list_models():
    """Fetch available models from the configured OpenAI-compatible API."""
    import httpx

    config = get_config()
    api_key = config.get_ai_api_key()
    base_url = config.ai.base_url.rstrip("/")

    if not api_key:
        raise HTTPException(status_code=400, detail="API Key 未配置，无法获取模型列表")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            headers = {"Authorization": f"Bearer {api_key}"}
            resp = await client.get(f"{base_url}/models", headers=headers)
            resp.raise_for_status()
            data = resp.json()

        models = []
        for m in data.get("data", []):
            model_id = m.get("id", "")
            if model_id:
                models.append({
                    "id": model_id,
                    "owned_by": m.get("owned_by", ""),
                })

        # Sort alphabetically
        models.sort(key=lambda x: x["id"])
        return {"models": models, "count": len(models)}

    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"API 返回错误: {e.response.status_code} - {e.response.text[:200]}",
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"无法连接 API: {e}")


class AISettingsRequest(BaseModel):
    """Request to update AI settings."""
    base_url: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    temperature: Optional[float] = None


class SynthesisSettingsRequest(BaseModel):
    """Request to update synthesis settings."""
    soundfont: Optional[str] = None
    sample_rate: Optional[int] = None
    output_format: Optional[str] = None


class PostprocessSettingsRequest(BaseModel):
    """Request to update post-processing settings."""
    reverb: Optional[bool] = None
    reverb_room_size: Optional[float] = None
    normalize: Optional[bool] = None
    fade_in_ms: Optional[int] = None
    fade_out_ms: Optional[int] = None


class SettingsUpdateRequest(BaseModel):
    """Full settings update request."""
    ai: Optional[AISettingsRequest] = None
    synthesis: Optional[SynthesisSettingsRequest] = None
    postprocess: Optional[PostprocessSettingsRequest] = None


@router.get("/settings")
async def get_settings():
    """Get current application settings (API key is masked)."""
    config = get_config()
    api_key = config.get_ai_api_key()
    masked_key = ""
    if api_key:
        if len(api_key) > 8:
            masked_key = api_key[:4] + "****" + api_key[-4:]
        else:
            masked_key = "****"

    # List available soundfonts
    sf_dir = config.resolve_path(config.paths.soundfonts_dir)
    soundfonts = []
    if sf_dir.exists():
        for f in sorted(sf_dir.glob("*.sf2")):
            soundfonts.append(f.name)
        for f in sorted(sf_dir.glob("*.sf3")):
            soundfonts.append(f.name)

    return {
        "ai": {
            "base_url": config.ai.base_url,
            "model": config.ai.model,
            "api_key_set": bool(api_key),
            "api_key_masked": masked_key,
            "temperature": config.ai.temperature,
            "max_retries": config.ai.max_retries,
        },
        "synthesis": {
            "soundfont": config.synthesis.soundfont,
            "sample_rate": config.synthesis.sample_rate,
            "output_format": config.synthesis.output_format,
            "available_soundfonts": soundfonts,
        },
        "postprocess": {
            "reverb": config.postprocess.reverb,
            "reverb_room_size": config.postprocess.reverb_room_size,
            "normalize": config.postprocess.normalize,
            "fade_in_ms": config.postprocess.fade_in_ms,
            "fade_out_ms": config.postprocess.fade_out_ms,
        },
    }


@router.put("/settings")
async def update_settings(req: SettingsUpdateRequest):
    """Update application settings at runtime."""
    config = get_config()

    if req.ai:
        if req.ai.base_url is not None:
            config.ai.base_url = req.ai.base_url
        if req.ai.model is not None:
            config.ai.model = req.ai.model
        if req.ai.api_key is not None:
            config.ai.api_key = req.ai.api_key
        if req.ai.temperature is not None:
            config.ai.temperature = req.ai.temperature

    if req.synthesis:
        if req.synthesis.soundfont is not None:
            config.synthesis.soundfont = req.synthesis.soundfont
        if req.synthesis.sample_rate is not None:
            config.synthesis.sample_rate = req.synthesis.sample_rate
        if req.synthesis.output_format is not None:
            config.synthesis.output_format = req.synthesis.output_format

    if req.postprocess:
        if req.postprocess.reverb is not None:
            config.postprocess.reverb = req.postprocess.reverb
        if req.postprocess.reverb_room_size is not None:
            config.postprocess.reverb_room_size = req.postprocess.reverb_room_size
        if req.postprocess.normalize is not None:
            config.postprocess.normalize = req.postprocess.normalize
        if req.postprocess.fade_in_ms is not None:
            config.postprocess.fade_in_ms = req.postprocess.fade_in_ms
        if req.postprocess.fade_out_ms is not None:
            config.postprocess.fade_out_ms = req.postprocess.fade_out_ms

    # Persist to settings.yaml so config survives restart / page refresh
    try:
        save_config(config)
        logger.info("Settings saved to config/settings.yaml")
    except Exception as e:
        logger.error("Failed to save settings to file: %s", e)

    return {"message": "Settings updated", "settings": await get_settings()}


# ── Project CRUD Routes ──────────────────────────────────────────────────


class CreateProjectRequest(BaseModel):
    """Request to create a new project."""
    name: str = Field(default="新项目", max_length=200)
    prompt: str = Field(..., min_length=1, max_length=2000)
    style: MusicStyle = MusicStyle.CLASSICAL
    key: str = "C"
    time_signature: str = "4/4"
    tempo: int = Field(default=120, ge=30, le=300)
    measures: int = Field(default=16, ge=4, le=64)
    instruments: list[str] = Field(default_factory=lambda: ["piano"])
    output_format: OutputFormat = OutputFormat.MP3


@router.get("/projects")
async def list_projects():
    """List all projects."""
    return {"projects": _project_mgr.list_projects()}


@router.post("/projects")
async def create_project(req: CreateProjectRequest):
    """Create a new project (does not start generation)."""
    music_req = MusicRequest(
        prompt=req.prompt,
        style=req.style,
        key=req.key,
        time_signature=req.time_signature,
        tempo=req.tempo,
        measures=req.measures,
        instruments=req.instruments,
        output_format=req.output_format,
    )
    project = _project_mgr.create_project(req.name, music_req)
    return {"project": project.model_dump()}


@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    """Get project details."""
    try:
        project = _project_mgr.get_project(project_id)
        return {"project": project.model_dump()}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在")


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    """Delete a project and all its files."""
    try:
        _version_mgr.delete_project_versions(project_id)
        _project_mgr.delete_project(project_id)
        return {"message": "项目已删除"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Project Generate / Retry ─────────────────────────────────────────────


def _run_project_pipeline(project_id: str, resume_from: str | None = None):
    """Run pipeline for a project (background thread)."""
    try:
        project = _project_mgr.get_project(project_id)
    except FileNotFoundError:
        logger.error("Project not found for generation: %s", project_id)
        return

    config = get_config()
    pipeline = MusicPipeline(config)
    cp = project.checkpoint

    existing_score = project.score if resume_from else None
    existing_midi = cp.midi_path if resume_from and cp.midi_path else None
    existing_wav = cp.wav_path if resume_from and cp.wav_path else None

    project.status = TaskStatus.GENERATING
    _project_mgr.save_project(project)

    result = pipeline.generate(
        request=project.request,
        task_id=project.id,
        resume_from=resume_from,
        existing_score=existing_score,
        existing_midi=existing_midi,
        existing_wav=existing_wav,
        project_manager=_project_mgr,
        project_id=project.id,
    )

    project = _project_mgr.get_project(project_id)
    project.status = result.status
    if result.score:
        project.score = result.score
    if result.midi_path:
        project.midi_file = result.midi_path
    if result.audio_path:
        project.audio_file = result.audio_path
    if result.duration_seconds:
        project.duration_seconds = result.duration_seconds

    # Auto-snapshot on fresh (non-resume) generation
    if result.status == TaskStatus.COMPLETED and result.score and resume_from is None:
        parent_id = project.current_version_id
        v = _version_mgr.create_version(
            project_id=project_id,
            score=result.score,
            message="初始生成",
            source="initial",
            parent_id=parent_id,
        )
        project.current_version_id = v.id

    _project_mgr.save_project(project)


@router.post("/projects/{project_id}/generate")
async def generate_for_project(project_id: str):
    """Start music generation for a project."""
    try:
        project = _project_mgr.get_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not project.request:
        raise HTTPException(status_code=400, detail="项目缺少生成参数")

    loop = asyncio.get_event_loop()
    loop.run_in_executor(_executor, _run_project_pipeline, project_id, None)
    return {"message": "生成已开始", "project_id": project_id}


@router.post("/projects/{project_id}/retry")
async def retry_project(project_id: str):
    """Retry from last successful checkpoint."""
    try:
        project = _project_mgr.get_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在")

    stage_map = {"generated": "converting", "converted": "rendering", "rendered": "postprocessing"}
    resume_from = stage_map.get(project.checkpoint.stage)

    loop = asyncio.get_event_loop()
    loop.run_in_executor(_executor, _run_project_pipeline, project_id, resume_from)
    return {"message": f"重试已开始 (从 {resume_from or '头'} 开始)", "project_id": project_id}


# ── AI Refine / Score Edit ────────────────────────────────────────────────


class RefineRequest(BaseModel):
    modification_prompt: str = Field(..., min_length=1, max_length=2000)
    section: Optional[str] = None


class ScoreEditRequest(BaseModel):
    abc_notation: str = Field(..., min_length=1)
    message: Optional[str] = None   # optional label for the auto-snapshot


def _run_refine(project_id: str, modification_prompt: str, section: str | None):
    """Run AI refinement in background thread."""
    try:
        project = _project_mgr.get_project(project_id)
    except FileNotFoundError:
        return
    config = get_config()
    from hachimi.generation.llm_generator import LLMGenerator
    generator = LLMGenerator(config)

    project.status = TaskStatus.GENERATING
    _project_mgr.save_project(project)
    try:
        full_prompt = modification_prompt
        if section:
            full_prompt = f"[针对段落: {section}] {modification_prompt}"
        new_score = generator.refine(project.score, full_prompt)
        project = _project_mgr.get_project(project_id)
        project.score = new_score
        project.checkpoint.stage = "generated"
        project.checkpoint.abc_notation = new_score.abc_notation

        # Auto-snapshot: capture the refined score
        short_msg = full_prompt[:50] + ("…" if len(full_prompt) > 50 else "")
        parent_id = project.current_version_id
        v = _version_mgr.create_version(
            project_id=project_id,
            score=new_score,
            message=f"AI修改: {short_msg}",
            source="refine",
            parent_id=parent_id,
        )
        project.current_version_id = v.id

        _project_mgr.save_project(project)
        _run_project_pipeline(project_id, resume_from="converting")
    except Exception as e:
        project = _project_mgr.get_project(project_id)
        project.status = TaskStatus.FAILED
        project.checkpoint.error_message = str(e)
        project.checkpoint.error_stage = "refine"
        _project_mgr.save_project(project)
        logger.error("Refine failed: %s", e, exc_info=True)


@router.post("/projects/{project_id}/refine")
async def refine_project(project_id: str, req: RefineRequest):
    """Use AI to modify/refine existing score."""
    try:
        project = _project_mgr.get_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not project.score:
        raise HTTPException(status_code=400, detail="项目还没有生成谱子")
    loop = asyncio.get_event_loop()
    loop.run_in_executor(_executor, _run_refine, project_id, req.modification_prompt, req.section)
    return {"message": "AI 微调已开始", "project_id": project_id}


@router.put("/projects/{project_id}/score")
async def edit_score(project_id: str, req: ScoreEditRequest):
    """Manually edit score and regenerate audio."""
    try:
        project = _project_mgr.get_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在")
    if project.score:
        project.score.abc_notation = req.abc_notation
    else:
        from hachimi.core.schemas import ScoreResult as _SR
        project.score = _SR(title=project.name, abc_notation=req.abc_notation, key="C", time_signature="4/4", tempo=120, instruments=[])
    project.checkpoint.stage = "generated"
    project.checkpoint.abc_notation = req.abc_notation

    # Auto-snapshot
    snap_msg = req.message or "手动编辑 ABC"
    parent_id = project.current_version_id
    v = _version_mgr.create_version(
        project_id=project_id,
        score=project.score,
        message=snap_msg,
        source="manual_edit" if not req.message else "tempo_change" if "速度" in snap_msg else "manual_edit",
        parent_id=parent_id,
    )
    project.current_version_id = v.id

    _project_mgr.save_project(project)
    loop = asyncio.get_event_loop()
    loop.run_in_executor(_executor, _run_project_pipeline, project_id, "converting")
    return {"message": "谱子已更新，正在重新生成音频", "project_id": project_id}


@router.post("/projects/{project_id}/audio-feedback")
async def audio_feedback(project_id: str):
    """Let AI listen to the generated audio and provide improvement suggestions."""
    try:
        project = _project_mgr.get_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在")

    if not project.score:
        raise HTTPException(status_code=400, detail="项目还没有谱子")
    if not project.audio_file:
        raise HTTPException(status_code=400, detail="项目还没有生成音频")

    config = get_config()
    audio_path = config.resolve_path(project.audio_file)
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="音频文件不存在")

    try:
        from hachimi.generation.llm_generator import LLMGenerator
        gen = LLMGenerator(config)
        feedback = gen.analyze_audio(project.score, str(audio_path))
        return feedback
    except Exception as e:
        logger.error("audio_feedback failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── Version Management (Studio history) ──────────────────────────────────


class CreateVersionRequest(BaseModel):
    message: str = Field(default="")
    source: str = Field(default="manual")
    parent_id: Optional[str] = None
    branch_name: str = Field(default="main")


class CreateBranchRequest(BaseModel):
    branch_name: str = Field(..., min_length=1, max_length=100)


@router.get("/projects/{project_id}/versions")
async def list_versions(project_id: str):
    """List all score versions for a project (newest first)."""
    try:
        project = _project_mgr.get_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在")
    versions = _version_mgr.list_versions(project_id)
    return {
        "versions": versions,
        "current_version_id": project.current_version_id,
    }


@router.post("/projects/{project_id}/versions")
async def create_version(project_id: str, req: CreateVersionRequest):
    """Manually save the current score as a named snapshot."""
    try:
        project = _project_mgr.get_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not project.score:
        raise HTTPException(status_code=400, detail="项目还没有谱子")

    parent_id = req.parent_id or project.current_version_id
    v = _version_mgr.create_version(
        project_id=project_id,
        score=project.score,
        message=req.message or "手动快照",
        source=req.source,
        parent_id=parent_id,
        branch_name=req.branch_name,
    )
    project.current_version_id = v.id
    _project_mgr.save_project(project)
    return {
        "version": {
            "id": v.id,
            "version_number": v.version_number,
            "message": v.message,
            "branch_name": v.branch_name,
            "source": v.source,
            "created_at": v.created_at,
        }
    }


@router.post("/projects/{project_id}/versions/{version_id}/checkout")
async def checkout_version(project_id: str, version_id: str):
    """Restore a project's score to a specific version and re-render audio."""
    try:
        project = _project_mgr.get_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在")

    score = _version_mgr.get_version_score(version_id)
    if score is None:
        raise HTTPException(status_code=404, detail="版本不存在")

    project.score = score
    project.checkpoint.stage = "generated"
    project.checkpoint.abc_notation = score.abc_notation
    project.current_version_id = version_id
    _project_mgr.save_project(project)

    loop = asyncio.get_event_loop()
    loop.run_in_executor(_executor, _run_project_pipeline, project_id, "converting")
    return {"message": "已回退到此版本，正在重新生成音频", "project_id": project_id}


@router.post("/projects/{project_id}/versions/{version_id}/branch")
async def branch_from_version(project_id: str, version_id: str, req: CreateBranchRequest):
    """Fork a new branch from an existing version snapshot."""
    try:
        _project_mgr.get_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在")

    v = _version_mgr.create_branch_version(
        project_id=project_id,
        from_version_id=version_id,
        branch_name=req.branch_name,
    )
    if v is None:
        raise HTTPException(status_code=404, detail="源版本不存在")

    return {
        "version": {
            "id": v.id,
            "version_number": v.version_number,
            "branch_name": v.branch_name,
            "message": v.message,
            "source": v.source,
            "created_at": v.created_at,
        }
    }


@router.delete("/projects/{project_id}/versions/{version_id}")
async def delete_version(project_id: str, version_id: str):
    """Delete a version (fails if other versions reference it as parent)."""
    ok = _version_mgr.delete_version(version_id)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="无法删除：该版本有子版本引用，请先删除子版本",
        )
    return {"message": "版本已删除"}


# ── Setup: FluidSynth & SoundFont ────────────────────────────────────────


@router.get("/setup/fluidsynth")
async def check_fluidsynth():
    """Check if FluidSynth is installed."""
    from scripts.install_fluidsynth import is_fluidsynth_installed, ensure_fluidsynth_path
    ensure_fluidsynth_path()
    result = is_fluidsynth_installed()
    return {"installed": result["installed"], "path": result["path"] or ""}


@router.post("/setup/fluidsynth")
async def install_fluidsynth():
    """Install FluidSynth (Windows only)."""
    import sys
    if sys.platform != "win32":
        raise HTTPException(status_code=400, detail="自动安装仅支持 Windows")
    try:
        from scripts.install_fluidsynth import install_fluidsynth as do_install
        result = do_install()
        return {"message": "FluidSynth 安装完成", "detail": str(result)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"安装失败: {e}")


@router.get("/setup/soundfonts")
async def list_soundfonts():
    """List available SoundFont files."""
    config = get_config()
    sf_dir = config.resolve_path(config.paths.soundfonts_dir)
    files = []
    if sf_dir.exists():
        for f in sorted(sf_dir.glob("*.sf2")):
            files.append({"name": f.name, "size_mb": round(f.stat().st_size / 1048576, 1)})
        for f in sorted(sf_dir.glob("*.sf3")):
            files.append({"name": f.name, "size_mb": round(f.stat().st_size / 1048576, 1)})
    return {"soundfonts": files, "directory": str(sf_dir)}


class SoundFontDownloadRequest(BaseModel):
    choice: str = Field(default="FluidR3_GM", description="FluidR3_GM or MuseScore_General")


@router.post("/setup/soundfonts")
async def download_soundfont(req: SoundFontDownloadRequest):
    """Download a SoundFont file."""
    config = get_config()
    sf_dir = config.resolve_path(config.paths.soundfonts_dir)
    sf_dir.mkdir(parents=True, exist_ok=True)

    urls = {
        "FluidR3_GM": (
            "https://keymusician01.s3.amazonaws.com/FluidR3_GM.sf2",
            "FluidR3_GM.sf2",
        ),
        "MuseScore_General": (
            "https://ftp.osuosl.org/pub/musescore/soundfont/MuseScore_General/MuseScore_General.sf2",
            "MuseScore_General.sf2",
        ),
    }

    if req.choice not in urls:
        raise HTTPException(status_code=400, detail=f"未知选项: {req.choice}")

    url, filename = urls[req.choice]
    dest = sf_dir / filename

    if dest.exists():
        return {"message": f"{filename} 已存在", "path": str(dest)}

    try:
        import httpx
        with httpx.Client(timeout=300.0, follow_redirects=True) as client:
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=65536):
                        f.write(chunk)
        return {"message": f"{filename} 下载完成", "path": str(dest)}
    except Exception as e:
        if dest.exists():
            dest.unlink()
        raise HTTPException(status_code=500, detail=f"下载失败: {e}")


# ── Project File Download ─────────────────────────────────────────────────


@router.get("/projects/{project_id}/download/{file_type}")
async def download_project_file(project_id: str, file_type: str):
    """Download a project file (audio, midi, etc.)."""
    try:
        project = _project_mgr.get_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在")

    from pathlib import Path as P
    file_map = {
        "audio": project.audio_file,
        "midi": project.midi_file,
        "wav": project.wav_file,
    }
    file_path_str = file_map.get(file_type)
    if not file_path_str:
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_type}")

    fp = P(file_path_str)
    if not fp.exists():
        raise HTTPException(status_code=404, detail="文件未找到")

    media_types = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".mid": "audio/midi"}
    return FileResponse(path=str(fp), media_type=media_types.get(fp.suffix, "application/octet-stream"),
                        filename=fp.name)
