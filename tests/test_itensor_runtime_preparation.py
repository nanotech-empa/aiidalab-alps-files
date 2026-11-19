"""Only configuration/protection contracts; no Julia installation or physics."""

import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "prepare_model", Path(__file__).parents[1] / "scripts/prepare-itensor-runtime.py"
)
assert SPEC is not None and SPEC.loader is not None
model = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(model)


def test_gui_binding_preserves_other_runtime_before_any_write(tmp_path, monkeypatch):
    monkeypatch.setattr(model.Path, "home", lambda: tmp_path)
    path = tmp_path / ".config/aiidalab-itensor-spectra/model-runtime.json"
    path.parent.mkdir(parents=True)
    original = json.dumps({"directory": "/existing/research/runtime"})
    path.write_text(original)
    with pytest.raises(ValueError, match="different runtime"):
        model.bind_gui(tmp_path / "new-native")
    assert path.read_text() == original
    assert not (tmp_path / ".julia-itensor-spin-localhost").is_symlink()


def test_gui_binding_is_supported_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(model.Path, "home", lambda: tmp_path)
    prefix = tmp_path / "native"
    (prefix / "depot").mkdir(parents=True)
    model.bind_gui(prefix)
    config = tmp_path / ".config/aiidalab-itensor-spectra/model-runtime.json"
    assert json.loads(config.read_text()) == {
        "directory": str(prefix / "model-runtime")
    }
    assert (tmp_path / ".julia-itensor-spin-localhost").resolve() == prefix / "depot"
    before = config.read_bytes()
    model.bind_gui(prefix)
    assert config.read_bytes() == before


def test_existing_depot_is_not_retargeted(tmp_path, monkeypatch):
    monkeypatch.setattr(model.Path, "home", lambda: tmp_path)
    old = tmp_path / "research-depot"
    old.mkdir()
    alias = tmp_path / ".julia-itensor-spin-localhost"
    alias.symlink_to(old)
    with pytest.raises(ValueError, match="different depot"):
        model.bind_gui(tmp_path / "new")
    assert alias.resolve() == old
    assert not (tmp_path / ".config").exists()


def test_model_plan_has_no_clone_install_or_profile_write(tmp_path, monkeypatch):
    julia = tmp_path / "julia"
    julia.write_text("#!/bin/sh\n")
    julia.chmod(0o755)
    monkeypatch.setattr(
        model.installer, "run", lambda *a: pytest.fail("No execution in plan mode")
    )
    result = model.prepare(tmp_path / "new", julia, "a" * 40)
    assert result["status"] == "PLAN_ONLY" and result["scientific_jobs"] == 0
    assert not (tmp_path / "new").exists()


def test_old_partial_prefix_is_never_reused(tmp_path):
    julia = tmp_path / "julia"
    julia.write_text("#!/bin/sh\n")
    julia.chmod(0o755)
    prefix = tmp_path / "partial"
    prefix.mkdir()
    (prefix / "research").write_bytes(b"retain")
    with pytest.raises(ValueError, match="partial Model prefix"):
        model.prepare(prefix, julia, "a" * 40, execute=True)
    assert (prefix / "research").read_bytes() == b"retain"
