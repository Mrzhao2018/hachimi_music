"""Project management: save/load/list music generation projects."""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from hachimi.core.config import get_config
from hachimi.core.schemas import (
    MusicRequest,
    MusicStyle,
    OutputFormat,
    ScoreResult,
    TaskStatus,
)

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PROJECTS_DIR = _PROJECT_ROOT / "projects"


# ── Project Models ────────────────────────────────────────────────────────

class PipelineCheckpoint(BaseModel):
    """Tracks which pipeline stages have completed, enabling retry from failure."""
    stage: str = "none"  # none / generated / converted / rendered / postprocessed
    abc_notation: Optional[str] = None
    midi_path: Optional[str] = None
    wav_path: Optional[str] = None
    audio_path: Optional[str] = None
    error_message: Optional[str] = None
    error_stage: Optional[str] = None


class Project(BaseModel):
    """A music generation project."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Untitled Project"
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    # Request parameters
    request: Optional[MusicRequest] = None

    # Generation results
    score: Optional[ScoreResult] = None
    status: TaskStatus = TaskStatus.PENDING

    # Pipeline checkpoint for retry
    checkpoint: PipelineCheckpoint = Field(default_factory=PipelineCheckpoint)

    # File paths (relative to project directory)
    midi_file: Optional[str] = None
    wav_file: Optional[str] = None
    audio_file: Optional[str] = None

    # Metadata
    duration_seconds: Optional[float] = None
    output_format: OutputFormat = OutputFormat.MP3


# ── Project Storage ───────────────────────────────────────────────────────

class ProjectManager:
    """Manages project CRUD and file storage."""

    def __init__(self, projects_dir: Optional[Path] = None):
        self.projects_dir = projects_dir or PROJECTS_DIR
        self.projects_dir.mkdir(parents=True, exist_ok=True)

    def _project_dir(self, project_id: str) -> Path:
        return self.projects_dir / project_id

    def _project_file(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "project.json"

    def list_projects(self) -> list[dict]:
        """List all projects (summary only)."""
        projects = []
        for d in sorted(self.projects_dir.iterdir(), reverse=True):
            pf = d / "project.json"
            if d.is_dir() and pf.exists():
                try:
                    data = json.loads(pf.read_text(encoding="utf-8"))
                    projects.append({
                        "id": data["id"],
                        "name": data.get("name", "Untitled"),
                        "created_at": data.get("created_at", ""),
                        "updated_at": data.get("updated_at", ""),
                        "status": data.get("status", "pending"),
                        "has_audio": bool(data.get("audio_file")),
                        "has_score": bool(data.get("score")),
                        "title": data.get("score", {}).get("title", "") if data.get("score") else "",
                    })
                except Exception as e:
                    logger.warning("Failed to read project %s: %s", d.name, e)
        # Sort by updated_at descending
        projects.sort(key=lambda p: p.get("updated_at", ""), reverse=True)
        return projects

    def get_project(self, project_id: str) -> Project:
        """Load a project by ID."""
        pf = self._project_file(project_id)
        if not pf.exists():
            raise FileNotFoundError(f"Project not found: {project_id}")
        data = json.loads(pf.read_text(encoding="utf-8"))
        return Project(**data)

    def save_project(self, project: Project) -> None:
        """Save a project to disk."""
        project.updated_at = datetime.now().isoformat()
        d = self._project_dir(project.id)
        d.mkdir(parents=True, exist_ok=True)
        pf = d / "project.json"
        pf.write_text(project.model_dump_json(indent=2), encoding="utf-8")

    def create_project(self, name: str, request: MusicRequest) -> Project:
        """Create a new project."""
        project = Project(
            name=name,
            request=request,
            output_format=request.output_format,
        )
        self.save_project(project)
        return project

    def delete_project(self, project_id: str) -> None:
        """Delete a project and all its files."""
        d = self._project_dir(project_id)
        if d.exists():
            shutil.rmtree(d)

    def get_project_file_path(self, project_id: str, filename: str) -> Path:
        """Get absolute path for a file within a project directory."""
        return self._project_dir(project_id) / filename

    def update_checkpoint(
        self,
        project_id: str,
        stage: str,
        **kwargs,
    ) -> Project:
        """Update the pipeline checkpoint for a project."""
        project = self.get_project(project_id)
        project.checkpoint.stage = stage
        for k, v in kwargs.items():
            if hasattr(project.checkpoint, k):
                setattr(project.checkpoint, k, v)
        self.save_project(project)
        return project
