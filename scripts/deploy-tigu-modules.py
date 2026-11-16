"""Install the same versioned Tigu stack in a private or administrator prefix.

Python3.8 is enough to bootstrap the checked Python3.12 toolchain. Default mode
is a plan. --execute installs selected families and writes only under the given
root/module tree. It never registers Codes, imports AiiDA, edits shell startup,
submits science or overwrites an existing unrelated installation/modulefile.
"""

import argparse
import grp
import hashlib
import importlib.util
import json
import os
import platform
import re
import shlex
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import NoReturn

HERE = Path(__file__).resolve().parent
RECIPES = HERE.parent / "runtime-recipes/tigu"
MICROMAMBA = {
    "url": (
        "https://github.com/mamba-org/micromamba-releases/releases/download/"
        "2.10.0-0/micromamba-linux-64"
    ),
    "sha256": "701f39c06f8e6a670a0e186c8479b9e5c0502a2f0cda6cef65d83bdd2875e8bd",
}
FAMILIES = {
    "cp2k": ("cp2k-2026.2-a0e486a", "empa/cp2k/2026.2-a0e486a"),
    "qe": ("qe-7.5", "empa/qe/7.5"),
    "banduppy": ("banduppy-1.0.0", "empa/banduppy/1.0.0"),
    "block2": ("block2-0.5.4", "empa/block2/0.5.4"),
    "render": ("cubehandler-245db38", "empa/cubehandler/245db38"),
    "support": ("support-20261116", "empa/support/20261116"),
    "helpers": ("orca-helpers-4d92f71", "empa/orca-helpers/4d92f71"),
    "julia": ("julia-1.12.6", "empa/julia/1.12.6"),
    "model": ("itensor-4f7f2f96-offline", "empa/itensor/0.4.3-4f7f2f96-offline"),
    "orca": ("site-orca", "empa/orca/6.1.1-mpi4.1.1"),
    "gaussian": ("site-gaussian", "empa/gaussian/16"),
}
LICENSED = {"orca", "gaussian"}
# Reproducible immutable build IDs distinguish corrected package/probe closures
# from retained failed prototypes without overwriting or relabelling them.
for _family in ("cp2k", "qe", "block2", "render", "support"):
    _build = hashlib.sha256((RECIPES / (_family + ".json")).read_bytes()).hexdigest()[
        :10
    ]
    _prefix, _module = FAMILIES[_family]
    FAMILIES[_family] = (_prefix + "-" + _build, _module + "-" + _build)


def fail(message: str) -> NoReturn:
    raise ValueError(message)


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def checked_path(value):
    path = Path(os.path.abspath(os.path.expanduser(str(value))))
    if path == Path("/") or re.search(r"[\x00-\x1f]", str(path)):
        fail(
            "Choose an absolute non-root installation directory "
            "without control characters."
        )
    for parent in (path, *path.parents):
        if parent.is_symlink():
            fail("Preserve and reconcile a symlinked deployment directory.")
    return path


def download(spec, cache):
    cache.mkdir(parents=True, exist_ok=True)
    name = spec.get("filename", spec["url"].rsplit("/", 1)[-1])
    if Path(name).name != name or not re.fullmatch(r"[0-9a-f]{64}", spec["sha256"]):
        fail("The locked artifact name/SHA is invalid.")
    # Conda needs the original package basename, not a prefixed filename.
    target = cache / spec["sha256"] / name
    if target.is_symlink():
        fail("An artifact cache file is a symlink.")
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".partial")
        if temporary.exists():
            fail("A partial artifact remains; review it before retrying.")
        print("Download " + name, flush=True)
        try:
            with urllib.request.urlopen(
                spec["url"], timeout=90
            ) as response, temporary.open("xb") as stream:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    stream.write(block)
            if digest(temporary) != spec["sha256"]:
                fail("Downloaded artifact SHA differs from the maintained lock.")
            temporary.rename(target)
        except BaseException:
            # Retain the exact failed/partial artifact and report its path.
            print("Retained download evidence: " + str(temporary), file=sys.stderr)
            raise
    if digest(target) != spec["sha256"]:
        fail("Cached artifact SHA differs from the maintained lock.")
    return target


