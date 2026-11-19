"""Install a user-supplied licensed Linux ARM64 ORCA archive and verify its MPI.

The program archive is never downloaded or redistributed by this repository.
Default mode only validates the supplied archive and prints a plan. The caller
installs the matching MPI recipe before passing --execute. No SCF/CASCI jobs,
AiiDA operations or licence acceptance are performed here.
"""

import argparse
import importlib.util
import json
import os
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "runtime_installer", Path(__file__).with_name("install-local-runtime.py")
)
assert SPEC is not None and SPEC.loader is not None
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


def validate_binary(path):
    if not os.access(path, os.X_OK):
        installer.fail("The supplied ORCA program is not executable.")
    with path.open("rb") as stream:
        header = stream.read(20)
    if (
        header[:4] != b"\x7fELF"
        or len(header) < 20
        or header[4:6] != bytes([2, 1])
        or int.from_bytes(header[18:20], "little") != 183
    ):
        installer.fail("The supplied ORCA executable is not native Linux ARM64.")


def install(archive, expected_sha256, prefix, mpi_prefix, execute=False):
    prefix, mpi_prefix = installer.guarded_path(prefix), installer.guarded_path(
        mpi_prefix
    )
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        installer.fail("Supply the vendor archive's full SHA-256.")
    if (
        installer.platform.system() != "Linux"
        or installer.platform.machine() != "aarch64"
    ):
        installer.fail("This ORCA recipe requires native Linux ARM64.")
    marker = prefix / "empa-orca-runtime.json"
    result = {
        "status": "PLAN_ONLY",
        "version": "6.1.1",
        "archive_sha256": expected_sha256,
        "prefix": str(prefix),
        "mpi_prefix": str(mpi_prefix),
        "scientific_jobs": 0,
    }
    if prefix.exists():
        if not marker.is_file():
            installer.fail(
                "Existing ORCA prefix is unowned/partial; preserve and review it."
            )
        previous = json.loads(marker.read_text())
        if (
            previous.get("status") != "INSTALLED_AND_CHECKED"
            or previous.get("archive_sha256") != expected_sha256
            or previous.get("mpi_prefix") != str(mpi_prefix)
        ):
            installer.fail(
                "Existing ORCA prefix has another archive/MPI or is incomplete."
            )
        if execute:
            for name, digest in previous["verified_files"].items():
                if installer.checksum(prefix / name) != digest:
                    installer.fail("The installed ORCA program changed.")
        return previous
    archive = Path(archive).expanduser()
    if not archive.is_file():
        installer.fail("Supply your licensed ORCA 6.1.1 Linux ARM64 archive first.")
    if installer.checksum(archive) != expected_sha256:
        installer.fail("Licensed archive SHA-256 differs from the reviewed selection.")
    if not execute:
        return result
    if not (mpi_prefix / "bin/mpicc").is_file():
        installer.fail(
            "Install the selected OpenMPI 4.1.8 compiler/runtime recipe first."
        )
    prefix.parent.mkdir(parents=True, exist_ok=True)
    env = installer.isolated_environment(prefix)
    env["PATH"] = str(mpi_prefix / "bin") + os.pathsep + env.get("PATH", "")
    env["LD_LIBRARY_PATH"] = str(mpi_prefix / "lib") + os.pathsep + str(prefix)
    env["OMPI_MCA_osc_sm_backing_directory"] = str(prefix.parent)
    log = prefix.parent / f".{prefix.name}-installation.log"
    result["status"] = "INSTALLING"
    try:
        with tarfile.open(archive) as stream:
            members = stream.getmembers()
            roots = {Path(v.name).parts[0] for v in members if Path(v.name).parts}
            if len(roots) != 1 or any(
                v.name.startswith("/") or ".." in Path(v.name).parts for v in members
            ):
                installer.fail(
                    "Expected one safe ORCA release directory inside the archive."
                )
            root = roots.pop()
            if not root.startswith("orca_6_1_1_"):
                installer.fail(
                    "This catalog selection requires the ORCA6.1.1 vendor archive."
                )
            with tempfile.TemporaryDirectory(dir=prefix.parent) as directory:
                stream.extractall(directory, filter="data")
                unpacked = Path(directory) / root
                for name in ("orca", "orca_plot", "orca_2json", "orca_startup_mpi"):
                    validate_binary(unpacked / name)
                unpacked.rename(prefix)
        version = subprocess.check_output(
            [str(mpi_prefix / "bin/mpirun"), "--version"], env=env, text=True
        )
        if "4.1.8" not in version:
            installer.fail(
                "The selected MPI is not the distribution's required OpenMPI 4.1.8."
            )
        for name in ("orca", "orca_startup_mpi"):
            links = subprocess.check_output(
                ["ldd", str(prefix / name)], env=env, text=True
            )
            if "not found" in links:
                installer.fail(f"ORCA shared-library dependencies are missing: {links}")
            if any(
                str(mpi_prefix) not in line
                for line in links.splitlines()
                if "libmpi" in line
            ):
                installer.fail(
                    "ORCA resolved an MPI library outside the selected runtime."
                )
        probe = Path(__file__).with_name("check_orca_mpi.c")
        compiler = mpi_prefix / "bin/aarch64-conda-linux-gnu-cc"
        env["OMPI_CC"] = str(compiler)
        target = subprocess.check_output(
            [str(compiler), "-dumpmachine"], env=env, text=True
        )
        if not target.startswith("aarch64"):
            installer.fail(
                "The MPI numeric-type probe compiler targets another architecture."
            )
        installer.run(
            [mpi_prefix / "bin/mpicc", probe, "-o", prefix / "mpi-type-probe"], env, log
        )
        installer.run([prefix / "mpi-type-probe"], env, log)
        result.update(
            status="INSTALLED_AND_CHECKED",
            mpi_version=version.strip(),
            verified_files=installer.installed_files(prefix),
        )
    except BaseException as error:
        result.update(status="FAILED", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        if prefix.exists():
            marker.write_text(json.dumps(result, indent=2) + "\n")
        else:
            (prefix.parent / f".{prefix.name}-failed-installation.json").write_text(
                json.dumps(result, indent=2) + "\n"
            )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--mpi-prefix", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        result = install(
            args.archive, args.sha256, args.prefix, args.mpi_prefix, args.execute
        )
    except (
        OSError,
        ValueError,
        subprocess.CalledProcessError,
        tarfile.TarError,
    ) as error:
        parser.exit(1, f"ORCA installation: {error}\n")
    installer.print_summary(
        result, args.prefix / "empa-orca-runtime.json" if args.execute else None
    )


if __name__ == "__main__":
    main()
