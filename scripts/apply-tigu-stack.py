"""Selected setup task: exact source staging, module reuse, or private installation.

No AiiDA import, key manipulation, profile access or science submission. Normal
SSH authenticates the user. A missing module may start one bounded Slurm install
task; authentication failures or changed modules never trigger a fallback.
"""

import argparse
import hashlib
import importlib.util
import io
import json
import shlex
import subprocess
import tarfile
import tempfile
from contextlib import nullcontext
from pathlib import Path
from typing import NoReturn

HERE = Path(__file__).resolve().parent
ASSETS = [
    "LICENSE",
    "scripts/install-tigu-modules.sh",
    "scripts/deploy-tigu-modules.py",
    "scripts/install-local-runtime.py",
    "scripts/prepare-itensor-runtime.py",
    "scripts/prepare-pythtb-runtime.py",
    "scripts/make-pythtb-worker.py",
    "scripts/source-checkout.py",
    "scripts/check_orca_mpi.c",
]

# Python3.8-compatible remote stager. Only a fixed regular-file source bundle is
# accepted; all hashes are checked before creating its absent destination.
REMOTE_STAGE = r"""
import hashlib, io, json, os, pathlib, sys, tarfile, uuid

root = pathlib.Path(sys.argv[1])
expected = sys.argv[2]
kind = sys.argv[3] if len(sys.argv) > 3 else "empa-tigu-module-stack"
architecture = sys.argv[4] if len(sys.argv) > 4 else "x86_64"
if (kind, architecture) not in (
    ("empa-tigu-module-stack", "x86_64"),
    ("empa-daint-native-stack", "aarch64"),
):
    raise ValueError("Unexpected native source deployment owner/platform")
if (
    not root.is_absolute()
    or root == pathlib.Path("/")
    or root != pathlib.Path(os.path.abspath(str(root)))
):
    raise ValueError("Use an absolute non-root stack prefix")
for p in (root, *root.parents):
    if p.is_symlink():
        raise ValueError("Preserve symlinked stack prefix")
with tarfile.open(fileobj=io.BytesIO(sys.stdin.buffer.read())) as t:
    members = t.getmembers()
    if any(
        not m.isfile() or m.name.startswith("/") or ".." in pathlib.Path(m.name).parts
        for m in members
    ):
        raise ValueError("Source bundle contains nonregular/escaping members")
    data = {m.name: t.extractfile(m).read() for m in members}
    manifest = json.loads(data.pop("empa-source-manifest.json"))
    hashes = {name: hashlib.sha256(blob).hexdigest() for name, blob in data.items()}
    if (
        hashes != manifest
        or hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
        != expected
    ):
        raise ValueError("Source bundle differs from the inspected source identity")
marker = root / "empa-stack-root.json"
if root.exists() and not marker.is_file():
    raise ValueError("Existing stack prefix is unowned; preserve it")
if not root.exists():
    root.mkdir(parents=True)
    marker.write_text(
        json.dumps({"kind": kind, "architecture": architecture}) + "\n"
    )
if (
    marker.is_symlink()
    or json.loads(marker.read_text()).get("kind") != kind
    or json.loads(marker.read_text()).get("architecture") != architecture
):
    raise ValueError("Stack prefix has another owner/identity")
sources = root / "sources"
sources.mkdir(exist_ok=True)
if sources.is_symlink():
    raise ValueError("Source parent is symlinked")
dest = sources / expected
if dest.exists():
    actual = {
        p.relative_to(dest).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in dest.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }
    if dest.is_symlink() or actual != hashes:
        raise ValueError("Existing staged source differs; preserve it")
else:
    temporary = sources / (".stage-" + uuid.uuid4().hex)
    temporary.mkdir()
    for name, blob in data.items():
        path = temporary / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(blob)
        path.chmod(0o755 if name.endswith(".sh") else 0o644)
    temporary.rename(dest)
print(
    json.dumps(
        {"status": "VERIFIED_SOURCE", "source": str(dest), "source_id": expected}
    )
)
"""


