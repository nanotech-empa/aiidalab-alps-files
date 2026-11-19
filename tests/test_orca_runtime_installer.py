"""Licensed-program installation contracts using synthetic ELF/tar fixtures only."""

import hashlib
import importlib.util
import io
import json
import tarfile
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "install_orca", Path(__file__).parents[1] / "scripts/install-orca-runtime.py"
)
assert SPEC is not None and SPEC.loader is not None
orca = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(orca)


@pytest.fixture
def archive(tmp_path, monkeypatch):
    monkeypatch.setattr(orca.installer.platform, "system", lambda: "Linux")
    monkeypatch.setattr(orca.installer.platform, "machine", lambda: "aarch64")
    path = tmp_path / "synthetic-not-a-licensed-program.tar.gz"
    header = bytearray(20)
    header[:6] = b"\x7fELF\x02\x01"
    header[18:20] = (183).to_bytes(2, "little")
    with tarfile.open(path, "w:gz") as output:
        for name in ("orca", "orca_plot", "orca_2json", "orca_startup_mpi"):
            entry = tarfile.TarInfo("orca_6_1_1_fixture/" + name)
            entry.size = len(header)
            entry.mode = 0o755
            output.addfile(entry, io.BytesIO(header))
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_licensed_archive_plan_never_runs_or_extracts(archive, tmp_path, monkeypatch):
    path, digest = archive
    monkeypatch.setattr(
        orca.installer, "run", lambda *a, **kw: pytest.fail("Plan executes nothing")
    )
    result = orca.install(path, digest, tmp_path / "native", tmp_path / "mpi")
    assert result["status"] == "PLAN_ONLY" and result["scientific_jobs"] == 0
    assert not (tmp_path / "native").exists()


def test_bad_archive_digest_is_rejected_before_installation(archive, tmp_path):
    path, _ = archive
    with pytest.raises(ValueError, match="SHA-256 differs"):
        orca.install(path, "f" * 64, tmp_path / "native", tmp_path / "mpi", True)
    assert not (tmp_path / "native").exists()


def test_missing_archive_does_not_attempt_mpi_installation(tmp_path, monkeypatch):
    monkeypatch.setattr(orca.installer.platform, "system", lambda: "Linux")
    monkeypatch.setattr(orca.installer.platform, "machine", lambda: "aarch64")
    with pytest.raises(ValueError, match="licensed ORCA"):
        orca.install(
            tmp_path / "absent", "a" * 64, tmp_path / "native", tmp_path / "mpi"
        )
    assert not (tmp_path / "mpi").exists()


def test_install_checks_matching_mpi_and_retains_original_archive(
    archive, tmp_path, monkeypatch
):
    path, digest = archive
    prefix, mpi = tmp_path / "native", tmp_path / "mpi"
    (mpi / "bin").mkdir(parents=True)
    (mpi / "bin/mpicc").touch()
    calls = []

    def output(args, **kwargs):
        calls.append(args)
        if str(args[0]).endswith("mpirun"):
            return "Open MPI4.1.8"
        if str(args[0]).endswith("-cc"):
            return "aarch64-conda-linux-gnu"
        return "libmpi.so => " + str(mpi / "lib/libmpi.so")

    def run(args, env, log):
        calls.append(args)
        if "-o" in args:
            Path(args[-1]).write_bytes(b"synthetic-probe")

    monkeypatch.setattr(orca.subprocess, "check_output", output)
    monkeypatch.setattr(orca.installer, "run", run)
    result = orca.install(path, digest, prefix, mpi, True)
    assert result["status"] == "INSTALLED_AND_CHECKED"
    assert orca.installer.checksum(path) == digest
    assert (
        json.loads((prefix / "empa-orca-runtime.json").read_text())["archive_sha256"]
        == digest
    )
    assert any(Path(c[0]).name == "mpi-type-probe" for c in calls)
    # A verified installed program does not require retaining its original archive.
    path.unlink()
    assert orca.install(path, digest, prefix, mpi)["status"] == "INSTALLED_AND_CHECKED"


def test_non_native_or_nonexecutable_binary_is_rejected(tmp_path):
    path = tmp_path / "not-arm64"
    path.write_bytes(b"not-an-ELF")
    path.chmod(0o755)
    with pytest.raises(ValueError, match="not native"):
        orca.validate_binary(path)
