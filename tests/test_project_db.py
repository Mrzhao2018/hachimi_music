"""Tests for the SQLite-backed ProjectManager."""

import tempfile
from pathlib import Path

import pytest

from hachimi.core.database import reset_engine
from hachimi.core.project import PipelineCheckpoint, Project, ProjectManager
from hachimi.core.schemas import MusicRequest, OutputFormat, TaskStatus


@pytest.fixture
def tmp_env(tmp_path):
    """Provide a temporary projects dir and DB path, reset engine after test."""
    projects_dir = tmp_path / "projects"
    db_path = tmp_path / "test.db"
    yield projects_dir, db_path
    reset_engine()


@pytest.fixture
def mgr(tmp_env):
    projects_dir, db_path = tmp_env
    return ProjectManager(projects_dir=projects_dir, db_path=db_path)


class TestProjectCRUD:
    def test_create_and_get(self, mgr):
        req = MusicRequest(prompt="A happy tune")
        project = mgr.create_project("Test Song", req)
        assert project.name == "Test Song"
        assert project.status == TaskStatus.PENDING

        loaded = mgr.get_project(project.id)
        assert loaded.id == project.id
        assert loaded.name == "Test Song"
        assert loaded.request.prompt == "A happy tune"

    def test_get_not_found(self, mgr):
        with pytest.raises(FileNotFoundError):
            mgr.get_project("nonexistent-id")

    def test_list_empty(self, mgr):
        assert mgr.list_projects() == []

    def test_list_projects_ordered(self, mgr):
        req = MusicRequest(prompt="test")
        p1 = mgr.create_project("First", req)
        p2 = mgr.create_project("Second", req)

        projects = mgr.list_projects()
        assert len(projects) == 2
        # newest first
        assert projects[0]["id"] == p2.id
        assert projects[1]["id"] == p1.id

    def test_list_projects_fields(self, mgr):
        req = MusicRequest(prompt="test")
        mgr.create_project("My Song", req)

        projects = mgr.list_projects()
        p = projects[0]
        assert "id" in p
        assert p["name"] == "My Song"
        assert p["status"] == "pending"
        assert "created_at" in p
        assert "updated_at" in p
        assert "has_audio" in p
        assert "has_score" in p
        assert "title" in p

    def test_save_updates_project(self, mgr):
        req = MusicRequest(prompt="test")
        project = mgr.create_project("Original", req)

        project.name = "Updated"
        project.status = TaskStatus.COMPLETED
        mgr.save_project(project)

        loaded = mgr.get_project(project.id)
        assert loaded.name == "Updated"
        assert loaded.status == TaskStatus.COMPLETED

    def test_delete_project(self, mgr):
        req = MusicRequest(prompt="test")
        project = mgr.create_project("To Delete", req)
        assert len(mgr.list_projects()) == 1

        mgr.delete_project(project.id)
        assert len(mgr.list_projects()) == 0

        with pytest.raises(FileNotFoundError):
            mgr.get_project(project.id)

    def test_delete_nonexistent(self, mgr):
        # Should not raise
        mgr.delete_project("does-not-exist")


class TestCheckpoint:
    def test_update_checkpoint(self, mgr):
        req = MusicRequest(prompt="test")
        project = mgr.create_project("CP Test", req)

        mgr.update_checkpoint(project.id, "generated", abc_notation="X:1\nK:C\nCDEF|")
        loaded = mgr.get_project(project.id)
        assert loaded.checkpoint.stage == "generated"
        assert loaded.checkpoint.abc_notation == "X:1\nK:C\nCDEF|"

    def test_checkpoint_error(self, mgr):
        req = MusicRequest(prompt="test")
        project = mgr.create_project("Err Test", req)

        mgr.update_checkpoint(
            project.id, "none",
            error_message="something broke",
            error_stage="converting",
        )
        loaded = mgr.get_project(project.id)
        assert loaded.checkpoint.error_message == "something broke"
        assert loaded.checkpoint.error_stage == "converting"


class TestFilePaths:
    def test_project_file_path(self, mgr):
        req = MusicRequest(prompt="test")
        project = mgr.create_project("Path Test", req)

        path = mgr.get_project_file_path(project.id, "output.mid")
        assert path.name == "output.mid"
        assert project.id in str(path)

    def test_project_dir_created(self, mgr):
        req = MusicRequest(prompt="test")
        project = mgr.create_project("Dir Test", req)

        d = mgr.get_project_file_path(project.id, "").parent
        assert d.exists()


class TestScoreStorage:
    def test_score_roundtrip(self, mgr):
        from hachimi.core.schemas import InstrumentAssignment, ScoreResult
        req = MusicRequest(prompt="test")
        project = mgr.create_project("Score Test", req)

        score = ScoreResult(
            abc_notation="X:1\nT:Test\nK:C\nCDEF|",
            title="Test Song",
            key="C",
            time_signature="4/4",
            tempo=120,
            instruments=[
                InstrumentAssignment(
                    voice_id="1",
                    voice_name="melody",
                    instrument="Acoustic Grand Piano",
                    gm_program=0,
                ),
            ],
        )
        project.score = score
        mgr.save_project(project)

        loaded = mgr.get_project(project.id)
        assert loaded.score is not None
        assert loaded.score.title == "Test Song"
        assert loaded.score.abc_notation == "X:1\nT:Test\nK:C\nCDEF|"
        assert len(loaded.score.instruments) == 1
        assert loaded.score.instruments[0].gm_program == 0
