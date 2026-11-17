"""Resolve reviewed source for editable or ordinary package installations.

An installed package directory need not contain Git history. Fetch only the
selected immutable commit from its canonical repository in a temporary checkout;
never derive a repository from the current directory or copy site-packages.
"""

import importlib.util
import os
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def selected_checkout(package, repository, commit):
    installed = importlib.util.find_spec(package)
    if installed is None or not installed.origin:
        message = f"Install the selected {package} client before its remote runtime."
        raise ValueError(message)
    if installed is not None and installed.origin:
        origin = Path(installed.origin).resolve()
        result = subprocess.run(
            ["git", "-C", str(origin.parent), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and origin.is_relative_to(
            Path(result.stdout.strip()).resolve()
        ):
            root = Path(result.stdout.strip()).resolve()
            tracked = subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "ls-files",
                    "--error-unmatch",
                    str(origin.relative_to(root)),
                ],
                capture_output=True,
            )
            if tracked.returncode == 0:
                # A real editable checkout remains subject to the caller's
                # clean-source/content guard. Never hide dirty user changes.
                yield root
                return

    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    with tempfile.TemporaryDirectory(prefix="empa-selected-source-") as directory:
        root = Path(directory) / "source"
        subprocess.run(["git", "init", "--quiet", str(root)], env=env, check=True)
        subprocess.run(
            ["git", "-C", str(root), "remote", "add", "origin", repository],
            env=env,
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "fetch",
                "--quiet",
                "--no-tags",
                "--depth=1",
                "origin",
                commit,
            ],
            env=env,
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(root), "checkout", "--quiet", "--detach", commit],
            env=env,
            check=True,
        )
        head = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], env=env, text=True
        ).strip()
        if head != commit:
            message = "Fetched source differs from the selected immutable commit."
            raise ValueError(message)
        yield root
