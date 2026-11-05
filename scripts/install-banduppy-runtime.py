"""Install a new isolated BandUPpy 1.0 worker with the selected native Python.

No AiiDA package/profile is installed or loaded. Existing prefixes are checked
and never upgraded in place. Use the Python that will run the worker.
"""

import argparse
import json
import os
import subprocess
import sys
import venv
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    args = parser.parse_args()
    if not args.executable.is_absolute():
        message = "Use an absolute worker executable path."
        raise ValueError(message)
    executable = args.executable
    prefix = executable.parent.parent
    if executable.name != "python" or executable.parent.name != "bin":
        message = "Use a PREFIX/bin/python worker executable."
        raise ValueError(message)
    if sys.version_info < (3, 11):
        message = "Select native Python >=3.11 for the separate worker."
        raise RuntimeError(message)
    marker = prefix / "empa-runtime.json"
    # Isolate venv's internal ensurepip subprocess from live AiiDA state.
    os.environ["AIIDA_PATH"] = str(prefix / "isolated-aiida")
    env = dict(os.environ)
    check = (
        "import ase, numpy, scipy, cloudpickle, banduppy; "
        "from importlib.metadata import version; "
        "assert version('banduppy') == '1.0.0'; print('banduppy-ready')"
    )
    if prefix.exists():
        if (
            not marker.is_file()
            or json.loads(marker.read_text()).get("banduppy") != "1.0.0"
        ):
            message = (
                "Prefix already exists without a matching completed marker. "
                "Review it and choose a new prefix."
            )
            raise RuntimeError(message)
    else:
        prefix.parent.mkdir(parents=True, exist_ok=True)
        venv.EnvBuilder(with_pip=True, symlinks=False).create(prefix)
        subprocess.run(
            [
                str(executable),
                "-m",
                "pip",
                "install",
                "banduppy==1.0.0",
                "ase",
                "cloudpickle",
            ],
            env=env,
            check=True,
        )
        subprocess.run([str(executable), "-c", check], env=env, check=True)
        with (prefix / "requirements-installed.txt").open("w") as stream:
            subprocess.run(
                [str(executable), "-m", "pip", "freeze", "--all"],
                env=env,
                check=True,
                stdout=stream,
            )
        marker.write_text(
            json.dumps(
                {
                    "banduppy": "1.0.0",
                    "python": sys.version,
                    "base_executable": sys.executable,
                },
                indent=2,
            )
            + "\n"
        )
    subprocess.run([str(executable), "-c", check], env=env, check=True)
    print(executable)


if __name__ == "__main__":
    main()
