"""PythTB worker composition/reuse guards; no SSH, install or science."""

import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "pythtb_runtime", Path(__file__).parents[1] / "scripts/prepare-pythtb-runtime.py"
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_plan_does_not_install_or_claim_a_prefix(tmp_path, monkeypatch):
    monkeypatch.setattr(
        module.installer, "install", lambda *a, **kw: pytest.fail("No install for plan")
    )
    recipe = Path(__file__).parents[1] / "runtime-recipes/tigu/pythtb.json"
    prefix = tmp_path / "new-worker"
    result = module.prepare(prefix, recipe)
    assert result["status"] == "PLAN" and result["scientific_jobs"] == 0
    assert not prefix.exists()


def test_composed_receipt_does_not_hash_itself_and_rejects_changed_source(tmp_path):
    recipe = Path(__file__).parents[1] / "runtime-recipes/tigu/pythtb.json"
    prefix = tmp_path / "worker"
    source = prefix / "runtime/lib/python3.12/site-packages/aiidalab_tb/model.py"
    source.parent.mkdir(parents=True)
    source.write_text("# reviewed app numerical source\n")
    receipt = prefix / "empa-pythtb-runtime.json"
    receipt.write_text('{"status":"INSTALLING"}')
    saved = {
        "status": "INSTALLED_AND_CHECKED",
        "recipe_sha256": module.installer.checksum(recipe),
        "verified_files": module.installed_files(prefix),
    }
    receipt.write_text(json.dumps(saved))
    assert "empa-pythtb-runtime.json" not in saved["verified_files"]
    assert module.prepare(prefix, recipe) == saved
    source.write_text("# changed worker source\n")
    with pytest.raises(ValueError, match="runtime changed"):
        module.prepare(prefix, recipe)


def test_unowned_or_incomplete_runtime_is_preserved(tmp_path):
    recipe = Path(__file__).parents[1] / "runtime-recipes/tigu/pythtb.json"
    prefix = tmp_path / "existing"
    prefix.mkdir()
    with pytest.raises(ValueError, match="unowned"):
        module.prepare(prefix, recipe)
    (prefix / "empa-pythtb-runtime.json").write_text('{"status":"FAILED_RETAINED"}')
    with pytest.raises(ValueError, match="incomplete"):
        module.prepare(prefix, recipe)
