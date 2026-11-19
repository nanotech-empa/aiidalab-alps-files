"""Package the reviewed public installer plus private canonical Model source.

The resulting archive is private and is intended for Carlo to give Sasha. It
contains no credentials, AiiDA profile, user home, scientific data or licensed
ORCA/Gaussian binaries. Do not upload it to the public configuration repository.
"""

import argparse
import hashlib
import importlib.util
import io
import json
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import NoReturn

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> NoReturn:
    raise ValueError(message)


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / name)
    assert spec is not None and spec.loader is not None
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def package(checkout, output, pythtb_checkout):
    output = Path(output).expanduser().resolve()
    if output.is_relative_to(ROOT) or output.exists():
        fail("Use an absent private output outside the public catalog checkout.")
    dirty = subprocess.check_output(
        ["git", "-C", str(ROOT), "status", "--porcelain"], text=True
    )
    if dirty:
        fail(
            "Commit and verify the catalog candidate before making its private handoff."
        )
    commit = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    source_id, public = load("apply-tigu-stack.py").source_bundle(ROOT)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="private-tigu-handoff-") as temporary:
        root = Path(temporary) / "empa-tigu-installer"
        root.mkdir(mode=0o700)
        with tarfile.open(fileobj=io.BytesIO(public)) as archive:
            archive.extractall(root, filter="data")
        private = root / "private-sources"
        private.mkdir(mode=0o700)
        capsule = load("make-model-source.py").create(
            checkout, private / "model-source.tar.gz"
        )
        metadata = {
            key: capsule[key] for key in ["source_commit", "source_tree", "sha256"]
        }
        metadata["filename"] = "model-source.tar.gz"
        (private / "model-source.json").write_text(
            json.dumps(metadata, indent=2) + "\n"
        )
        (private / "model-source.json").chmod(0o600)
        worker_recipe = json.loads(
            (ROOT / "runtime-recipes/tigu/pythtb.json").read_text()
        )
        worker = load("make-pythtb-worker.py").create(
            pythtb_checkout,
            private / "pythtb",
            worker_recipe["worker"]["engine_sha256"],
            expected_worker=worker_recipe["worker"],
        )
        worker_metadata = dict(worker, filename="pythtb/" + worker["filename"])
        (private / "pythtb-worker.json").write_text(
            json.dumps(worker_metadata, indent=2) + "\n"
        )
        (private / "pythtb-worker.json").chmod(0o600)
        text = (
            "Private EMPA Tigu installer\n\n"
            "Run scripts/install-tigu-modules.sh --root /AUTHORIZED/PREFIX first "
            "to inspect the plan. Then run the same command under a small Slurm "
            "allocation with --execute. Choose --module-root if needed and "
            "--shared-group AUTHORIZED_GROUP for access by the intended users. "
            "No sudo, group creation or global shell changes are performed.\n\n"
            "Existing licensed ORCA/Gaussian locations are verified and exposed, "
            "not copied. Override --orca-root/--orca-mpi/--gaussian-root only "
            "for another explicitly verified site installation.\n\n"
            "The private Model source capsule and source-matching PythTB worker "
            "wheel are detected automatically. Keep "
            "this delivery restricted to authorized recipients. No GitHub token "
            "is required on a compute node.\n\n"
            "Installation/module checks and scientific qualification are distinct. "
            "Read docs/tigu-modules-for-administrator.md and the supplied source "
            "identity record.\n"
        )
        (root / "README.txt").write_text(text)
        docs = root / "docs"
        docs.mkdir()
        (docs / "tigu-modules-for-administrator.md").write_bytes(
            (ROOT / "docs/tigu-modules-for-administrator.md").read_bytes()
        )
        (root / "source-identity.json").write_text(
            json.dumps(
                {
                    "catalog_commit": commit,
                    "source_id": source_id,
                    "model": metadata,
                    "pythtb": worker_metadata,
                },
                indent=2,
            )
            + "\n"
        )
        with (
            output.open("xb") as stream,
            tarfile.open(fileobj=stream, mode="w:gz") as archive,
        ):
            archive.add(root, arcname=root.name)
        output.chmod(0o600)
    report = {
        "kind": "private-tigu-administrator-installer",
        "catalog_commit": commit,
        "source_id": source_id,
        "archive": str(output),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "private_model_source": metadata,
        "private_pythtb_worker": worker_metadata,
        "contains_credentials_or_scientific_data": False,
    }
    output.with_suffix(output.suffix + ".json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    output.with_suffix(output.suffix + ".json").chmod(0o600)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--checkout",
        required=True,
        type=Path,
        help="Clean selected private Model backend checkout",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--pythtb-checkout",
        required=True,
        type=Path,
        help="Clean source-matching PythTB app checkout",
    )
    args = parser.parse_args()
    print(
        json.dumps(package(args.checkout, args.output, args.pythtb_checkout), indent=2)
    )


if __name__ == "__main__":
    main()