def child_env(root):
    env = os.environ.copy()
    for key in (
        "PYTHONPATH",
        "PYTHONHOME",
        "PIP_PREFIX",
        "PIP_TARGET",
        "PIP_CONSTRAINT",
        "CONDA_PREFIX",
        "CONDA_DEFAULT_ENV",
        "LD_LIBRARY_PATH",
    ):
        env.pop(key, None)
    env.update(
        AIIDA_PATH=str(root / "isolated-installer-state"),
        PIP_USER="0",
        PYTHONNOUSERSITE="1",
        OMP_NUM_THREADS="1",
        OPENBLAS_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        CONDA_PKGS_DIRS=str(root / "conda-cache"),
        MAMBA_ROOT_PREFIX=str(root / "mamba-state"),
        MAMBA_EXTRACT_THREADS="2",
        MAMBA_DOWNLOAD_THREADS="4",
        PIP_CACHE_DIR=str(root / "pip-cache"),
        XDG_CACHE_HOME=str(root / "cache"),
        MPLCONFIGDIR=str(root / "matplotlib"),
    )
    env["PATH"] = str(root / "tools") + os.pathsep + env.get("PATH", "")
    return env


def bootstrap(root):
    """Exact complete official closure; never invoke the system/user pip."""
    tools = root / "tools"
    tools.mkdir(parents=True, exist_ok=True)
    manager = tools / "micromamba"
    if manager.exists():
        if manager.is_symlink() or digest(manager) != MICROMAMBA["sha256"]:
            fail("Existing package-manager identity differs; preserve it.")
    else:
        source = download(MICROMAMBA, root / "downloads")
        with manager.open("xb") as output, source.open("rb") as stream:
            output.write(stream.read())
        manager.chmod(0o755)
    recipe_path = RECIPES / "bootstrap.json"
    recipe = json.loads(recipe_path.read_text())
    prefix = root / "python312"
    receipt = root / "python312-receipt.json"
    if prefix.exists():
        if not receipt.is_file() or json.loads(receipt.read_text())[
            "recipe_sha256"
        ] != digest(recipe_path):
            fail(
                "An unknown/partial bootstrap prefix exists; "
                "preserve it and use a new root."
            )
        saved = json.loads(receipt.read_text())
        if digest(prefix / "bin/python3.12") != saved["python_sha256"]:
            fail("The installed bootstrap interpreter changed.")
        return prefix / "bin/python"
    files = [download(spec, root / "downloads") for spec in recipe["artifacts"]]
    explicit = root / "python312-explicit.txt"
    explicit.write_text("@EXPLICIT\n" + "\n".join(p.as_uri() for p in files) + "\n")
    subprocess.run(
        [
            str(manager),
            "create",
            "--yes",
            "--offline",
            "--prefix",
            str(prefix),
            "--file",
            str(explicit),
        ],
        env=child_env(root),
        check=True,
    )
    subprocess.run(
        [str(prefix / "bin/python"), "--version"], env=child_env(root), check=True
    )
    receipt.write_text(
        json.dumps(
            {
                "recipe_sha256": digest(recipe_path),
                "python_sha256": digest(prefix / "bin/python3.12"),
                "manager_sha256": digest(manager),
            },
            indent=2,
        )
        + "\n"
    )
    return prefix / "bin/python"


def tcl(value):
    return (
        "{"
        + str(value).replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
        + "}"
    )


def module_text(family, prefix, root, mpi=None):
    """Tcl modulefiles work with the site's Lmod and Environment Modules."""
    lines = [
        "#%Module1.0",
        "module-whatis " + tcl("EMPA reviewed " + family + " runtime"),
        "conflict " + tcl("empa/" + family),
        "prepend-path PATH " + tcl(prefix / "bin"),
        "prepend-path LD_LIBRARY_PATH " + tcl(prefix / "lib"),
        "setenv PYTHONNOUSERSITE 1",
        "setenv OPENBLAS_NUM_THREADS 1",
        "setenv MKL_NUM_THREADS 1",
        "if {[info exists env(SLURM_CPUS_PER_TASK)]} {",
        "    setenv OMP_NUM_THREADS $env(SLURM_CPUS_PER_TASK)",
        "} else {",
        "    setenv OMP_NUM_THREADS 1",
        "}",
        "setenv EMPA_"
        + family.upper()
        + "_RECEIPT "
        + tcl(root / "receipts" / (family + ".json")),
    ]
    if family == "cp2k":
        lines.append("setenv CP2K_DATA_DIR " + tcl(prefix / "share/cp2k/data"))
    if family == "model":
        lines += [
            "setenv ITENSOR_SPIN_CASE_ROOT " + tcl(prefix / "source/remote/engine"),
            "setenv ITENSOR_SPIN_JULIA "
            + tcl(root / FAMILIES["julia"][0] / "bin/julia"),
            "set shared_depot " + tcl(prefix / "depot"),
            (
                "setenv JULIA_DEPOT_PATH "
                '"$env(HOME)/.cache/empa/itensor-4f7f2f96:$shared_depot"'
            ),
            "setenv GKSwstype 100",
        ]
        lines.append("prepend-path PATH " + tcl(prefix / "source/remote"))
    if family == "orca":
        lines += [
            "prepend-path PATH " + tcl(prefix),
            "prepend-path PATH " + tcl(mpi / "bin"),
            "prepend-path LD_LIBRARY_PATH " + tcl(mpi / "lib"),
        ]
    if family == "gaussian":
        lines += [
            "prepend-path PATH " + tcl(prefix),
            "setenv GAUSS_EXEDIR " + tcl(prefix),
        ]
    return "\n".join(lines) + "\n"


