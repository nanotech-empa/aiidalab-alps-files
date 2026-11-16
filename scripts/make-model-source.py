"""Make a credential-free shallow source capsule for the private Model backend.

Only the verified canonical checkout is used. No local dirty files, credentials,
full home/profile, old research history or external licensed programs are copied.
Keep the capsule private; never add it to the public configuration repository.
"""

import argparse
import hashlib
import json
import os
import subprocess
import tarfile
import tempfile
from pathlib import Path

COMMIT = "4f7f2f963bacb5e870fc118842004e31609c7c55"


def create(checkout, output):
    checkout, output = Path(checkout).resolve(), Path(output).absolute()
    head = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
    ).strip()
    dirty = subprocess.check_output(
        ["git", "-C", str(checkout), "status", "--porcelain"], text=True
    )
    if head != COMMIT or dirty:
        message = "Use the clean selected canonical Model backend checkout."
        raise ValueError(message)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        message = "Source capsule output already exists; preserve it."
        raise ValueError(message)
    env = os.environ.copy()
    env.update(
        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0"
    )
    with tempfile.TemporaryDirectory(prefix="model-source-capsule-") as temporary:
        source = Path(temporary) / "source"
        subprocess.run(
            [
                "git",
                "clone",
                "--quiet",
                "--no-local",
                "--depth",
                "1",
                checkout.as_uri(),
                str(source),
            ],
            env=env,
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(source),
                "remote",
                "set-url",
                "origin",
                "https://github.com/nanotech-empa/aiida-itensor-spin.git",
            ],
            env=env,
            check=True,
        )
        with output.open("xb") as stream, tarfile.open(
            fileobj=stream, mode="w:gz"
        ) as archive:
            archive.add(source, arcname="source")
        output.chmod(0o600)
    result = {
        "kind": "private-canonical-model-source-capsule",
        "source_commit": COMMIT,
        "source_tree": subprocess.check_output(
            ["git", "-C", str(checkout), "rev-parse", "HEAD^{tree}"], text=True
        ).strip(),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "archive": str(output),
        "credentials_included": False,
        "private_distribution_required": True,
    }
    output.with_suffix(output.suffix + ".json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    output.with_suffix(output.suffix + ".json").chmod(0o600)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(create(args.checkout, args.output), indent=2))


if __name__ == "__main__":
    main()
