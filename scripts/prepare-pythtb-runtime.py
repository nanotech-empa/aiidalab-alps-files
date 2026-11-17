"""Compose the native PythTB worker from official dependencies and a private wheel.

The wheel is built from the installed clean app checkout before transfer. No
GitHub credentials, notebook home, AiiDA state or research files are copied.
"""

import argparse
import importlib.util
import json
import subprocess
from pathlib import Path
from typing import NoReturn


def fail(message: str) -> NoReturn:
    raise ValueError(message)


SPEC = importlib.util.spec_from_file_location(
    "native_installer", Path(__file__).with_name("install-local-runtime.py")
)
assert SPEC is not None and SPEC.loader is not None
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


def installed_files(prefix):
    result = installer.installed_files(prefix)
    result.pop("empa-pythtb-runtime.json", None)
    result.pop("installation.log", None)
    return result


def prepare(prefix, recipe, wheel=None, wheel_sha256=None, execute=False):
    prefix = installer.guarded_path(prefix)
    recipe = Path(recipe)
    data = json.loads(recipe.read_text())
    identity = installer.checksum(recipe)
    worker = data["worker"]
    marker = prefix / "empa-pythtb-runtime.json"
    if prefix.exists():
        if not marker.is_file() or marker.is_symlink():
            fail("Preserve an existing unowned PythTB prefix.")
        saved = json.loads(marker.read_text())
        if (
            saved.get("status") != "INSTALLED_AND_CHECKED"
            or saved.get("recipe_sha256") != identity
        ):
            fail("Preserve the incomplete or different PythTB runtime.")
        if installed_files(prefix) != saved["verified_files"]:
            fail("The composed PythTB runtime changed.")
        return saved
    result = {
        "status": "PLAN",
        "prefix": str(prefix),
        "recipe_sha256": identity,
        "worker": worker,
        "scientific_jobs": 0,
    }
    if not execute:
        return result
    if wheel is None or installer.checksum(wheel) != wheel_sha256:
        fail("Supply the reviewed private worker wheel with its exact SHA.")
    prefix.mkdir(parents=True)
    marker.write_text(json.dumps({**result, "status": "INSTALLING"}, indent=2))
    log = prefix / "installation.log"
    env = installer.isolated_environment(prefix)
    runtime = prefix / "runtime"
    try:
        installer.install(recipe, runtime, execute=True)
        installer.run(
            [
                runtime / "bin/python",
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--no-index",
                str(Path(wheel).resolve()),
            ],
            env,
            log,
        )
        response = subprocess.check_output(
            [str(runtime / "bin/empa-tb-worker"), "--manifest"], env=env, text=True
        )
        manifest = json.loads(response)
        if any(
            manifest.get(key) != worker[key] for key in ("protocol", "engine_sha256")
        ):
            fail("The installed PythTB engine differs from the selected app source.")
        installer.run([runtime / "bin/python", "-m", "pip", "check"], env, log)
        # A stable owned launcher is shared by module and direct Code bindings.
        launcher = prefix / "bin/empa-tb-worker"
        launcher.parent.mkdir()
        import shlex

        launcher.write_text(
            "#!/bin/sh\nexec "
            + shlex.quote(str(runtime / "bin/empa-tb-worker"))
            + ' "$@"\n'
        )
        launcher.chmod(0o755)
        result.update(
            status="INSTALLED_AND_CHECKED",
            worker_wheel_sha256=wheel_sha256,
            code_extras={
                "pythtb_worker": {
                    **worker,
                    "launcher_sha256": installer.checksum(launcher),
                }
            },
        )
        # The dependency layer has been composed with the recorded worker wheel.
        # Retain its original receipt, without falsely claiming unchanged files.
        layer = runtime / "empa-runtime.json"
        before = json.loads(layer.read_text())
        before["status"] = "DEPENDENCY_LAYER_COMPOSED"
        before["composed_runtime"] = str(marker)
        layer.write_text(json.dumps(before, indent=2) + "\n")
        result["verified_files"] = installed_files(prefix)
    except BaseException as error:
        result.update(status="FAILED_RETAINED", error=str(error))
        raise
    finally:
        marker.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--worker-wheel", type=Path)
    parser.add_argument("--wheel-sha256")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    result = prepare(
        args.prefix, args.recipe, args.worker_wheel, args.wheel_sha256, args.execute
    )
    installer.print_summary(result, args.prefix / "empa-pythtb-runtime.json")


if __name__ == "__main__":
    main()
