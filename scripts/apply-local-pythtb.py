"""Compose the source-matching native PythTB worker for a local ARM64 instance.

Reuse the maintained wheel builder, locked dependencies and receipt owner.
Planning never fetches, builds, installs, registers a Code or runs science.
"""

import argparse
import importlib.util
import json
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP_COMMIT = "902d3b00023f6d21a09c261cccc65bd72aaaff39"
APP_REPOSITORY = "https://github.com/nanotech-empa/aiidalab-tb.git"


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare(prefix, recipe, execute=False):
    runtime = load("prepare-pythtb-runtime.py")
    result = runtime.prepare(prefix, recipe)
    if not execute or result["status"] == "INSTALLED_AND_CHECKED":
        return result
    worker = json.loads(Path(recipe).read_text())["worker"]
    with (
        load("source-checkout.py").selected_checkout(
            "aiidalab_tb", APP_REPOSITORY, APP_COMMIT
        ) as source,
        tempfile.TemporaryDirectory(prefix="local-pythtb-wheel-") as temporary,
    ):
        output = Path(temporary) / "wheel"
        metadata = load("make-pythtb-worker.py").create(
            source, output, worker["engine_sha256"], expected_worker=worker
        )
        return runtime.prepare(
            prefix, recipe, output / metadata["filename"], metadata["sha256"], True
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    print(json.dumps(prepare(args.prefix, args.recipe, args.execute)))


if __name__ == "__main__":
    main()
