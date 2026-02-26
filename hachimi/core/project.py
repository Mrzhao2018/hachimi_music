"""Project management backed by SQLite via SQLModel.

Drop-in replacement for the old JSON-file-based ProjectManager.
The public API (create_project, get_project, save_project, list_projects,
delete_project, update_checkpoint, get_project_file_path) is unchanged so
callers (routes.py, pipeline.py) need zero modifications.
"""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from sqlmodel import Field as SQLField, Session, SQLModel, select

from hachimi.core.database import create_db_and_tables, get_engine
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
    """A music generation project — Pydantic model used by the rest of the app.

    This is the same shape as the old ``Project`` so callers do not need changes.
    """

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


# ── SQLModel DB table ─────────────────────────────────────────────────────

class ProjectRow(SQLModel, table=True):
    """One row per project in the ``projects`` table."""

    __tablename__ = "projects"

    id: str = SQLField(primary_key=True, default_factory=lambda: str(uuid.uuid4()))
    name: str = SQLField(default="Untitled Project", index=True)
    created_at: str = SQLField(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = SQLField(
        default_factory=lambda: datetime.now().isoformat(),
        index=True,
    )
    status: str = SQLField(default="pending", index=True)
    output_format: str = SQLField(default="mp3")

    # Large / nested objects stored as JSON text columns
    request_json: Optional[str] = SQLField(default=None)
    score_json: Optional[str] = SQLField(default=None)
    checkpoint_json: str = SQLField(default='{"stage":"none"}')

    # File paths (relative to project directory)
    midi_file: Optional[str] = SQLField(default=None)
    wav_file: Optional[str] = SQLField(default=None)
    audio_file: Optional[str] = SQLField(default=None)

    duration_seconds: Optional[float] = SQLField(default=None)


# ── Conversion helpers ────────────────────────────────────────────────────

def _row_to_project(row: ProjectRow) -> Project:
    """Convert a DB row to the Pydantic Project model."""
    request = None
    if row.request_json:
        request = MusicRequest(**json.loads(row.request_json))

    score = None
    if row.score_json:
        score = ScoreResult(**json.loads(row.score_json))

    checkpoint = PipelineCheckpoint()
    if row.checkpoint_json:
        checkpoint = PipelineCheckpoint(**json.loads(row.checkpoint_json))

    return Project(
        id=row.id,
        name=row.name,
        created_at=row.created_at,
        updated_at=row.updated_at,
        request=request,
        score=score,
        status=TaskStatus(row.status),
        checkpoint=checkpoint,
        midi_file=row.midi_file,
        wav_file=row.wav_file,
        audio_file=row.audio_file,
        duration_seconds=row.duration_seconds,
        output_format=OutputFormat(row.output_format),
    )


def _project_to_row(project: Project) -> ProjectRow:
    """Convert the Pydantic Project model to a flat DB row."""
    return ProjectRow(
        id=project.id,
        name=project.name,
        created_at=project.created_at,
        updated_at=project.updated_at,
        status=project.status.value,
        output_format=project.output_format.value,
        request_json=project.request.model_dump_json() if project.request else None,
        score_json=project.score.model_dump_json() if project.score else None,
        checkpoint_json=project.checkpoint.model_dump_json(),
        midi_file=project.midi_file,
        wav_file=project.wav_file,
        audio_file=project.audio_file,
        duration_seconds=project.duration_seconds,
    )


# ── Project Storage (public API unchanged) ────────────────────────────────

class ProjectManager:
    """Manages project CRUD backed by SQLite.

    The public interface is identical to the old JSON-file based version.
    """

    def __init__(self, projects_dir: Optional[Path] = None, db_path: Optional[Path] = None):
        self.projects_dir = projects_dir or PROJECTS_DIR
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        create_db_and_tables(db_path)
        self._engine = get_engine(db_path)

    # ── helpers ────────────────────────────────────────────────────────

    def _project_dir(self, project_id: str) -> Path:
        return self.projects_dir / project_id

    def _session(self) -> Session:
        return Session(self._engine)

    # ── public API ────────────────────────────────────────────────────

    def list_projects(self) -> list[dict]:
        """List all projects (summary only), newest first."""
        with self._session() as session:
            stmt = select(ProjectRow).order_by(ProjectRow.updated_at.desc())  # type: ignore[attr-defined]
            rows = session.exec(stmt).all()
            projects = []
            for row in rows:
                score_title = ""
                if row.score_json:
                    try:
                        score_title = json.loads(row.score_json).get("title", "")
                    except Exception:
                        pass
                projects.append({
                    "id": row.id,
                    "name": row.name,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                    "status": row.status,
                    "has_audio": bool(row.audio_file),
                    "has_score": bool(row.score_json),
                    "title": score_title,
                })
            return projects

    def get_project(self, project_id: str) -> Project:
        """Load a project by ID."""
        with self._session() as session:
            row = session.get(ProjectRow, project_id)
            if row is None:
                raise FileNotFoundError(f"Project not found: {project_id}")
            return _row_to_project(row)

    def save_project(self, project: Project) -> None:
        """Upsert a project into the database."""
        project.updated_at = datetime.now().isoformat()
        row = _project_to_row(project)
        with self._session() as session:
            existing = session.get(ProjectRow, row.id)
            if existing:
                # Update all columns
                existing.name = row.name
                existing.created_at = row.created_at
                existing.updated_at = row.updated_at
                existing.status = row.status
                existing.output_format = row.output_format
                existing.request_json = row.request_json
                existing.score_json = row.score_json
                existing.checkpoint_json = row.checkpoint_json
                existing.midi_file = row.midi_file
                existing.wav_file = row.wav_file
                existing.audio_file = row.audio_file
                existing.duration_seconds = row.duration_seconds
                session.add(existing)
            else:
                session.add(row)
            session.commit()

    def create_project(self, name: str, request: MusicRequest) -> Project:
        """Create a new project."""
        project = Project(
            name=name,
            request=request,
            output_format=request.output_format,
        )
        # Ensure project file directory exists
        self._project_dir(project.id).mkdir(parents=True, exist_ok=True)
        self.save_project(project)
        return project

    def delete_project(self, project_id: str) -> None:
        """Delete a project from the DB and remove its files."""
        with self._session() as session:
            row = session.get(ProjectRow, project_id)
            if row:
                session.delete(row)
                session.commit()
        # Also remove project file directory
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

