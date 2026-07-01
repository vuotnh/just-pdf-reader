"""Sanity tests to verify project scaffolding is correctly configured."""

import importlib
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestDirectoryStructure:
    """Verify required directories exist."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "rel_path",
        [
            "src",
            "src/presentation",
            "src/application",
            "src/domain",
            "src/infrastructure",
            "tests/unit",
            "tests/property",
            "tests/integration",
            "migrations",
            "resources",
        ],
    )
    def test_directory_exists(self, rel_path: str):
        assert (PROJECT_ROOT / rel_path).is_dir(), f"{rel_path} directory missing"

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "rel_path",
        [
            "src/__init__.py",
            "src/main.py",
            "pyproject.toml",
            "conftest.py",
        ],
    )
    def test_file_exists(self, rel_path: str):
        assert (PROJECT_ROOT / rel_path).is_file(), f"{rel_path} file missing"


class TestModuleImports:
    """Verify core modules are importable."""

    @pytest.mark.unit
    def test_src_package_importable(self):
        mod = importlib.import_module("src")
        assert mod is not None

    @pytest.mark.unit
    def test_main_module_importable(self):
        mod = importlib.import_module("src.main")
        assert hasattr(mod, "main")


class TestDatabaseFixtures:
    """Verify conftest fixtures work correctly."""

    @pytest.mark.unit
    def test_db_engine_fixture(self, db_engine):
        """Engine fixture should provide a working SQLite engine."""
        from sqlalchemy import text

        with db_engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.scalar() == 1

    @pytest.mark.unit
    def test_db_engine_has_foreign_keys(self, db_engine):
        """Engine should have foreign_keys pragma enabled."""
        from sqlalchemy import text

        with db_engine.connect() as conn:
            result = conn.execute(text("PRAGMA foreign_keys"))
            assert result.scalar() == 1

    @pytest.mark.unit
    def test_db_session_fixture(self, db_session):
        """Session fixture should provide a working session."""
        from sqlalchemy import text

        result = db_session.execute(text("SELECT 1"))
        assert result.scalar() == 1


class TestHypothesisProfiles:
    """Verify Hypothesis profiles are registered."""

    @pytest.mark.unit
    def test_ci_profile_registered(self):
        from hypothesis import settings

        profile = settings.get_profile("ci")
        assert profile.max_examples == 500

    @pytest.mark.unit
    def test_dev_profile_registered(self):
        from hypothesis import settings

        profile = settings.get_profile("dev")
        assert profile.max_examples == 100

    @pytest.mark.unit
    def test_quick_profile_registered(self):
        from hypothesis import settings

        profile = settings.get_profile("quick")
        assert profile.max_examples == 10
