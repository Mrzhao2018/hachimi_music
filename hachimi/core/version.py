"""Score version management for Studio history (git-like branching).

Provides ScoreVersion SQLModel table and VersionManager CRUD class.
Auto-snapshotted on every AI refine, manual edit, and initial generation.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import List, Optional

from sqlmodel import Field as SQLField, Session, SQLModel, select

from hachimi.core.database import create_db_and_tables, get_engine
from hachimi.core.schemas import ScoreResult

logger = logging.getLogger(__name__)


class ScoreVersion(SQLModel, table=True):
    """One row per saved version of a project's score.

    Implements a DAG (directed acyclic graph): each version optionally
    references a ``parent_id``, enabling linear history and branching.
    """

    __tablename__ = "score_versions"

    id: str = SQLField(primary_key=True, default_factory=lambda: str(uuid.uuid4()))
    project_id: str = SQLField(index=True)
    # Logical parent reference (no FK constraint to avoid SQLite issues with
    # self-referential FKs in SQLModel migrations).
    parent_id: Optional[str] = SQLField(default=None)
    branch_name: str = SQLField(default="main", index=True)
    version_number: int = SQLField(default=1)  # global seq within project
    score_json: str = SQLField(default="{}")   # serialised ScoreResult
    message: str = SQLField(default="")
    # Source tag for UI display
    # Values: initial / refine / manual_edit / tempo_change / branch / manual
    source: str = SQLField(default="manual")
    created_at: str = SQLField(default_factory=lambda: datetime.now().isoformat())


# ── VersionManager ────────────────────────────────────────────────────────

class VersionManager:
    """CRUD for score versions.  Thread-safe (each call opens its own session)."""

    def __init__(self):
        # create_db_and_tables is idempotent; calling it here ensures
        # score_versions is created even on first run / after migration.
        create_db_and_tables()
        self._engine = get_engine()

    def _session(self) -> Session:
        return Session(self._engine)

    # ── helpers ────────────────────────────────────────────────────────

    def _next_version_number(self, session: Session, project_id: str) -> int:
        stmt = select(ScoreVersion).where(ScoreVersion.project_id == project_id)
        rows = session.exec(stmt).all()
        if not rows:
            return 1
        return max(r.version_number for r in rows) + 1

    # ── public API ─────────────────────────────────────────────────────

    def create_version(
        self,
        project_id: str,
        score: ScoreResult,
        message: str = "",
        source: str = "manual",
        parent_id: Optional[str] = None,
        branch_name: str = "main",
    ) -> ScoreVersion:
        """Persist a new version snapshot and return the saved row."""
        with self._session() as session:
            vnum = self._next_version_number(session, project_id)
            version = ScoreVersion(
                project_id=project_id,
                parent_id=parent_id,
                branch_name=branch_name,
                version_number=vnum,
                score_json=score.model_dump_json(),
                message=message or f"版本 {vnum}",
                source=source,
            )
            session.add(version)
            session.commit()
            session.refresh(version)
            return version

    def get_version(self, version_id: str) -> Optional[ScoreVersion]:
        with self._session() as session:
            return session.get(ScoreVersion, version_id)

    def get_version_score(self, version_id: str) -> Optional[ScoreResult]:
        """Deserialise the stored ScoreResult for a given version."""
        v = self.get_version(version_id)
        if not v:
            return None
        try:
            return ScoreResult(**json.loads(v.score_json))
        except Exception:
            return None

    def list_versions(self, project_id: str) -> List[dict]:
        """Return all versions for a project, newest-first."""
        with self._session() as session:
            stmt = (
                select(ScoreVersion)
                .where(ScoreVersion.project_id == project_id)
                .order_by(ScoreVersion.version_number.desc())  # type: ignore[attr-defined]
            )
            rows = session.exec(stmt).all()
            return [
                {
                    "id": r.id,
                    "project_id": r.project_id,
                    "parent_id": r.parent_id,
                    "branch_name": r.branch_name,
                    "version_number": r.version_number,
                    "message": r.message,
                    "source": r.source,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    def get_latest_version(self, project_id: str) -> Optional[ScoreVersion]:
        """Return the version with the highest version_number for this project."""
        with self._session() as session:
            stmt = (
                select(ScoreVersion)
                .where(ScoreVersion.project_id == project_id)
                .order_by(ScoreVersion.version_number.desc())  # type: ignore[attr-defined]
            )
            return session.exec(stmt).first()

    def create_branch_version(
        self,
        project_id: str,
        from_version_id: str,
        branch_name: str,
    ) -> Optional[ScoreVersion]:
        """Fork a new branch from an existing version.

        Returns the newly created ScoreVersion or None if source version
        is not found.
        """
        with self._session() as session:
            source_ver = session.get(ScoreVersion, from_version_id)
            if not source_ver:
                return None
            src_num = source_ver.version_number
            src_score_json = source_ver.score_json

        score = ScoreResult(**json.loads(src_score_json))
        return self.create_version(
            project_id=project_id,
            score=score,
            message=f"从 v{src_num} 分叉到 {branch_name}",
            source="branch",
            parent_id=from_version_id,
            branch_name=branch_name,
        )

    def delete_version(self, version_id: str) -> bool:
        """Delete a version.

        Will **not** delete if there are child versions pointing at this one
        as their parent (prevents dangling graph edges).
        Returns True on success, False on refusal.
        """
        with self._session() as session:
            version = session.get(ScoreVersion, version_id)
            if not version:
                return False
            # Check for children
            stmt = select(ScoreVersion).where(ScoreVersion.parent_id == version_id)
            children = session.exec(stmt).all()
            if children:
                return False
            session.delete(version)
            session.commit()
            return True

    def delete_project_versions(self, project_id: str) -> None:
        """Remove ALL versions belonging to a project (called on project delete)."""
        with self._session() as session:
            stmt = select(ScoreVersion).where(ScoreVersion.project_id == project_id)
            for row in session.exec(stmt).all():
                session.delete(row)
            session.commit()
