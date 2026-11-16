"""Installer contract using disposable files; no native installs or AiiDA state."""

import hashlib
import importlib.util
import io
import json
import subprocess
import tarfile
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "local_installer", Path(__file__).parents[1] / "scripts/install-local-runtime.py"
)
assert SPEC is not None and SPEC.loader is not None
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


@pytest.fixture
def recipe(tmp_path, monkeypatch):
    monkeypatch.setattr(installer.platform, "system", lambda: "Linux")
    monkeypatch.setattr(installer.platform, "machine", lambda: "aarch64")
    data = {
        "schema": 1,
        "id": "fixture",
        "kind": "pip-prefix",
        "architecture": "aarch64",
        "artifacts": [],
        "executables": ["bin/worker"],
        "checks": [],
    }
    path = tmp_path / "recipe.json"

    def write(**changes):
        path.write_text(json.dumps(data | changes))
        return path

    return write


def test_default_is_only_a_plan(recipe, tmp_path, monkeypatch):
    prefix = tmp_path / "not-installed"
    monkeypatch.setattr(
        installer, "run", lambda *a: pytest.fail("No tool in plan mode")
    )
    result = installer.install(recipe(), prefix)
    assert result["status"] == "PLAN_ONLY"
    assert not prefix.exists()
    assert not (tmp_path / ".not-installed-installation.json").exists()


def test_wrong_architecture_fails_before_download_or_writes(
    recipe, tmp_path, monkeypatch
):
    path = recipe()
    monkeypatch.setattr(installer.platform, "machine", lambda: "x86_64")
    with pytest.raises(ValueError, match="native Linux aarch64"):
        installer.install(path, tmp_path / "runtime", execute=True)
    assert not (tmp_path / "runtime").exists()


def test_unknown_existing_prefix_is_preserved(recipe, tmp_path):
    prefix = tmp_path / "runtime"
    prefix.mkdir()
    owned = prefix / "unrelated"
    owned.write_bytes(b"keep-exactly")
    with pytest.raises(ValueError, match="Prefix exists"):
        installer.install(recipe(), prefix, execute=True)
    assert owned.read_bytes() == b"keep-exactly"


def test_symlink_ancestor_is_refused(recipe, tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        installer.install(recipe(), alias / "runtime", execute=True)
    assert list(real.iterdir()) == []


def test_download_sha_and_cache_are_checked(tmp_path, monkeypatch):
    data = b"official-artifact"
    digest = hashlib.sha256(data).hexdigest()
    monkeypatch.setattr(
        installer.urllib.request, "urlopen", lambda *a, **kw: io.BytesIO(data)
    )
    spec = {"url": "https://example.org/worker.whl", "sha256": digest}
    path = installer.artifact(spec, tmp_path / "cache")
    assert path.name == "worker.whl"  # Conda and wheel filenames must stay valid.
    assert path.read_bytes() == data
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="Cached artifact"):
        installer.artifact(spec, tmp_path / "cache")


def test_bad_download_is_never_promoted(tmp_path, monkeypatch):
    monkeypatch.setattr(
        installer.urllib.request, "urlopen", lambda *a, **kw: io.BytesIO(b"bad")
    )
    with pytest.raises(ValueError, match="Downloaded artifact"):
        installer.artifact(
            {"url": "https://example.org/a.whl", "sha256": "a" * 64}, tmp_path
        )
    assert not list(tmp_path.rglob("*.whl"))


def test_standard_prefix_and_scoped_environment(recipe, tmp_path, monkeypatch):
    prefix = tmp_path / "runtime"
    calls = []
    monkeypatch.setenv("PIP_USER", "1")
    monkeypatch.setenv("AIIDA_PATH", str(tmp_path / "live-state"))
    monkeypatch.setenv("PYTHONPATH", "/unrelated/imports")

    def install(arguments, env, log):
        calls.append((list(map(str, arguments)), env))
        (prefix / "bin").mkdir(parents=True)
        launcher = prefix / "bin/worker"
        launcher.write_text("#!/bin/sh\nexit 0\n")
        launcher.chmod(0o755)

    monkeypatch.setattr(installer, "run", install)
    path = recipe(code_extras={"worker": {"version": "1", "hash_launcher": True}})
    result = installer.install(path, prefix, True)
    command, env = calls[0]
    assert "--prefix" in command and "--target" not in command
    assert env["PIP_USER"] == "0" and env["PYTHONNOUSERSITE"] == "1"
    assert "PYTHONPATH" not in env
    assert env["AIIDA_PATH"] != str(tmp_path / "live-state")
    assert not (tmp_path / "live-state").exists()
    assert result["code_extras"]["worker"]["launcher_sha256"] == installer.checksum(
        prefix / "bin/worker"
    )
    assert (
        json.loads((prefix / "empa-runtime.json").read_text())["status"]
        == "INSTALLED_AND_CHECKED"
    )
    (prefix / "bin/worker").write_text("changed")
    with pytest.raises(ValueError, match="file changed"):
        installer.install(path, prefix, True)


