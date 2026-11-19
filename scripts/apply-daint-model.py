"""Prepare the existing frozen Model engine on Daint without public disclosure.

Reuses the same source stager, private capsule and Project/Manifest preparer as
Tigu. Native Julia is supplied by the shared public uenv. No scientific jobs,
Code registration, profile/service changes or SSH configuration edits occur.
"""

import argparse
import importlib.util
import json
import re
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn


def fail(message: str) -> NoReturn:
    raise ValueError(message)


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "native_transfer", HERE / "apply-tigu-stack.py"
)
assert SPEC is not None and SPEC.loader is not None
transfer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(transfer)
COMMIT = "4f7f2f963bacb5e870fc118842004e31609c7c55"


def ensure_image(host, image, image_source):
    try:
        transfer.ssh(host, ["uenv", "image", "inspect", "--json", image])
    except subprocess.CalledProcessError as error:
        diagnostic = (error.stdout or b"") + (error.stderr or b"")
        if isinstance(diagnostic, bytes):
            diagnostic = diagnostic.decode(errors="replace")
        if error.returncode == 255 or not any(
            term in diagnostic.lower()
            for term in ("no uenv matches", "not found", "no matching uenv")
        ):
            raise
        transfer.ssh(host, ["uenv", "image", "pull", image_source])


def apply(root, image, account, execute=False):
    image_source = image
    image = image.removeprefix("service::")
    root = Path(root)
    if not root.is_absolute() or root == Path("/") or ".." in root.parts:
        fail("Choose an absolute non-root owned Daint installation directory.")
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", account):
        fail("Use the selected Daint allocation account.")
    assets = [
        "LICENSE",
        "scripts/install-local-runtime.py",
        "scripts/prepare-itensor-runtime.py",
    ]
    identity, payload = transfer.source_bundle(assets=assets, include_recipes=False)
    prefix = root / ("model-" + COMMIT[:10])
    result = {
        "status": "PLAN",
        "source_commit": COMMIT,
        "source_id": identity,
        "prefix": str(prefix),
        "image": image,
        "image_source": image_source,
        "account": account,
        "private_engine_in_public_uenv": False,
        "scientific_jobs": 0,
    }
    if not execute:
        return result
    host = "daint.alps.cscs.ch"
    # Registry prefixes are download selectors, not valid run/Slurm labels.
    # Reuse an installed image without requiring any registry connection.
    ensure_image(host, image, image_source)
    staged = json.loads(
        transfer.ssh(
            host,
            [
                "python3",
                "-c",
                transfer.REMOTE_STAGE,
                str(root),
                identity,
                "empa-daint-native-stack",
                "aarch64",
            ],
            payload,
        ).stdout
    )
    capsule, digest = transfer.stage_model_capsule(host, root)
    command = [
        "srun",
        "--nodes=1",
        "--ntasks=1",
        "--cpus-per-task=2",
        "--mem=12G",
        "--time=02:00:00",
        "--account=" + account,
        "--uenv=" + image,
        "--view=default",
        "/user-environment/env/default/bin/python",
        staged["source"] + "/scripts/prepare-itensor-runtime.py",
        "--prefix",
        str(prefix),
        "--julia",
        "/user-environment/native/julia/bin/julia",
        "--source-commit",
        COMMIT,
        "--source-archive",
        capsule,
        "--source-sha256",
        digest,
        "--compute-only",
        "--execute",
    ]
    # Stream the existing preparer's progress rather than hiding a Julia build
    # in a captured SSH buffer. Keep an explicit local control receipt even if
    # the SSH client or preparation command fails after allocation starts.
    directory = Path.home() / ".cache/aiidalab-empa-setup/daint-model"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = directory / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json"
    )
    result.update(
        status="PREPARATION_STARTING",
        control_performed=False,
        receipt=str(receipt),
        command=command,
    )
    with receipt.open("x") as stream:
        json.dump(result, stream, indent=2)
    try:
        process = subprocess.Popen(
            [
                "ssh",
                "-oBatchMode=yes",
                "-oStrictHostKeyChecking=yes",
                host,
                shlex.join(command),
            ],
            stdin=subprocess.DEVNULL,
        )
        result.update(status="PREPARATION_RUNNING", control_performed=True)
        receipt.write_text(json.dumps(result, indent=2) + "\n")
        result["returncode"] = process.wait()
        subprocess.CompletedProcess(command, process.returncode).check_returncode()
        result.update(status="MODEL_PREPARATION_COMPLETED")
    except BaseException as error:
        result.update(status="PREPARATION_FAILED_RETAINED", error=str(error))
        raise
    finally:
        result["observed_utc"] = datetime.now(timezone.utc).isoformat()
        receipt.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--account", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(apply(args.root, args.image, args.account, args.execute), indent=2)
    )


if __name__ == "__main__":
    main()
