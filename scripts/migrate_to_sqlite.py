"""Migrate existing JSON-file projects into the SQLite database.

Usage:
    python -m scripts.migrate_to_sqlite

Reads every ``projects/<uuid>/project.json`` and inserts them into
``data/hachimi.db``.  The original JSON files are left untouched.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hachimi.core.project import (
    PipelineCheckpoint,
    Project,
    ProjectManager,
)
from hachimi.core.schemas import (
    MusicRequest,
    OutputFormat,
    ScoreResult,
    TaskStatus,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


PROJECTS_DIR = ROOT / "projects"


def migrate():
    if not PROJECTS_DIR.exists():
        logger.info("No projects/ directory found — nothing to migrate.")
        return

    mgr = ProjectManager()
    migrated = 0
    skipped = 0

    for d in sorted(PROJECTS_DIR.iterdir()):
        pf = d / "project.json"
        if not (d.is_dir() and pf.exists()):
            continue

        project_id = d.name
        try:
            # Check if already in DB
            try:
                mgr.get_project(project_id)
                logger.info("  SKIP %s (already in DB)", project_id[:12])
                skipped += 1
                continue
            except FileNotFoundError:
                pass

            data = json.loads(pf.read_text(encoding="utf-8"))
            project = Project(**data)
            mgr.save_project(project)
            migrated += 1
            logger.info("  OK   %s  %s", project_id[:12], project.name)
        except Exception as e:
            logger.error("  FAIL %s: %s", project_id[:12], e)

    logger.info("Migration complete: %d migrated, %d skipped.", migrated, skipped)


if __name__ == "__main__":
    migrate()