def publish_file(path, data):
    path = checked_path(path)
    if path.exists():
        if path.read_text() != data:
            fail(
                "An existing modulefile differs; preserve it "
                "and select a new module tree."
            )
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x") as stream:
            stream.write(data)


def share_completed(root, modules, receipts, group):
    """Grant only the explicitly chosen group access to newly owned runtimes."""
    gid = grp.getgrnam(group).gr_gid
    if os.geteuid() != 0 and gid not in {os.getgid(), *os.getgroups()}:
        fail("The installer account is not a member of the selected shared group.")
    paths = {root}
    for prefix in [
        root / "python312",
        root / "tools",
        *(
            Path(r["prefix"])
            for r in receipts.values()
            if Path(r["prefix"]).is_relative_to(root)
        ),
    ]:
        if prefix.exists():
            paths.add(prefix)
            paths.update(p for p in prefix.rglob("*") if not p.is_symlink())
    for receipt in receipts.values():
        module = modules / receipt["module"]
        paths.add(module)
        parent = module.parent
        while parent != modules:
            paths.add(parent)
            parent = parent.parent
    if any(p.stat().st_uid != os.getuid() for p in paths):
        fail("An installation path has another owner; preserve its permissions.")
    for path in sorted(paths):
        mode = stat.S_IMODE(path.stat().st_mode)
        os.chown(path, -1, gid)
        os.chmod(
            path,
            mode
            | stat.S_IRGRP
            | (stat.S_IXGRP if path.is_dir() or mode & stat.S_IXUSR else 0),
        )


def verify_receipt(root, modules, family):
    receipt_path = root / "receipts" / (family + ".json")
    if not receipt_path.is_file() or receipt_path.is_symlink():
        fail("The requested family has no completed module receipt.")
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("status") != "MODULE_LOAD_VERIFIED":
        fail("The requested module did not complete its load check.")
    module = modules / receipt["module"]
    if module.is_symlink() or digest(module) != receipt["module_sha256"]:
        fail("The modulefile differs from its completed receipt.")
    for name, identity in receipt["executables"].items():
        if digest(Path(receipt["prefix"]) / name) != identity:
            fail("A module executable differs from its completed receipt.")
    for name, identity in receipt.get("external_files", {}).items():
        if digest(Path(name)) != identity:
            fail("A licensed program's selected MPI executable changed.")
    recipe = RECIPES / (family + ".json")
    if (
        family != "model"
        and family not in LICENSED
        and digest(recipe) != receipt["recipe_sha256"]
    ):
        fail("The module has another recipe than the selected candidate.")
    return receipt


