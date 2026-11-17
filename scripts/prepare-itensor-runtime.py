"""Prepare the committed Model Hamiltonians runtime; never submit or register jobs."""

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "runtime_installer", Path(__file__).with_name("install-local-runtime.py")
)
assert SPEC is not None and SPEC.loader is not None
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)

PROJECT = {
    "Project.toml": "d57ca8566d07e89f7a9270de236d16f922da3277ef2c1cc3a71de26a52daa148",
    "Manifest.toml": "82e919f11c298f6bb9882cd4a3772c47cfd93aaffea3018d3f7b30662e9be28a",
}


def recipe_identity(commit):
    data = {"source_commit": commit, "project_files": PROJECT}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def engine_identity(source):
    """Use the maintained backend setup helper's complete engine/wrapper scope."""
    paths = [
        source / "remote/itensor-spin-gs-local",
        source / "remote/itensor-spin-segment-local",
        *sorted((source / "remote/engine").glob("*.jl")),
        *sorted((source / "remote/engine/ITensor_libs").glob("*.jl")),
        source / "remote/engine/ITensor_env/Project.toml",
        source / "remote/engine/ITensor_env/Manifest.toml",
    ]
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def bind_gui(prefix):
    """Use the app's supported config and fallback depot; never overwrite either."""
    alias = Path.home() / ".julia-itensor-spin-localhost"
    depot = prefix / "depot"
    if alias.exists() or alias.is_symlink():
        if alias.resolve() != depot:
            installer.fail(
                "The Model app already has a different depot; "
                "preserve and reconcile it."
            )
    configured = Path.home() / ".config/aiidalab-itensor-spectra/model-runtime.json"
    desired = {"directory": str(prefix / "model-runtime")}
    if configured.is_symlink():
        installer.fail("The Model runtime configuration is a symlink; review it.")
    if configured.exists():
        if json.loads(configured.read_text()) != desired:
            installer.fail(
                "The Model app already has a different runtime configuration."
            )
    if not alias.exists() and not alias.is_symlink():
        alias.symlink_to(depot, target_is_directory=True)
    if not configured.exists():
        configured.parent.mkdir(parents=True, exist_ok=True)
        with configured.open("x") as stream:
            json.dump(desired, stream, indent=2)


