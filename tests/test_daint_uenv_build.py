"""Public recipe staging/submission contracts; no SSH/build/native execution."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "daint_build", Path(__file__).parents[1] / "scripts/build-daint-uenv.py"
)
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def recipe(tmp_path):
    path = tmp_path / "recipe"
    path.mkdir()
    for name in ("config.yaml", "compilers.yaml", "environments.yaml"):
        (path / name).write_text("name: test\n")
    return path


def test_plan_never_connects_or_builds(tmp_path, monkeypatch):
    monkeypatch.setattr(builder, "ssh", lambda *a: pytest.fail("No SSH for plan"))
    result = builder.build(
        recipe(tmp_path), "empa-test/v1@daint%gh200", "/remote/builds"
    )
    assert result["status"] == "PLAN" and result["scientific_jobs"] == 0


def test_stage_checks_existing_bytes_and_symlinks(tmp_path):
    source = recipe(tmp_path)
    identity, payload, _ = builder.recipe_bundle(source)
    dest = tmp_path / "remote"
    args = [sys.executable, "-c", builder.STAGE, str(dest), identity]
    result = subprocess.run(args, input=payload, capture_output=True, check=True)
    path = Path(json.loads(result.stdout)["recipe"])
    subprocess.run(args, input=payload, capture_output=True, check=True)
    (path / "config.yaml").write_text("preserve independent changes\n")
    failed = subprocess.run(args, input=payload, capture_output=True)
    assert failed.returncode != 0 and b"Existing staged recipe differs" in failed.stderr
    assert (path / "config.yaml").read_text() == "preserve independent changes\n"
    (source / "private-link").symlink_to(tmp_path / "unrelated")
    with pytest.raises(ValueError, match="symlinks"):
        builder.recipe_bundle(source)


@pytest.mark.parametrize(
    "exitcode,status", [(0, "SUBMITTED"), (1, "BUILD_SERVICE_REJECTED")]
)
def test_service_failure_receipt_and_no_duplicate_submission(
    tmp_path, exitcode, status
):
    source = recipe(tmp_path)
    tools = tmp_path / "bin"
    tools.mkdir()
    executable = tools / "uenv"
    executable.write_text(
        '#!/bin/sh\necho "service response"\nexit ' + str(exitcode) + "\n"
    )
    executable.chmod(0o755)
    env = {**os.environ, "PATH": str(tools) + os.pathsep + os.environ["PATH"]}
    args = [
        sys.executable,
        "-c",
        builder.BUILD,
        str(source),
        "empa-test/v1@daint%gh200",
    ]
    subprocess.run(args, env=env, capture_output=True, check=True)
    first = (source / "empa-build-submission.json").read_bytes()
    assert json.loads(first)["status"] == status
    assert json.loads(first)["control_performed"] is True
    failed = subprocess.run(args, env=env, capture_output=True)
    assert failed.returncode != 0 and b"already exists" in failed.stderr
    assert (source / "empa-build-submission.json").read_bytes() == first


def test_transport_failure_keeps_actual_control_uncertainty(tmp_path, monkeypatch):
    def ssh(host, args, data=None):
        if data is not None:
            return type("Reply", (), {"stdout": b'{"recipe":"/remote/staged"}'})()
        raise subprocess.CalledProcessError(255, ["ssh"], stderr=b"connection lost")

    monkeypatch.setattr(builder, "ssh", ssh)
    result = builder.build(
        recipe(tmp_path), "empa-test/v1@daint%gh200", "/remote", True
    )
    assert result["status"] == "SUBMISSION_OBSERVATION_FAILED"
    assert result["control_performed"].startswith("unknown")
    assert result["remote_recipe"] == "/remote/staged"