def install_family(root, modules, family, module_init, site=None):
    if family in LICENSED:
        if (root / "receipts" / (family + ".json")).exists():
            return verify_receipt(root, modules, family)
        prefix = checked_path(site[family])
        names = ["orca", "orca_plot", "orca_2json"] if family == "orca" else ["g16"]
        if any(not os.access(str(prefix / name), os.X_OK) for name in names):
            fail(
                "The licensed site program is absent or this account "
                "has no executable access: " + family
            )
        for name in names:
            with (prefix / name).open("rb") as stream:
                header = stream.read(20)
            if (
                header[:6] != b"\x7fELF\x02\x01"
                or int.from_bytes(header[18:20], "little") != 62
            ):
                fail("The licensed site program is not native Linux x86_64.")
        # Never copy, modify, distribute or upgrade a licensed site installation.
        if family == "orca":
            mpi = checked_path(site["orca_mpi"])
            output = subprocess.check_output(
                [str(mpi / "bin/mpirun"), "--version"], text=True
            )
            if not re.search(r"\b4\.1\.1\b", output):
                fail("This Tigu ORCA distribution requires its selected site MPI4.1.1.")
        else:
            mpi = None
        external = {str(mpi / "bin/mpirun"): digest(mpi / "bin/mpirun")} if mpi else {}
        return publish_receipt(
            root,
            modules,
            family,
            prefix,
            names,
            {
                "recipe_sha256": hashlib.sha256(
                    json.dumps(
                        {name: digest(prefix / name) for name in names}, sort_keys=True
                    ).encode()
                ).hexdigest(),
                "external_files": external,
            },
            module_init,
            mpi,
        )
    spec = importlib.util.spec_from_file_location(
        "native_installer", HERE / "install-local-runtime.py"
    )
    assert spec is not None and spec.loader is not None
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    prefix = root / FAMILIES[family][0]
    env = child_env(root)
    env["PATH"] = str(root / "tools") + os.pathsep + env["PATH"]
    if family == "model":
        spec = importlib.util.spec_from_file_location(
            "model_installer", HERE / "prepare-itensor-runtime.py"
        )
        assert spec is not None and spec.loader is not None
        model = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(model)
        record = model.prepare(
            prefix,
            root / FAMILIES["julia"][0] / "bin/julia",
            "4f7f2f963bacb5e870fc118842004e31609c7c55",
            execute=True,
            bind_app=False,
            source_archive=site.get("model_source"),
            source_sha256=site.get("model_source_sha256"),
        )
        executable_paths = [
            "source/remote/itensor-spin-gs-local",
            "source/remote/itensor-spin-segment-local",
        ]
    else:
        # The installer receives command-scoped environment only.
        subprocess.run(
            [
                sys.executable,
                str(HERE / "install-local-runtime.py"),
                "--recipe",
                str(RECIPES / (family + ".json")),
                "--prefix",
                str(prefix),
                "--execute",
            ],
            env=env,
            check=True,
        )
        record = json.loads((prefix / "empa-runtime.json").read_text())
        executable_paths = json.loads((RECIPES / (family + ".json")).read_text())[
            "executables"
        ]
    return publish_receipt(
        root, modules, family, prefix, executable_paths, record, module_init
    )