def prepare(
    prefix,
    julia,
    source_commit,
    execute=False,
    bind_app=True,
    source_archive=None,
    source_sha256=None,
):
    prefix = installer.guarded_path(prefix)
    julia = Path(julia).resolve()
    if len(source_commit) != 40 or not all(
        c in "0123456789abcdef" for c in source_commit
    ):
        installer.fail("Select a full reviewed backend commit.")
    if not julia.is_file() or not os.access(julia, os.X_OK):
        installer.fail("Install the selected official Julia runtime first.")
    if (
        bind_app
        and os.environ.get("ITENSOR_SPIN_JULIA")
        and Path(os.environ["ITENSOR_SPIN_JULIA"]).resolve() != julia
    ):
        installer.fail(
            "The GUI has another explicit Julia selection; reconcile it before setup."
        )
    if (
        bind_app
        and os.environ.get("ITENSOR_SPIN_JULIA_DEPOT")
        and Path(os.environ["ITENSOR_SPIN_JULIA_DEPOT"]).resolve() != prefix / "depot"
    ):
        installer.fail(
            "The GUI has another explicit Julia depot; reconcile it before setup."
        )
    result = {
        "status": "PLAN_ONLY",
        "prefix": str(prefix),
        "source_commit": source_commit,
        "julia": str(julia),
        "project_files": PROJECT,
        "recipe_sha256": recipe_identity(source_commit),
        "scientific_jobs": 0,
        "bind_app": bind_app,
    }
    marker = prefix / "empa-model-runtime.json"
    if prefix.exists():
        if not marker.is_file():
            installer.fail(
                "An existing or partial Model prefix must be preserved and reviewed."
            )
        previous = json.loads(marker.read_text())
        if (
            previous.get("source_commit") != source_commit
            or previous.get("status") != "INSTALLED_AND_CHECKED"
            or previous.get("bind_app", True) != bind_app
        ):
            installer.fail(
                "The existing Model prefix has another source or is incomplete."
            )
        if any(
            installer.checksum(prefix / "source/remote/engine/ITensor_env" / name)
            != digest
            for name, digest in PROJECT.items()
        ):
            installer.fail("The frozen Model project changed.")
        if installer.checksum(julia) != previous.get("julia_sha256"):
            installer.fail(
                "The selected Julia executable differs from the prepared runtime."
            )
        source = prefix / "source"
        head = subprocess.check_output(
            ["git", "-C", source, "rev-parse", "HEAD"], text=True
        ).strip()
        dirty = subprocess.check_output(
            ["git", "-C", source, "status", "--porcelain", "--untracked-files=no"],
            text=True,
        )
        if head != source_commit or dirty:
            installer.fail("The committed Model engine checkout changed.")
        if bind_app:
            if installer.checksum(
                prefix / "model-runtime/runtime-manifest.json"
            ) != previous.get("exported_manifest_sha256"):
                installer.fail("The exported Model runtime manifest changed.")
            exported = json.loads(
                (prefix / "model-runtime/runtime-manifest.json").read_text()
            )
            if any(
                installer.checksum(prefix / "model-runtime" / name) != digest
                for name, digest in exported["files"].items()
            ):
                installer.fail("The exported Model engine changed.")
            if execute:
                bind_gui(prefix)
        return previous
    if not execute:
        return result
    prefix.mkdir(parents=True, mode=0o700)
    env = installer.isolated_environment(prefix)
    env.update(
        JULIA_DEPOT_PATH=str(prefix / "depot"),
        JULIA_LOAD_PATH="@:@stdlib",
        JULIA_NUM_THREADS="1,0",
        JULIA_NUM_PRECOMPILE_TASKS="1",
        JULIA_PKG_PRECOMPILE_AUTO="0",
        GKSwstype="100",
    )
    log = prefix / "preparation.log"
    result["status"] = "INSTALLING"
    try:
        source = prefix / "source"
        if source_archive is not None:
            if installer.checksum(source_archive) != source_sha256:
                installer.fail("The private canonical source capsule changed.")
            with tarfile.open(source_archive) as archive:
                if any(
                    m.name != "source" and not m.name.startswith("source/")
                    for m in archive.getmembers()
                ):
                    installer.fail("The source capsule contains unexpected paths.")
                archive.extractall(prefix, filter="data")
            capsule_head = subprocess.check_output(
                ["git", "-C", source, "rev-parse", "HEAD"], text=True
            ).strip()
            dirty = subprocess.check_output(
                ["git", "-C", source, "status", "--porcelain"], text=True
            )
            if capsule_head != source_commit or dirty:
                installer.fail("The capsule is not the exact clean canonical source.")
            result["source_archive_sha256"] = source_sha256
        else:
            installer.run(
                [
                    "git",
                    "clone",
                    "--no-checkout",
                    "https://github.com/nanotech-empa/aiida-itensor-spin.git",
                    source,
                ],
                env,
                log,
            )
        installer.run(
            ["git", "-C", source, "checkout", "--detach", source_commit], env, log
        )
        project = source / "remote/engine/ITensor_env"
        if any(
            installer.checksum(project / name) != digest
            for name, digest in PROJECT.items()
        ):
            installer.fail(
                "Selected backend does not contain the reviewed frozen Julia project."
            )
        installer.run(
            [
                str(julia),
                "--startup-file=no",
                "--threads=1,0",
                f"--project={project}",
                "-e",
                "using Pkg; Pkg.instantiate(; verbose=true); "
                "Pkg.precompile(; strict=true); "
                "using ITensors, ITensorMPS, JLD2, Plots, WignerSymbols, LaTeXStrings; "
                'println("FROZEN_ITENSOR_IMPORTS_OK")',
            ],
            env,
            log,
        )
        if any(
            installer.checksum(project / name) != digest
            for name, digest in PROJECT.items()
        ):
            installer.fail(
                "Julia changed a frozen project file; retain the prefix for diagnosis."
            )
        if bind_app:
            app = importlib.util.find_spec("aiidalab_itensor_spectra")
            if app is None or not app.origin:
                installer.fail("Install the Model Hamiltonians app before its runtime.")
            exporter = Path(app.origin).parent / "model_runtime.py"
            installer.run(
                [
                    sys.executable,
                    exporter,
                    "--source",
                    source,
                    "--revision",
                    source_commit,
                    "--destination",
                    prefix / "model-runtime",
                ],
                env,
                log,
            )
            bind_gui(prefix)
        result.update(
            status="INSTALLED_AND_CHECKED",
            julia_sha256=installer.checksum(julia),
            exported_manifest_sha256=(
                installer.checksum(prefix / "model-runtime/runtime-manifest.json")
                if bind_app
                else None
            ),
            verified_files={
                f"source/remote/itensor-spin-{kind}-local": installer.checksum(
                    source / f"remote/itensor-spin-{kind}-local"
                )
                for kind in ("gs", "segment")
            },
            code_extras={
                "engine_source_commit": source_commit,
                "engine_sha256": engine_identity(source),
                "supports_spin_graph": True,
                "supports_spectral_bond_cap": True,
                "supports_blas_execution_policy": True,
            },
        )
    except BaseException as error:
        result.update(status="FAILED", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        marker.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--julia", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-archive", type=Path)
    parser.add_argument("--source-sha256")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--compute-only",
        action="store_true",
        help="Prepare the remote engine/depot without changing any GUI home binding.",
    )
    args = parser.parse_args()
    try:
        result = prepare(
            args.prefix,
            args.julia,
            args.source_commit,
            args.execute,
            not args.compute_only,
            source_archive=args.source_archive,
            source_sha256=args.source_sha256,
        )
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Model runtime installation: {error}\n")
    installer.print_summary(
        result, args.prefix / "empa-model-runtime.json" if args.execute else None
    )


if __name__ == "__main__":
    main()
