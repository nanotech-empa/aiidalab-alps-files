"""Private/shared module deployment contracts; no SSH, install or science."""

import importlib.util
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "tigu_modules", Path(__file__).parents[1] / "scripts/deploy-tigu-modules.py"
)
assert SPEC is not None and SPEC.loader is not None
stack = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stack)


def test_default_plan_has_no_files_download_or_command(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(stack.platform, "system", lambda: "Linux")
    monkeypatch.setattr(stack.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        stack, "bootstrap", lambda *a: pytest.fail("No bootstrap for a plan")
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["deployment", "--root", str(tmp_path / "new"), "--families", "model"],
    )
    stack.main()
    data = json.loads(capsys.readouterr().out)
    assert list(data["families"]) == ["julia", "model"]
    assert data["scientific_jobs"] == 0
    assert not (tmp_path / "new").exists()


def test_shared_and_private_modules_use_only_the_selected_prefix(tmp_path):
    for dirname in ["private stack", "administrator-stack"]:
        root = tmp_path / dirname
        text = stack.module_text("cp2k", root / "cp2k", root)
        assert str(root / "cp2k/bin") in text
        assert str(root / "cp2k/share/cp2k/data") in text
        assert "SLURM_CPUS_PER_TASK" in text
        assert "module purge" not in text and "bashrc" not in text
    assert stack.tcl("a{b}\\c") == "{a\\{b\\}\\\\c}"


def test_module_publication_preserves_existing_and_symlinks(tmp_path):
    module = tmp_path / "modules/cp2k/2026.2"
    stack.publish_file(module, "original\n")
    stack.publish_file(module, "original\n")
    with pytest.raises(ValueError, match="existing modulefile differs"):
        stack.publish_file(module, "different\n")
    assert module.read_text() == "original\n"
    alias = tmp_path / "alias"
    alias.symlink_to(module.parent)
    with pytest.raises(ValueError, match="symlinked"):
        stack.publish_file(alias / "new", "no\n")
    assert not (module.parent / "new").exists()


def test_registered_provider_checks_executable_and_module_identities(
    tmp_path, monkeypatch
):
    root, modules = tmp_path / "root", tmp_path / "modules"
    prefix = root / "runtime"
    (prefix / "bin").mkdir(parents=True)
    exe = prefix / "bin/python"
    exe.write_bytes(b"selected native interpreter")
    module = modules / "empa/test/1"
    stack.publish_file(module, "#%Module1.0\n")
    recipes = tmp_path / "recipes"
    recipes.mkdir()
    recipe = recipes / "banduppy.json"
    recipe.write_text("{}")
    monkeypatch.setattr(stack, "RECIPES", recipes)
    receipt = {
        "status": "MODULE_LOAD_VERIFIED",
        "family": "banduppy",
        "prefix": str(prefix),
        "module": "empa/test/1",
        "module_sha256": stack.digest(module),
        "recipe_sha256": stack.digest(recipe),
        "executables": {"bin/python": stack.digest(exe)},
    }
    (root / "receipts").mkdir()
    (root / "receipts/banduppy.json").write_text(json.dumps(receipt))
    assert stack.verify_receipt(root, modules, "banduppy") == receipt
    exe.write_bytes(b"changed")
    with pytest.raises(ValueError, match="executable differs"):
        stack.verify_receipt(root, modules, "banduppy")
    exe.write_bytes(b"selected native interpreter")
    module.write_text("modified\n")
    with pytest.raises(ValueError, match="modulefile differs"):
        stack.verify_receipt(root, modules, "banduppy")


def test_compute_only_model_plan_does_not_bind_gui(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "model_remote", stack.HERE / "prepare-itensor-runtime.py"
    )
    assert spec is not None and spec.loader is not None
    model = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(model)
    julia = tmp_path / "julia"
    julia.write_text("#!/bin/sh\n")
    julia.chmod(0o755)
    monkeypatch.setattr(
        model, "bind_gui", lambda *a: pytest.fail("No GUI binding on Tigu")
    )
    result = model.prepare(tmp_path / "model", julia, "a" * 40, bind_app=False)
    assert result["bind_app"] is False and result["scientific_jobs"] == 0
    assert not (tmp_path / "model").exists()


def test_standalone_dispatcher_is_exact_canonical_source(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "native_files", stack.HERE / "install-local-runtime.py"
    )
    assert spec is not None and spec.loader is not None
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    source = tmp_path / "file.py"
    source.write_bytes(b"# original author and source\n")
    archive = tmp_path / "source.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        info = tarfile.TarInfo("upstream/file.py")
        content = source.read_bytes()
        info.size = len(content)
        stream.addfile(info, io.BytesIO(content))
    recipe = {
        "artifacts": [{"name": "source"}],
        "source_files": [
            {
                "artifact": "source",
                "member": "upstream/file.py",
                "destination": "share/orca/file.py",
                "sha256": stack.digest(source),
            }
        ],
    }
    prefix = tmp_path / "runtime"
    installer.install_source_files(prefix, recipe, [archive])
    assert (prefix / "share/orca/file.py").read_bytes() == source.read_bytes()
    with pytest.raises(ValueError, match="overwrite"):
        installer.install_source_files(prefix, recipe, [archive])


def test_all_tigu_native_recipes_have_complete_hashes():
    for recipe in stack.RECIPES.glob("*.json"):
        data = json.loads(recipe.read_text())
        assert data["architecture"] == "x86_64"
        assert data["artifacts"]
        for artifact in data["artifacts"]:
            assert artifact["url"].startswith("https://")
            assert len(artifact["sha256"]) == 64
        for build in data.get("native_builds", []):
            assert any(a["name"] == build["artifact"] for a in data["artifacts"])
            assert "aarch64" not in str(build)


def test_publish_receipt_uses_only_a_command_scoped_environment(tmp_path, monkeypatch):
    root = tmp_path / "stack"
    prefix = root / "banduppy"
    (prefix / "bin").mkdir(parents=True)
    worker = prefix / "bin/python"
    worker.write_text("#!/bin/sh\nexit 0\n")
    worker.chmod(0o755)
    init = tmp_path / "synthetic-module-init.sh"
    init.write_text("module() { :; }\n")
    monkeypatch.setenv("AIIDA_PATH", str(tmp_path / "unrelated-live-state"))
    result = stack.publish_receipt(
        root,
        root / "modules",
        "banduppy",
        prefix,
        ["bin/python"],
        {"recipe_sha256": "a" * 64},
        init,
    )
    assert result["status"] == "MODULE_LOAD_VERIFIED"
    assert not (tmp_path / "unrelated-live-state").exists()
    assert result["executables"] == {"bin/python": stack.digest(worker)}


def load_setup_task():
    spec = importlib.util.spec_from_file_location(
        "tigu_apply", stack.HERE / "apply-tigu-stack.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_staging_verifies_reuse_and_never_overwrites(tmp_path):
    import subprocess

    task = load_setup_task()
    identity, bundle = task.source_bundle()
    root = tmp_path / "stack"
    args = [sys.executable, "-c", task.REMOTE_STAGE, str(root), identity]
    first = subprocess.run(args, input=bundle, capture_output=True, check=True)
    dest = Path(json.loads(first.stdout)["source"])
    script = dest / "scripts/deploy-tigu-modules.py"
    before = script.stat().st_mtime_ns
    subprocess.run(args, input=bundle, capture_output=True, check=True)
    assert script.stat().st_mtime_ns == before
    script.write_text("retain changed source for review\n")
    failed = subprocess.run(args, input=bundle, capture_output=True)
    assert failed.returncode != 0 and b"Existing staged source differs" in failed.stderr
    assert script.read_text() == "retain changed source for review\n"


def test_compatible_module_does_not_submit_an_install_task(tmp_path, monkeypatch):
    task = load_setup_task()
    identity = task.source_bundle()[0]
    calls = []
    receipt = {"status": "MODULE_LOAD_VERIFIED", "module": "empa/banduppy/1.0.0"}

    def ssh(host, arguments, data=None):
        calls.append(arguments)
        output = {"source": "/private/source"} if data else receipt
        return type("Reply", (), {"stdout": json.dumps(output).encode()})()

    monkeypatch.setattr(task, "ssh", ssh)
    monkeypatch.setattr(
        task.subprocess,
        "run",
        lambda *a, **k: pytest.fail("No install for a matching module"),
    )
    assert (
        task.apply(
            "tigu", tmp_path / "stack", tmp_path / "modules", "banduppy", identity
        )
        == receipt
    )
    assert len(calls) == 2 and "--probe-family" in calls[1]


def test_authentication_failure_never_becomes_an_install_fallback(
    tmp_path, monkeypatch
):
    import subprocess

    task = load_setup_task()
    identity = task.source_bundle()[0]

    def denied(*args, **kwargs):
        raise subprocess.CalledProcessError(255, ["ssh"], stderr=b"Permission denied")

    monkeypatch.setattr(task, "ssh", denied)
    monkeypatch.setattr(
        task.subprocess,
        "run",
        lambda *a, **k: pytest.fail("No install after access failure"),
    )
    with pytest.raises(subprocess.CalledProcessError):
        task.apply(
            "tigu", tmp_path / "stack", tmp_path / "modules", "banduppy", identity
        )


def test_private_model_capsule_keeps_exact_shallow_source_and_no_local_changes(
    tmp_path, monkeypatch
):
    import subprocess

    spec = importlib.util.spec_from_file_location(
        "source_maker", stack.HERE / "make-model-source.py"
    )
    assert spec is not None and spec.loader is not None
    maker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(maker)
    checkout = tmp_path / "canonical"
    subprocess.run(["git", "init", "-q", str(checkout)], check=True)
    (checkout / "engine.jl").write_text("# canonical authored engine source\n")
    subprocess.run(["git", "-C", str(checkout), "add", "engine.jl"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(checkout),
            "-c",
            "user.name=Test Author",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "Scientific source fixture",
        ],
        check=True,
    )
    commit = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
    ).strip()
    monkeypatch.setattr(maker, "COMMIT", commit)
    archive = tmp_path / "private/source.tar.gz"
    record = maker.create(checkout, archive)
    assert record["source_commit"] == commit and archive.stat().st_mode & 0o777 == 0o600
    extracted = tmp_path / "extract"
    extracted.mkdir()
    with tarfile.open(archive) as source:
        source.extractall(extracted, filter="data")
    assert (
        subprocess.check_output(
            ["git", "-C", str(extracted / "source"), "rev-parse", "HEAD"], text=True
        ).strip()
        == commit
    )
    assert (
        subprocess.check_output(
            [
                "git",
                "-C",
                str(extracted / "source"),
                "rev-parse",
                "--is-shallow-repository",
            ],
            text=True,
        ).strip()
        == "true"
    )
    (checkout / "unrelated-private-note").write_text("must not be copied")
    with pytest.raises(ValueError, match="clean selected"):
        maker.create(checkout, tmp_path / "refused.tar.gz")


def test_shared_group_never_changes_licensed_site_or_unrelated_paths(
    tmp_path, monkeypatch
):
    import os

    root = tmp_path / "stack"
    (root / "python312").mkdir(parents=True)
    (root / "tools").mkdir()
    site = tmp_path / "licensed-site"
    site.mkdir()
    executable = site / "orca"
    executable.write_text("retain site permissions")
    modules = tmp_path / "modules"
    module = modules / "empa/orca/6.1.1"
    stack.publish_file(module, "#%Module1.0\n")
    changed = []
    monkeypatch.setattr(
        stack.grp, "getgrnam", lambda name: type("Group", (), {"gr_gid": os.getgid()})()
    )
    monkeypatch.setattr(
        stack.os, "chown", lambda path, uid, gid: changed.append(Path(path))
    )
    monkeypatch.setattr(stack.os, "chmod", lambda *args: None)
    stack.share_completed(
        root,
        modules,
        {"orca": {"prefix": str(site), "module": "empa/orca/6.1.1"}},
        "authorized-group",
    )
    assert changed and site not in changed and executable not in changed
