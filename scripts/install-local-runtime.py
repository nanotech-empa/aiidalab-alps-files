"""Install one reviewed Linux ARM64 runtime, never the active app environment.

Recipes and complete artifact identities live beside this script in Git. The
default is a plan; --execute claims a new prefix. Existing or interrupted
prefixes are never upgraded, deleted or silently adopted. No AiiDA imports,
profile operations, Code registration or scientific calculations belong here.
"""

import argparse
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import venv
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn
from urllib.parse import unquote


def fail(message: str) -> NoReturn:
    """Report an installation contract failure without hiding its cause."""
    raise ValueError(message)


def checksum(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def installed_files(prefix):
    """Ignore interpreter caches, retain immutable source/data/library identities."""
    files = {}
    inodes = {}
    for path in sorted(prefix.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        relative = path.relative_to(prefix).as_posix()
        if relative == "empa-runtime.json":
            continue
        stat = path.stat()
        key = (stat.st_dev, stat.st_ino)
        if key not in inodes:
            inodes[key] = checksum(path)
        files[relative] = inodes[key]
    return files


def guarded_path(value):
    path = Path(value).expanduser()
    if not path.is_absolute() or path != Path(os.path.abspath(path)):
        fail("Use a normalized absolute runtime prefix.")
    if path == Path(path.anchor):
        fail("The filesystem root is not a runtime prefix.")
    for item in (path, *path.parents):
        if item.is_symlink():
            fail(f"Runtime path contains a symlink: {item}")
    return path


def isolated_environment(prefix):
    env = os.environ.copy()
    for key in (
        "PYTHONPATH",
        "PYTHONHOME",
        "PIP_PREFIX",
        "PIP_TARGET",
        "PIP_CONSTRAINT",
        "CONDA_PREFIX",
        "CONDA_DEFAULT_ENV",
    ):
        env.pop(key, None)
    env.update(
        AIIDA_PATH=str(prefix.parent / f".{prefix.name}-installer-aiida"),
        PYTHONNOUSERSITE="1",
        PIP_USER="0",
        PIP_DISABLE_PIP_VERSION_CHECK="1",
        PIP_CACHE_DIR=str(prefix.parent / ".empa-pip-cache"),
        XDG_CACHE_HOME=str(prefix.parent / ".empa-runtime-cache"),
        MPLCONFIGDIR=str(prefix.parent / ".empa-matplotlib"),
        MPLBACKEND="Agg",
        OMP_NUM_THREADS="1",
        OPENBLAS_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        MAKEFLAGS="-j2",
        CMAKE_BUILD_PARALLEL_LEVEL="2",
        CONDA_PKGS_DIRS=str(prefix.parent / ".empa-conda-cache" / prefix.name),
        MAMBA_ROOT_PREFIX=str(prefix.parent / ".empa-mamba" / prefix.name),
    )
    return env


def run(arguments, env, log, cwd=None):
    """Stream concise progress; keep complete compiler/tool output in the log."""
    tool = Path(arguments[0]).name
    print(f"Running {tool}; full output: {log}", flush=True)
    with Path(log).open("a") as output:
        process = subprocess.Popen(
            list(map(str, arguments)),
            env=env,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            while True:
                try:
                    result = process.wait(timeout=5)
                    break
                except subprocess.TimeoutExpired:
                    print(f"{tool} is running; log: {log}", flush=True)
        except BaseException:
            process.terminate()
            process.wait()
            raise
    if result:
        with Path(log).open("rb") as output:
            output.seek(max(0, output.seek(0, 2) - 8192))
            print(output.read().decode("utf-8", errors="replace"), flush=True)
        raise subprocess.CalledProcessError(result, arguments)


def print_summary(result, receipt=None):
    """Full file/artifact manifests belong in a receipt, not a notebook output."""
    summary = {
        key: result[key]
        for key in (
            "status",
            "recipe",
            "prefix",
            "recipe_sha256",
            "installer_sha256",
            "version",
            "source_commit",
            "archive_sha256",
        )
        if key in result
    }
    if "artifacts" in result:
        summary["artifact_count"] = len(result["artifacts"])
    if "verified_files" in result:
        summary["verified_file_count"] = len(result["verified_files"])
    if receipt:
        summary["receipt"] = str(receipt)
    print(json.dumps(summary, indent=2))


def build_sources(recipe, prefix, downloads, env, log):
    """Build only native sources declared in the reviewed recipe, not the app."""
    for key in (
        "CC",
        "CXX",
        "FC",
        "F77",
        "CFLAGS",
        "CXXFLAGS",
        "FCFLAGS",
        "FFLAGS",
        "CPPFLAGS",
        "LDFLAGS",
        "AR",
        "AS",
        "LD",
        "HOST",
        "BUILD",
    ):
        env.pop(key, None)
    env["PATH"] = str(prefix / "bin") + os.pathsep + env.get("PATH", "")
    env["LD_LIBRARY_PATH"] = str(prefix / "lib")
    for name, target in recipe.get("compiler_aliases", {}).items():
        path, executable = prefix / "bin" / name, prefix / "bin" / target
        if (
            Path(name).name != name
            or Path(target).name != target
            or not executable.is_file()
        ):
            fail("A native compiler alias is invalid.")
        if not path.exists() and not path.is_symlink():
            path.symlink_to(target)
    for build in recipe.get("native_builds", []):
        entry = next(
            (
                p
                for p, spec in zip(downloads, recipe["artifacts"], strict=True)
                if spec["name"] == build["artifact"]
            ),
            None,
        )
        if entry is None:
            fail("A native build has no hashed source artifact.")
        build_root = prefix / ".empa-build" / build["artifact"]
        build_root.mkdir(parents=True, exist_ok=False)
        with tarfile.open(entry) as archive:
            top = build["archive_root"]
            if any(
                m.name != top and not m.name.startswith(top + "/")
                for m in archive.getmembers()
            ):
                fail("Native source archive has unexpected paths.")
            archive.extractall(build_root, filter="data")
        source = build_root / top

        def replace(value, source=source):
            return value.replace("@PREFIX@", str(prefix)).replace(
                "@SOURCE@", str(source)
            )

        build_env = dict(env)
        build_env.update(
            {key: replace(value) for key, value in build.get("environment", {}).items()}
        )
        for name in ("CC", "CXX", "FC", "F77"):
            if build_env.get(name):
                target = subprocess.check_output(
                    [build_env[name], "-dumpmachine"], env=build_env, text=True
                )
                if not target.startswith(recipe["architecture"]):
                    fail("A selected native compiler targets another architecture.")
        for command in build["commands"]:
            run([replace(v) for v in command], build_env, log, cwd=source)


def artifact(spec, directory):
    """Hash every artifact, including a pre-existing download, before use."""
    url, digest = spec["url"], spec["sha256"]
    if not url.startswith("https://") or not re.fullmatch(r"[0-9a-f]{64}", digest):
        fail("Artifacts require an HTTPS URL and full SHA-256.")
    directory = guarded_path(directory / digest)
    filename = spec.get("filename", unquote(url.rsplit("/", 1)[-1]))
    if Path(filename).name != filename or filename in {".", ".."}:
        fail("An artifact filename must be a basename.")
    path = directory / filename
    directory.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        fail("An artifact cache entry is a symlink.")
    if not path.exists():
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as stream:
            temporary = Path(stream.name)
            try:
                with urllib.request.urlopen(url, timeout=60) as response:
                    shutil.copyfileobj(response, stream)
                stream.flush()
                if checksum(temporary) != digest:
                    fail("Downloaded artifact SHA-256 differs from the recipe.")
                temporary.rename(path)
            finally:
                temporary.unlink(missing_ok=True)
    if checksum(path) != digest:
        fail("Cached artifact SHA-256 differs from the recipe.")
    return path


def runtime_library_path(prefix, recipe):
    """Include only the explicit native image libraries required by a recipe."""
    paths = [str(prefix / "lib"), *recipe.get("library_paths", [])]
    if any(
        not Path(p).is_absolute()
        or ".." in Path(p).parts
        or any(ord(c) < 32 for c in p)
        for p in paths
    ):
        fail("Native library paths must be explicit absolute paths.")
    return os.pathsep.join(paths)


def verify(prefix, recipe, env, log):
    for name in recipe.get("executables", []):
        path = prefix / name
        if not path.is_file() or not os.access(path, os.X_OK):
            fail(f"Required executable is unavailable: {name}")
    for name in recipe.get("data_files", []):
        if not (prefix / name).is_file():
            fail(f"Required runtime data is unavailable: {name}")
    local_env = dict(env)
    local_env["PATH"] = str(prefix / "bin") + os.pathsep + env.get("PATH", "")
    local_env["LD_LIBRARY_PATH"] = runtime_library_path(prefix, recipe)
    if recipe["kind"] == "pip-prefix":
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
        site = prefix / f"lib/python{python_version}/site-packages"
        local_env["PYTHONPATH"] = str(site)
    check_root = Path(
        tempfile.mkdtemp(prefix="." + prefix.name + "-checks-", dir=prefix.parent)
    )
    if recipe["kind"] == "conda" and any(
        a.get("type") == "python-source" for a in recipe.get("artifacts", [])
    ):
        run(
            [prefix / "bin/python", "-m", "pip", "check"],
            local_env,
            log,
            cwd=check_root,
        )
    for arguments in recipe.get("checks", []):
        command = [
            str(prefix / v[8:]) if v.startswith("@PREFIX/") else v for v in arguments
        ]
        command = [sys.executable if v == "@PYTHON" else v for v in command]
        run(command, local_env, log, cwd=check_root)


def install_source_files(prefix, recipe, downloads):
    """Retain exact canonical standalone worker files without installing AiiDA."""
    for spec in recipe.get("source_files", []):
        target = prefix / spec["destination"]
        if (
            Path(spec["destination"]).is_absolute()
            or ".." in Path(spec["destination"]).parts
            or target.exists()
            or target.is_symlink()
        ):
            fail("A canonical worker file would escape or overwrite its prefix.")
        archive_path = next(
            path
            for path, artifact_spec in zip(downloads, recipe["artifacts"], strict=True)
            if artifact_spec["name"] == spec["artifact"]
        )
        with tarfile.open(archive_path) as archive:
            member = archive.getmember(spec["member"])
            if not member.isfile():
                fail("Canonical worker source must be a regular archive member.")
            source = archive.extractfile(member)
            assert source is not None
            with source:
                content = source.read()
        if hashlib.sha256(content).hexdigest() != spec["sha256"]:
            fail("Canonical worker source SHA-256 differs from its recipe.")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def install(recipe_path, prefix, execute=False):
    recipe_path, prefix = Path(recipe_path).resolve(), guarded_path(prefix)
    recipe = json.loads(recipe_path.read_text())
    if recipe.get("schema") != 1 or recipe.get("kind") not in {
        "conda",
        "pip-prefix",
        "venv",
        "archive",
    }:
        fail("Unsupported runtime recipe.")
    if recipe["architecture"] not in {"aarch64", "x86_64"}:
        fail("Unsupported native architecture in runtime recipe.")
    if platform.system() != "Linux" or platform.machine() != recipe["architecture"]:
        fail(
            f"This recipe requires native Linux {recipe['architecture']}; "
            "emulation is not qualified."
        )
    if recipe.get("python") and list(sys.version_info[:2]) != recipe["python"]:
        fail("The runtime wheel requires the recipe's Python interpreter.")
    identity = checksum(recipe_path)
    marker = prefix / "empa-runtime.json"
    record = prefix.parent / f".{prefix.name}-installation.json"
    log = prefix.parent / f".{prefix.name}-installation.log"
    env = isolated_environment(prefix)
    if recipe.get("library_paths"):
        env["LD_LIBRARY_PATH"] = runtime_library_path(prefix, recipe)
    for key, value in recipe.get("build_environment", {}).items():
        if key not in {"CC", "CXX", "FC", "F77", "MPICC", "MPI4PY_BUILD_MPICC"}:
            fail("Unsupported explicit native compiler setting.")
        if not Path(value).is_absolute() or ".." in Path(value).parts:
            fail("Use an absolute native compiler executable.")
        env[key] = value
    if prefix.exists():
        if not marker.is_file() or marker.is_symlink():
            fail(
                "Prefix exists without a completed recipe. "
                "Review it; choose a new prefix."
            )
        receipt = json.loads(marker.read_text())
        if (
            receipt.get("recipe_sha256") != identity
            or receipt.get("status") != "INSTALLED_AND_CHECKED"
        ):
            fail("Existing runtime has a different or incomplete recipe.")
        if execute:
            if installed_files(prefix) != receipt.get("verified_files"):
                fail("Installed runtime file changed, is missing or is unexpected.")
            verify(prefix, recipe, env, log)
        return {
            "status": "MATCHING_EXISTING_RUNTIME",
            "prefix": str(prefix),
            "recipe_sha256": identity,
        }
    if record.exists():
        fail("An earlier attempt exists. Review its log; choose a new prefix.")
    result = {
        "status": "PLAN_ONLY",
        "recipe": recipe["id"],
        "recipe_sha256": identity,
        "installer_sha256": checksum(Path(__file__)),
        "prefix": str(prefix),
        "architecture": recipe["architecture"],
        "artifacts": recipe["artifacts"],
        "scientific_execution": False,
    }
    if not execute:
        return result
    prefix.parent.mkdir(parents=True, exist_ok=True)
    result.update(
        status="INSTALLING", started_utc=datetime.now(timezone.utc).isoformat()
    )
    with record.open("x") as stream:
        json.dump(result, stream, indent=2)
    try:
        cache = prefix.parent / ".empa-runtime-artifacts"
        downloads = []
        for index, spec in enumerate(recipe["artifacts"], start=1):
            print(
                f"Artifact {index}/{len(recipe['artifacts'])}: {spec['name']}",
                flush=True,
            )
            downloads.append(artifact(spec, cache))
        if recipe["kind"] == "conda":
            manager = (
                shutil.which("micromamba")
                or shutil.which("mamba")
                or shutil.which("conda")
            )
            if not manager:
                fail(
                    "This runtime needs its selected "
                    "micromamba/mamba/conda package manager."
                )
            explicit = record.with_suffix(".explicit.txt")
            conda_files = [
                p
                for p, spec in zip(downloads, recipe["artifacts"], strict=True)
                if spec.get("type", "conda") == "conda"
            ]
            explicit.write_text(
                "@EXPLICIT\n" + "\n".join(p.as_uri() for p in conda_files) + "\n"
            )
            run(
                [
                    manager,
                    "create",
                    "--yes",
                    "--offline",
                    "--prefix",
                    prefix,
                    "--file",
                    explicit,
                ],
                env,
                log,
            )
            build_sources(recipe, prefix, downloads, env, log)
            python_files = [
                p.as_uri() + "#sha256=" + spec["sha256"]
                for p, spec in zip(downloads, recipe["artifacts"], strict=True)
                if spec.get("type") == "python-source"
            ]
            if python_files:
                run(
                    [
                        prefix / "bin/python",
                        "-m",
                        "pip",
                        "install",
                        "--no-index",
                        "--no-deps",
                        "--no-build-isolation",
                        *python_files,
                    ],
                    env,
                    log,
                )
        elif recipe["kind"] == "pip-prefix":
            wheels = [
                p.as_uri() + "#sha256=" + spec["sha256"]
                for p, spec in zip(downloads, recipe["artifacts"], strict=True)
            ]
            run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--no-deps",
                    "--no-index",
                    "--ignore-installed",
                    "--prefix",
                    prefix,
                    *wheels,
                ],
                env,
                log,
            )
        elif recipe["kind"] == "venv":
            wheels = [
                p.as_uri() + "#sha256=" + spec["sha256"]
                for p, spec in zip(downloads, recipe["artifacts"], strict=True)
                if spec.get("type") not in {"source-files", "python-source"}
            ]
            venv.EnvBuilder(with_pip=True, symlinks=False).create(prefix)
            run(
                [
                    prefix / "bin/python",
                    "-m",
                    "pip",
                    "install",
                    "--no-deps",
                    "--no-index",
                    *wheels,
                ],
                env,
                log,
            )
            sources = [
                p.as_uri()
                + "#sha256="
                + spec["sha256"]
                + (
                    "&subdirectory=" + spec["subdirectory"]
                    if spec.get("subdirectory")
                    else ""
                )
                for p, spec in zip(downloads, recipe["artifacts"], strict=True)
                if spec.get("type") == "python-source"
            ]
            if sources:
                run(
                    [
                        prefix / "bin/python",
                        "-m",
                        "pip",
                        "install",
                        "--no-index",
                        "--no-deps",
                        "--no-build-isolation",
                        *sources,
                    ],
                    env,
                    log,
                )
        else:
            with tarfile.open(downloads[0]) as archive:
                members = archive.getmembers()
                top = recipe["archive_root"]
                if any(
                    m.name != top and not m.name.startswith(top + "/") for m in members
                ):
                    fail("Archive members differ from the expected release root.")
                with tempfile.TemporaryDirectory(dir=prefix.parent) as directory:
                    archive.extractall(directory, filter="data")
                    (Path(directory) / top).rename(prefix)
        install_source_files(prefix, recipe, downloads)
        for name, text in recipe.get("launchers", {}).items():
            if Path(name).is_absolute() or ".." in Path(name).parts:
                fail("A generated launcher must stay inside the runtime.")
            path = prefix / name
            if not path.is_relative_to(prefix) or path.exists() or path.is_symlink():
                fail("A generated launcher would overwrite an installed file.")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text.replace("@PREFIX@", shlex.quote(str(prefix))))
            path.chmod(0o755)
        verify(prefix, recipe, env, log)
        print("Recording installed source, data and library fingerprints", flush=True)
        result.update(
            status="INSTALLED_AND_CHECKED",
            verified_files=installed_files(prefix),
            completed_utc=datetime.now(timezone.utc).isoformat(),
        )
        if recipe.get("code_extras"):
            result["code_extras"] = recipe["code_extras"]
            for value in result["code_extras"].values():
                if value.pop("hash_launcher", None):
                    value["launcher_sha256"] = checksum(
                        prefix / recipe["executables"][0]
                    )
        marker.write_text(json.dumps(result, indent=2) + "\n")
    except BaseException as error:
        result.update(
            status="FAILED",
            error=f"{type(error).__name__}: {error}",
            failed_utc=datetime.now(timezone.utc).isoformat(),
        )
        raise
    finally:
        record.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        result = install(args.recipe, args.prefix, args.execute)
    except (
        OSError,
        ValueError,
        subprocess.CalledProcessError,
        tarfile.TarError,
    ) as error:
        parser.exit(1, f"Runtime installation: {error}\n")
    print_summary(result, args.prefix / "empa-runtime.json" if args.execute else None)


if __name__ == "__main__":
    main()
