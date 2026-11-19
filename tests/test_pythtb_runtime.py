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


@pytest.mark.parametrize(
    "changed",
    [
        {"capabilities": ["solve"]},
        {"postprocess_engine_sha256": "0" * 64},
        {"pythtb_version": "2.0.1"},
    ],
)
def test_model_only_or_stale_postprocessor_is_rejected(changed):
    recipe = Path(__file__).parents[1] / "runtime-recipes/tigu/pythtb.json"
    expected = json.loads(recipe.read_text())["worker"]
    module.validate_worker_manifest({**expected, "extra_diagnostic": True}, expected)
    with pytest.raises(ValueError, match="capabilities or source identity"):
        module.validate_worker_manifest({**expected, **changed}, expected)


def test_localhost_plan_does_not_fetch_build_install_or_create_prefix(
    tmp_path, monkeypatch
):
    path = Path(__file__).parents[1] / "scripts/apply-local-pythtb.py"
    spec = importlib.util.spec_from_file_location("local_pythtb", path)
    local = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(local)
    original = local.load

    def only_runtime(name):
        assert name == "prepare-pythtb-runtime.py", "Planning must not fetch or build"
        return original(name)

    monkeypatch.setattr(local, "load", only_runtime)
    recipe = (
        Path(__file__).parents[1] / "runtime-recipes/pythtb-2.0.2-cp312-aarch64.json"
    )
    prefix = tmp_path / "new-native-worker"
    result = local.prepare(prefix, recipe)
    assert result["status"] == "PLAN" and not prefix.exists()
    assert result["worker"]["capabilities"] == ["solve", "orbital", "wannier"]


def test_localhost_code_and_locked_recipe_supply_the_complete_native_contract():
    import yaml

    root = Path(__file__).parents[1]
    recipe = root / "runtime-recipes/pythtb-2.0.2-cp312-aarch64.json"
    data = json.loads(recipe.read_text())
    catalog = yaml.safe_load((root / "runtime-catalog.yml").read_text())
    apps = yaml.safe_load((root / "applications.yml").read_text())
    assert "local_pythtb" in apps["applications"]["pythtb"]["codes"]
    code = catalog["codes"]["local_pythtb"]
    assert code["computer"] == "mac-localhost" and not code["with_mpi"]
    assert code["default_calc_job_plugin"] == "empa_tb.calculate"
    assert code["runtime_receipt"]["extras"]["pythtb_worker"] == data["worker"]
    assert code["runtime_receipt"]["recipe_sha256"] == module.installer.checksum(recipe)
    assert catalog["setup_tasks"]["local_pythtb_runtime"]["codes"] == ["local_pythtb"]
    approved = {
        (a["url"], a["sha256"])
        for p in (root / "runtime-recipes").rglob("*.json")
        if p != recipe
        for a in json.loads(p.read_text()).get("artifacts", [])
    }
    assert data["architecture"] == "aarch64"
    assert all((a["url"], a["sha256"]) in approved for a in data["artifacts"])
    from packaging.utils import parse_wheel_filename

    # Each dependency is installed with pip into a CPython 3.12 ARM64 venv.
    from urllib.parse import urlsplit

    for artifact in data["artifacts"]:
        filename = Path(urlsplit(artifact["url"]).path).name
        assert filename.endswith(".whl")
        _, _, _, tags = parse_wheel_filename(filename)
        assert any(
            t.interpreter in {"py3", "py312", "cp312"}
            and (t.platform == "any" or t.platform.endswith("_aarch64"))
            and t.abi in {"none", "abi3", "cp312"}
            for t in tags
        )


def test_worker_checkout_accepts_only_numbered_session_notebooks(tmp_path):
    import runpy
    import subprocess

    check = runpy.run_path(
        str(Path(__file__).parents[1] / "scripts/make-pythtb-worker.py")
    )["check_checkout"]
    git = ["git", "-C", str(tmp_path)]
    subprocess.run([*git, "init", "-q"], check=True)
    (tmp_path / "app.ipynb").write_text("{}")
    (tmp_path / "numerics.py").write_text("value = 1")
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run(
        [
            *git,
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.org",
            "commit",
            "-qm",
            "reviewed",
        ],
        check=True,
    )
    (tmp_path / "app-0.ipynb").write_text("local user session")
    check(tmp_path)
    unexpected = tmp_path / "other-0.ipynb"
    unexpected.touch()
    with pytest.raises(ValueError, match="clean reviewed"):
        check(tmp_path)
    unexpected.unlink()
    (tmp_path / "numerics.py").write_text("value = 2")
    with pytest.raises(ValueError, match="clean reviewed"):
        check(tmp_path)
    subprocess.run([*git, "add", "numerics.py"], check=True)
    with pytest.raises(ValueError, match="clean reviewed"):
        check(tmp_path)