def publish_receipt(
    root, modules, family, prefix, executable_paths, record, module_init, mpi=None
):
    module = FAMILIES[family][1]
    module_path = modules / module
    publish_file(module_path, module_text(family, prefix, root, mpi))
    body = (
        "source "
        + shlex.quote(str(module_init))
        + "\nmodule use "
        + shlex.quote(str(modules))
        + "\nmodule load "
        + shlex.quote(module)
        + "\n"
        + "\n".join(
            "test -x " + shlex.quote(str(prefix / name)) for name in executable_paths
        )
    )
    subprocess.run(["/bin/bash", "-ec", body], env=child_env(root), check=True)
    receipt = {
        "status": "MODULE_LOAD_VERIFIED",
        "family": family,
        "module": module,
        "prefix": str(prefix),
        "module_root": str(modules),
        "module_init": str(module_init),
        "module_sha256": digest(module_path),
        "recipe_sha256": record["recipe_sha256"],
        "executables": {name: digest(prefix / name) for name in executable_paths},
        "code_extras": record.get("code_extras", {}),
        "external_files": record.get("external_files", {}),
        "scientific_qualification": "NOT_PERFORMED",
        "installer_sha256": digest(Path(__file__)),
    }
    receipts = root / "receipts"
    receipts.mkdir(exist_ok=True)
    (receipts / (family + ".json")).write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--module-root", type=Path)
    parser.add_argument(
        "--module-init", type=Path, default=Path("/etc/profile.d/lmod.sh")
    )
    parser.add_argument(
        "--families", nargs="+", choices=["all", *FAMILIES], default=["all"]
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--check-family", choices=FAMILIES)
    parser.add_argument("--probe-family", choices=FAMILIES)
    parser.add_argument("--model-source", type=Path)
    parser.add_argument("--model-source-sha256")
    parser.add_argument(
        "--shared-group",
        help="Existing authorized site group; no groups/accounts are created.",
    )
    parser.add_argument(
        "--orca-root", type=Path, default=Path("/store/amsp/ORCA_6_1_1")
    )
    parser.add_argument("--orca-mpi", type=Path, default=Path("/opt/openmpi-4.1.1"))
    parser.add_argument("--gaussian-root", type=Path, default=Path("/opt/g16_avx2"))
    args = parser.parse_args()
    supplied = HERE.parent / "private-sources/model-source.json"
    if args.model_source is None and supplied.is_file():
        record = json.loads(supplied.read_text())
        args.model_source = supplied.parent / record["filename"]
        args.model_source_sha256 = record["sha256"]
    root = checked_path(args.root)
    modules = checked_path(args.module_root or root / "modulefiles")
    if args.check_family or args.probe_family:
        family = args.check_family or args.probe_family
        if args.probe_family and not (root / "receipts" / (family + ".json")).exists():
            print(json.dumps({"status": "MISSING", "family": family}))
            return
        print(json.dumps(verify_receipt(root, modules, family), sort_keys=True))
        return
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        fail(
            "Tigu deployment requires native Linux x86_64; "
            "no ARM64 binaries or emulation."
        )
    families = (
        list(FAMILIES) if "all" in args.families else list(dict.fromkeys(args.families))
    )
    if "model" in families and "julia" not in families:
        families.insert(0, "julia")
    plan = {
        "status": "PLAN_ONLY",
        "root": str(root),
        "module_root": str(modules),
        "families": {
            f: {
                "prefix": str(
                    {"orca": args.orca_root, "gaussian": args.gaussian_root}.get(
                        f, root / FAMILIES[f][0]
                    )
                ),
                "module": FAMILIES[f][1],
            }
            for f in families
        },
        "licensed_site_programs": (
            "Verify and expose existing licensed ORCA/Gaussian site installations "
            "and matching MPI without copying or upgrading them."
        ),
        "scientific_jobs": 0,
    }
    if not args.execute:
        print(json.dumps(plan, indent=2))
        return
    # Bound only this installer and its descendants, independently of the site's
    # Slurm accounting/affinity configuration. Never touch another process.
    allowed = sorted(os.sched_getaffinity(0))
    os.sched_setaffinity(0, set(allowed[:2]))
    print(
        json.dumps({"installer_allowed_cpus": sorted(os.sched_getaffinity(0))}),
        flush=True,
    )
    if not args.module_init.is_file():
        fail("Provide the site's real Lmod/Modules initialization file.")
    root.mkdir(parents=True, exist_ok=True)
    marker = root / "empa-stack-root.json"
    if not marker.exists():
        if any(p.name != "empa-stack-root.json" for p in root.iterdir()):
            fail(
                "The stack root is nonempty and unowned; "
                "preserve it and choose another."
            )
        marker.write_text(
            json.dumps({"kind": "empa-tigu-module-stack", "architecture": "x86_64"})
            + "\n"
        )
    elif (
        marker.is_symlink()
        or json.loads(marker.read_text()).get("kind") != "empa-tigu-module-stack"
    ):
        fail("The existing stack root is unowned or has another identity.")
    python = bootstrap(root)
    if Path(sys.executable).resolve() != python.resolve():
        env = child_env(root)
        os.execve(
            str(python),
            [str(python), str(Path(__file__).resolve()), *sys.argv[1:]],
            env,
        )
    results = {}
    failures = {}
    for family in families:
        print("Selected runtime: " + family, flush=True)
        try:
            results[family] = install_family(
                root,
                modules,
                family,
                args.module_init,
                {
                    "orca": args.orca_root,
                    "orca_mpi": args.orca_mpi,
                    "gaussian": args.gaussian_root,
                    "model_source": args.model_source,
                    "model_source_sha256": args.model_source_sha256,
                },
            )
            print(
                json.dumps(
                    {
                        "family": family,
                        "module": results[family]["module"],
                        "status": results[family]["status"],
                    }
                ),
                flush=True,
            )
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            failures[family] = str(error)
            print(
                json.dumps(
                    {"family": family, "status": "FAILED_RETAINED", "error": str(error)}
                ),
                flush=True,
            )
        (root / "deployment.json").write_text(
            json.dumps(
                {
                    "status": (
                        "FAILED_FAMILIES_RETAINED"
                        if failures
                        else "MODULE_INSTALLATION_COMPLETE_SCIENCE_PENDING"
                    ),
                    "families": results,
                    "failures": failures,
                },
                indent=2,
            )
            + "\n"
        )
    if failures:
        fail(
            "Selected runtime failures are recorded in deployment.json; "
            "no scientific submission was made."
        )
    if args.shared_group:
        share_completed(root, modules, results, args.shared_group)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit("Tigu deployment: " + str(error)) from error