def test_failed_install_retains_receipt_and_partial_files(
    recipe, tmp_path, monkeypatch
):
    prefix = tmp_path / "runtime"

    def fail(arguments, env, log):
        prefix.mkdir()
        (prefix / "partial").write_bytes(b"diagnostic")
        raise subprocess.CalledProcessError(7, arguments)

    monkeypatch.setattr(installer, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        installer.install(recipe(), prefix, True)
    record = json.loads((tmp_path / ".runtime-installation.json").read_text())
    assert record["status"] == "FAILED" and "7" in record["error"]
    assert (prefix / "partial").read_bytes() == b"diagnostic"
    assert not (prefix / "empa-runtime.json").exists()
    with pytest.raises(ValueError, match="Prefix exists"):
        installer.install(recipe(), prefix, True)


def test_conda_uses_complete_local_explicit_lock(recipe, tmp_path, monkeypatch):
    prefix = tmp_path / "runtime"
    downloaded = tmp_path / "a-1.0-build.conda"
    downloaded.write_bytes(b"package")
    monkeypatch.setattr(installer, "artifact", lambda *a: downloaded)
    monkeypatch.setattr(installer.shutil, "which", lambda n: "/bin/mamba")

    def create(arguments, env, log):
        assert "--offline" in arguments
        explicit = Path(arguments[-1]).read_text()
        assert explicit == "@EXPLICIT\n" + downloaded.as_uri() + "\n"
        assert env["CONDA_PKGS_DIRS"].startswith(str(tmp_path))
        prefix.mkdir()

    monkeypatch.setattr(installer, "run", create)
    result = installer.install(
        recipe(kind="conda", executables=[], artifacts=[{"name": "fixture"}]),
        prefix,
        True,
    )
    assert result["status"] == "INSTALLED_AND_CHECKED"


def test_archive_rejects_path_escape(recipe, tmp_path, monkeypatch):
    archive = tmp_path / "release.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        item = tarfile.TarInfo("../escape")
        item.size = 3
        stream.addfile(item, io.BytesIO(b"bad"))
    monkeypatch.setattr(installer, "artifact", lambda *a: archive)
    with pytest.raises(ValueError, match="Archive members"):
        installer.install(
            recipe(
                kind="archive",
                archive_root="julia-1.12.6",
                artifacts=[{"name": "fixture"}],
            ),
            tmp_path / "runtime",
            True,
        )
    assert not (tmp_path.parent / "escape").exists()


def test_all_versioned_artifacts_have_hashes_and_expected_owners():
    root = Path(__file__).parents[1] / "runtime-recipes"
    for path in root.glob("*.json"):
        data = json.loads(path.read_text())
        assert data["schema"] == 1 and data["architecture"] == "aarch64"
        assert data["artifacts"]
        assert len({x["url"] for x in data["artifacts"]}) == len(data["artifacts"])
        for spec in data["artifacts"]:
            assert spec["url"].startswith(
                (
                    "https://conda.anaconda.org/conda-forge/",
                    "https://files.pythonhosted.org/",
                    "https://julialang-s3.julialang.org/",
                    "https://codeload.github.com/nanotech-empa/",
                    "https://codeload.github.com/aoterodelaroza/critic2/",
                    "https://download.open-mpi.org/release/open-mpi/v4.1/",
                )
            )
            assert len(spec["sha256"]) == 64


def test_encoded_conda_filename_is_decoded_once(tmp_path, monkeypatch):
    content = b"checked official package"
    monkeypatch.setattr(
        installer.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(content)
    )
    result = installer.artifact(
        {
            "url": "https://example.org/x264-1%21164-build.conda",
            "sha256": hashlib.sha256(content).hexdigest(),
        },
        tmp_path,
    )
    assert result.name == "x264-1!164-build.conda"
    assert "%2521" not in result.as_uri()


def test_native_checks_never_write_into_source_checkout(tmp_path, monkeypatch):
    prefix = tmp_path / "runtime"
    (prefix / "bin").mkdir(parents=True)
    command = prefix / "bin/probe"
    command.write_text("#!/bin/sh\nexit 0\n")
    command.chmod(0o755)
    observed = []

    def run(args, env, log, cwd=None):
        observed.append(cwd)
        (cwd / "CRASH").write_text("expected empty-input metadata diagnostic")

    monkeypatch.setattr(installer, "run", run)
    installer.verify(
        prefix,
        {"kind": "conda", "checks": [["@PREFIX/bin/probe"]]},
        {"PATH": "/usr/bin"},
        tmp_path / "log",
    )
    assert observed and observed[0].parent == prefix.parent
    assert observed[0] != prefix and (observed[0] / "CRASH").exists()
    assert not (prefix / "CRASH").exists()