def fail(message: str) -> NoReturn:
    raise ValueError(message)


def source_bundle(root=None, assets=None, include_recipes=True):
    root = Path(root or HERE.parent)
    paths = [root / name for name in (ASSETS if assets is None else assets)]
    if include_recipes:
        paths += sorted((root / "runtime-recipes/tigu").glob("*.json"))
    hashes = {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in paths
    }
    identity = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        for name in sorted(hashes):
            data = (root / name).read_bytes()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        data = json.dumps(hashes, sort_keys=True).encode()
        info = tarfile.TarInfo("empa-source-manifest.json")
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    return identity, output.getvalue()


def ssh(host, arguments, data=None):
    command = [
        "ssh",
        "-oBatchMode=yes",
        "-oStrictHostKeyChecking=yes",
        host,
        shlex.join(arguments),
    ]
    return subprocess.run(command, input=data, capture_output=True, check=True)


def source_checkout():
    spec = importlib.util.spec_from_file_location(
        "selected_source", HERE / "source-checkout.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stage_model_capsule(host, root):
    """Resolve the exact engine even from a non-editable client installation."""
    spec = importlib.util.spec_from_file_location(
        "model_capsule", HERE / "make-model-source.py"
    )
    assert spec is not None and spec.loader is not None
    maker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(maker)
    with source_checkout().selected_checkout(
        "aiida_itensor_spin",
        "https://github.com/nanotech-empa/aiida-itensor-spin.git",
        maker.COMMIT,
    ) as checkout, tempfile.TemporaryDirectory(prefix="model-transfer-") as directory:
        capsule = Path(directory) / "model-source.tar.gz"
        metadata = maker.create(checkout, capsule)
        blob = capsule.read_bytes()
    remote = (
        "import hashlib,pathlib,sys; r=pathlib.Path(sys.argv[1]); h=sys.argv[2]; "
        "d=r/'private-sources'; "
        "assert not d.is_symlink(); d.mkdir(mode=0o700,exist_ok=True); "
        "p=d/(h+'.tar.gz'); b=sys.stdin.buffer.read(); "
        "assert hashlib.sha256(b).hexdigest()==h; "
        "assert not p.is_symlink(); "
        "assert not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()==h; "
        "f=None if p.exists() else p.open('xb'); "
        "f is None or f.write(b); f is None or f.close(); p.chmod(0o600); print(str(p))"
    )
    result = ssh(host, ["python3", "-c", remote, str(root), metadata["sha256"]], blob)
    return result.stdout.decode().strip(), metadata["sha256"]


def stage_pythtb_worker(host, root, checkout=None):
    """Use the clean selected app; an explicit checkout avoids live activation."""
    source = importlib.util.spec_from_file_location(
        "pythtb_wheel", HERE / "make-pythtb-worker.py"
    )
    maker = importlib.util.module_from_spec(source)
    source.loader.exec_module(maker)
    recipe = json.loads((HERE.parent / "runtime-recipes/tigu/pythtb.json").read_text())
    selected = (
        nullcontext(Path(checkout))
        if checkout is not None
        else source_checkout().selected_checkout(
            "aiidalab_tb",
            "https://github.com/nanotech-empa/aiidalab-tb.git",
            "d9ab3fb5760fd6c06c297b280bd08ff79b00b20f",
        )
    )
    with selected as checkout, tempfile.TemporaryDirectory(
        prefix="private-pythtb-transfer-"
    ) as directory:
        output = Path(directory) / "wheel"
        metadata = maker.create(checkout, output, recipe["worker"]["engine_sha256"])
        blob = (output / metadata["filename"]).read_bytes()
    remote = (
        "import hashlib,pathlib,sys; r=pathlib.Path(sys.argv[1]); h=sys.argv[2]; "
        "n=sys.argv[3]; assert pathlib.Path(n).name==n and n.endswith('.whl'); "
        "d=r/'private-sources'; assert not d.is_symlink(); "
        "d.mkdir(mode=0o700,exist_ok=True); "
        "d=d/h; assert not d.is_symlink(); d.mkdir(mode=0o700,exist_ok=True); "
        "p=d/n; b=sys.stdin.buffer.read(); "
        "assert hashlib.sha256(b).hexdigest()==h; assert not p.is_symlink(); "
        "assert not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()==h; "
        "f=None if p.exists() else p.open('xb'); "
        "f is None or f.write(b); f is None or f.close(); p.chmod(0o600); print(str(p))"
    )
    result = ssh(
        host,
        ["python3", "-c", remote, str(root), metadata["sha256"], metadata["filename"]],
        blob,
    )
    return result.stdout.decode().strip(), metadata["sha256"]


def apply(host, root, module_root, family, expected, pythtb_checkout=None):
    identity, bundle = source_bundle()
    if identity != expected:
        fail(
            "Local installer files differ from the inspected catalog; "
            "synchronize and inspect again."
        )
    result = ssh(host, ["python3", "-c", REMOTE_STAGE, str(root), expected], bundle)
    source = json.loads(result.stdout)["source"]
    args = [
        "python3",
        source + "/scripts/deploy-tigu-modules.py",
        "--root",
        str(root),
        "--module-root",
        str(module_root),
    ]
    result = ssh(host, [*args, "--probe-family", family])
    provider = json.loads(result.stdout)
    if provider["status"] == "MODULE_LOAD_VERIFIED":
        print("Compatible module reused: " + provider["module"], flush=True)
        return provider
    if provider["status"] != "MISSING":
        fail("The selected module is invalid; preserve it and inspect the diagnosis.")
    private_args = []
    if family == "model":
        capsule, identity = stage_model_capsule(host, root)
        private_args = ["--model-source", capsule, "--model-source-sha256", identity]
    elif family == "pythtb":
        wheel, identity = stage_pythtb_worker(host, root, pythtb_checkout)
        private_args = ["--pythtb-wheel", wheel, "--pythtb-wheel-sha256", identity]
    command = [
        "ssh",
        "-oBatchMode=yes",
        "-oStrictHostKeyChecking=yes",
        host,
        shlex.join(
            [
                "srun",
                "--mpi=none",
                "--ntasks=1",
                "--cpus-per-task=2",
                "--mem=12G",
                "--time=02:00:00",
                "--cpu-bind=cores",
                *args,
                "--families",
                family,
                "--execute",
                *private_args,
            ]
        ),
    ]
    print("Install selected missing runtime on Tigu: " + family, flush=True)
    subprocess.run(command, check=True)
    provider = json.loads(ssh(host, [*args, "--check-family", family]).stdout)
    return provider


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-id", action="store_true")
    parser.add_argument("--host")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--module-root", type=Path)
    parser.add_argument("--family")
    parser.add_argument("--expected-source")
    parser.add_argument(
        "--pythtb-checkout",
        type=Path,
        help="Clean source-matching app checkout; defaults to the installed app",
    )
    args = parser.parse_args()
    if args.source_id:
        print(source_bundle()[0])
        return
    if not all(
        [args.host, args.root, args.module_root, args.family, args.expected_source]
    ):
        parser.error(
            "Supply the inspected host, stack/module roots, family and source identity."
        )
    try:
        result = apply(
            args.host,
            args.root,
            args.module_root,
            args.family,
            args.expected_source,
            args.pythtb_checkout,
        )
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        stderr = getattr(error, "stderr", None)
        detail = stderr.decode(errors="replace") if stderr else str(error)
        parser.exit(1, "Tigu source/provider command failed: " + detail + "\n")
    print(
        json.dumps(
            {
                key: result[key]
                for key in ["status", "family", "module", "recipe_sha256"]
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
