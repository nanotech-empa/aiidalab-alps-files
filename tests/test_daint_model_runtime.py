"""Frozen private Model deployment control without SSH, packages or jobs."""

import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    "daint_model", Path(__file__).parents[1] / "scripts/apply-daint-model.py"
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_default_plan_keeps_private_engine_outside_shared_image(tmp_path, monkeypatch):
    monkeypatch.setattr(
        module.transfer, "ssh", lambda *args: pytest.fail("No SSH for plan")
    )
    root = tmp_path / "model"
    result = module.apply(root, "selected-native-image", "selected-account")
    assert result["status"] == "PLAN" and result["scientific_jobs"] == 0
    assert not result["private_engine_in_public_uenv"]
    assert result["source_commit"] == "4f7f2f963bacb5e870fc118842004e31609c7c55"
    assert not root.exists()


def test_service_selector_is_not_used_as_a_runtime_label(tmp_path):
    result = module.apply(
        tmp_path / "model", "service::empa-model-native/2026.11:3075642581", "mr820"
    )
    assert result["image"] == "empa-model-native/2026.11:3075642581"
    assert result["image_source"] == "service::empa-model-native/2026.11:3075642581"


def test_authentication_failure_is_not_a_missing_image_fallback(tmp_path, monkeypatch):
    calls = []

    def failed(host, args, *rest):
        calls.append(args)
        raise subprocess.CalledProcessError(
            255, ["ssh"], stderr=b"Permission denied (publickey)"
        )

    monkeypatch.setattr(module.transfer, "ssh", failed)
    with pytest.raises(subprocess.CalledProcessError):
        module.apply(
            tmp_path / "model", "service::selected-native-image", "mr820", True
        )
    assert len(calls) == 1 and calls[0][:3] == ["uenv", "image", "inspect"]
    assert not (tmp_path / "model").exists()


@pytest.mark.parametrize("exit_code", [0, 7])
def test_control_receipt_survives_real_command_failure(
    tmp_path, monkeypatch, exit_code
):
    monkeypatch.setattr(module.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(
        module.transfer,
        "ssh",
        lambda *args: SimpleNamespace(stdout=b'{"source":"/selected/verified-tools"}'),
    )
    monkeypatch.setattr(
        module.transfer,
        "stage_model_capsule",
        lambda *args: ("/private/source.tar.gz", "a" * 64),
    )
    calls = []

    def launch(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(wait=lambda: exit_code, returncode=exit_code)

    monkeypatch.setattr(module.subprocess, "Popen", launch)
    if exit_code:
        with pytest.raises(subprocess.CalledProcessError):
            module.apply(tmp_path / "model", "selected-native-image", "mr820", True)
    else:
        assert (
            module.apply(tmp_path / "model", "selected-native-image", "mr820", True)[
                "status"
            ]
            == "MODEL_PREPARATION_COMPLETED"
        )
    (receipt,) = (tmp_path / ".cache/aiidalab-empa-setup/daint-model").glob("*.json")
    data = json.loads(receipt.read_text())
    assert data["control_performed"] is True and data["returncode"] == exit_code
    assert data["status"] == (
        "PREPARATION_FAILED_RETAINED" if exit_code else "MODEL_PREPARATION_COMPLETED"
    )
    command = calls[0][-1]
    assert "--cpus-per-task=2" in command and "--compute-only" in command
    assert "--source-sha256" in command and "--account=mr820" in command
