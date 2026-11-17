"""Build a credential-free worker wheel from the installed clean PythTB app.

Keep the wheel private while the app repository is private. No runtime package
installation, AiiDA import or scientific execution is performed here.
"""

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import NoReturn


def fail(message: str) -> NoReturn:
    raise ValueError(message)


def create(checkout, destination, expected_engine):
    checkout, destination = Path(checkout).resolve(), Path(destination).resolve()
    dirty = subprocess.check_output(
        ["git", "-C", str(checkout), "status", "--porcelain"], text=True
    )
    if dirty:
        fail("Use a clean reviewed PythTB app checkout.")
    names = ("model.py", "numerics.py", "remote_worker.py")
    hashes = {
        name: hashlib.sha256((checkout / "aiidalab_tb" / name).read_bytes()).hexdigest()
        for name in names
    }
    engine = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    if engine != expected_engine:
        fail("The selected PythTB app differs from the catalog's worker source.")
    head = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
    ).strip()
    epoch = subprocess.check_output(
        ["git", "-C", str(checkout), "show", "-s", "--format=%ct", "HEAD"], text=True
    ).strip()
    if destination.exists():
        fail("Preserve an existing wheel output directory.")
    destination.mkdir(parents=True, mode=0o700)
    # Build a disposable tracked snapshot; never leave build/egg-info in an app.
    import io
    import sys
    import tarfile
    import tempfile

    blob = subprocess.check_output(["git", "-C", str(checkout), "archive", head])
    with tempfile.TemporaryDirectory(prefix="private-pythtb-wheel-") as temporary:
        source = Path(temporary) / "source"
        source.mkdir()
        with tarfile.open(fileobj=io.BytesIO(blob)) as archive:
            archive.extractall(source, filter="data")
        env = os.environ.copy()
        for key in (
            "PYTHONPATH",
            "PYTHONHOME",
            "PIP_CONSTRAINT",
            "PIP_TARGET",
            "PIP_PREFIX",
        ):
            env.pop(key, None)
        env.update(
            PIP_USER="0",
            AIIDA_PATH=str(Path(temporary) / "aiida-state"),
            SOURCE_DATE_EPOCH=epoch,
        )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--no-build-isolation",
                "--wheel-dir",
                str(destination),
                str(source / "worker"),
            ],
            env=env,
            check=True,
        )
    wheels = list(destination.glob("empa_pythtb_worker-*.whl"))
    if len(wheels) != 1:
        fail("Expected exactly one native worker wheel.")
    wheel = wheels[0]
    wheel.chmod(0o600)
    record = {
        "source_commit": head,
        "engine_sha256": engine,
        "source_files": hashes,
        "filename": wheel.name,
        "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "private_distribution_required": True,
        "scientific_jobs": 0,
    }
    metadata = destination / "pythtb-worker.json"
    metadata.write_text(json.dumps(record, indent=2) + "\n")
    metadata.chmod(0o600)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--engine-sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(create(args.checkout, args.output, args.engine_sha256), indent=2))


if __name__ == "__main__":
    main()
