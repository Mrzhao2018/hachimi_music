"""Tests for version management (ScoreVersion + VersionManager)."""

from __future__ import annotations

import pytest
from pathlib import Path

from hachimi.core.database import reset_engine
from hachimi.core.schemas import InstrumentAssignment, ScoreResult
from hachimi.core.version import ScoreVersion, VersionManager


# ── Helpers ───────────────────────────────────────────────────────────────

def _make_score(title: str = "Test", tempo: int = 120) -> ScoreResult:
    return ScoreResult(
        abc_notation=f"X:1\nT:{title}\nM:4/4\nQ:1/4={tempo}\nK:C\n|:C D E F|G A B c:|\n",
        title=title,
        key="C",
        time_signature="4/4",
        tempo=tempo,
        instruments=[
            InstrumentAssignment(
                voice_id="1",
                voice_name="melody",
                instrument="Acoustic Grand Piano",
                gm_program=0,
                midi_channel=0,
            )
        ],
    )


@pytest.fixture(autouse=True)
def tmp_env(tmp_path):
    """Isolated DB for every test."""
    from hachimi.core.database import get_engine
    import hachimi.core.database as _db_mod

    # Point DB to a temp file
    db_path = tmp_path / "test.db"
    # Force re-creation with the temp path
    reset_engine()
    _db_mod._DEFAULT_DB_PATH = db_path

    yield

    # Teardown
    reset_engine()
    from pathlib import Path as _P
    _db_mod._DEFAULT_DB_PATH = _P(__file__).resolve().parent.parent / "data" / "hachimi.db"


@pytest.fixture
def vmgr():
    return VersionManager()


PROJECT_ID = "proj-test-001"


# ── Tests ──────────────────────────────────────────────────────────────────

class TestVersionCRUD:
    def test_create_version(self, vmgr):
        score = _make_score("First")
        v = vmgr.create_version(PROJECT_ID, score, message="初始生成", source="initial")
        assert v.id
        assert v.project_id == PROJECT_ID
        assert v.version_number == 1
        assert v.message == "初始生成"
        assert v.source == "initial"
        assert v.branch_name == "main"
        assert v.parent_id is None

    def test_version_number_increments(self, vmgr):
        for i in range(3):
            vmgr.create_version(PROJECT_ID, _make_score(f"v{i}"))
        versions = vmgr.list_versions(PROJECT_ID)
        nums = [v["version_number"] for v in versions]
        assert sorted(nums, reverse=True) == nums  # newest first
        assert nums[0] == 3
        assert nums[-1] == 1

    def test_list_empty(self, vmgr):
        assert vmgr.list_versions("nonexistent") == []

    def test_get_version(self, vmgr):
        v = vmgr.create_version(PROJECT_ID, _make_score())
        fetched = vmgr.get_version(v.id)
        assert fetched is not None
        assert fetched.id == v.id

    def test_get_version_missing(self, vmgr):
        assert vmgr.get_version("no-such-id") is None

    def test_get_version_score_roundtrip(self, vmgr):
        score = _make_score("Roundtrip", tempo=88)
        v = vmgr.create_version(PROJECT_ID, score)
        restored = vmgr.get_version_score(v.id)
        assert restored is not None
        assert restored.tempo == 88
        assert restored.title == "Roundtrip"
        assert len(restored.instruments) == 1
        assert restored.instruments[0].instrument == "Acoustic Grand Piano"

    def test_get_latest_version(self, vmgr):
        for i in range(4):
            vmgr.create_version(PROJECT_ID, _make_score(f"v{i}"))
        latest = vmgr.get_latest_version(PROJECT_ID)
        assert latest is not None
        assert latest.version_number == 4

    def test_delete_leaf_version(self, vmgr):
        v1 = vmgr.create_version(PROJECT_ID, _make_score("v1"))
        v2 = vmgr.create_version(PROJECT_ID, _make_score("v2"), parent_id=v1.id)
        # v2 has no children — should be deletable
        result = vmgr.delete_version(v2.id)
        assert result is True
        assert vmgr.get_version(v2.id) is None

    def test_delete_parent_version_blocked(self, vmgr):
        v1 = vmgr.create_version(PROJECT_ID, _make_score("v1"))
        vmgr.create_version(PROJECT_ID, _make_score("v2"), parent_id=v1.id)
        # v1 is the parent of v2 — should NOT be deletable
        result = vmgr.delete_version(v1.id)
        assert result is False
        assert vmgr.get_version(v1.id) is not None

    def test_delete_nonexistent(self, vmgr):
        assert vmgr.delete_version("ghost") is False


class TestBranching:
    def test_create_branch_version(self, vmgr):
        v1 = vmgr.create_version(PROJECT_ID, _make_score("root"), source="initial")
        branch_v = vmgr.create_branch_version(PROJECT_ID, v1.id, "experiment")
        assert branch_v is not None
        assert branch_v.branch_name == "experiment"
        assert branch_v.parent_id == v1.id
        assert branch_v.source == "branch"
        assert branch_v.version_number == 2

    def test_branch_version_from_missing(self, vmgr):
        result = vmgr.create_branch_version(PROJECT_ID, "ghost-id", "newbranch")
        assert result is None

    def test_multi_branch_list(self, vmgr):
        v1 = vmgr.create_version(PROJECT_ID, _make_score("root"), branch_name="main")
        vmgr.create_branch_version(PROJECT_ID, v1.id, "branch-a")
        vmgr.create_branch_version(PROJECT_ID, v1.id, "branch-b")
        versions = vmgr.list_versions(PROJECT_ID)
        branches = {v["branch_name"] for v in versions}
        assert "main" in branches
        assert "branch-a" in branches
        assert "branch-b" in branches

    def test_parent_id_chain(self, vmgr):
        v1 = vmgr.create_version(PROJECT_ID, _make_score(), source="initial")
        v2 = vmgr.create_version(PROJECT_ID, _make_score(), source="refine", parent_id=v1.id)
        v3 = vmgr.create_version(PROJECT_ID, _make_score(), source="refine", parent_id=v2.id)
        assert v2.parent_id == v1.id
        assert v3.parent_id == v2.id


class TestProjectVersions:
    def test_delete_project_versions(self, vmgr):
        for _ in range(5):
            vmgr.create_version(PROJECT_ID, _make_score())
        vmgr.delete_project_versions(PROJECT_ID)
        assert vmgr.list_versions(PROJECT_ID) == []

    def test_delete_project_versions_other_project_unaffected(self, vmgr):
        vmgr.create_version(PROJECT_ID, _make_score())
        vmgr.create_version("other-project", _make_score())
        vmgr.delete_project_versions(PROJECT_ID)
        assert vmgr.list_versions(PROJECT_ID) == []
        assert len(vmgr.list_versions("other-project")) == 1
