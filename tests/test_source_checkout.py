"""Resolve exact source from both editable and ordinary installed packages."""

import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    "source_checkout", Path(__file__).parents[1] / "scripts/source-checkout.py"
)
assert SPEC is not None and SPEC.loader is not None
source = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source)


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "canonical"
    subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    package = root / "package"
    package.mkdir()
    (package / "__init__.py").write_text("SELECTED = True\n")
    (root / "LICENSE").write_text("Preserve original licence\n")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "Selected source",
        ],
        check=True,
    )
    commit = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    return root, commit


def test_editable_checkout_is_retained_for_existing_content_guards(
    repository, monkeypatch
):
    root, commit = repository
    monkeypatch.setattr(
        source.importlib.util,
        "find_spec",
        lambda _: SimpleNamespace(origin=str(root / "package/__init__.py")),
    )
    with source.selected_checkout("package", root.as_uri(), commit) as selected:
        assert selected == root
    assert root.exists()


def test_noneditable_package_fetches_exact_commit_not_latest(
    repository, tmp_path, monkeypatch
):
    root, commit = repository
    # A newer remote tip must not change the exact selected runtime engine.
    (root / "package/__init__.py").write_text("SELECTED = False\n")
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--quiet",
            "-am",
            "Unselected later source",
        ],
        check=True,
    )
    origin = tmp_path / "site-packages/package/__init__.py"
    origin.parent.mkdir(parents=True)
    origin.write_text("INSTALLED_WHEEL = True\n")
    monkeypatch.setattr(
        source.importlib.util,
        "find_spec",
        lambda _: SimpleNamespace(origin=str(origin)),
    )
    with source.selected_checkout("package", root.as_uri(), commit) as selected:
        assert selected != root
        assert (selected / "package/__init__.py").read_text() == "SELECTED = True\n"
        assert (selected / "LICENSE").read_text() == "Preserve original licence\n"
        assert (
            subprocess.check_output(
                ["git", "-C", str(selected), "rev-parse", "HEAD"], text=True
            ).strip()
            == commit
        )
    assert not selected.exists()
    assert origin.read_text() == "INSTALLED_WHEEL = True\n"


def test_unrelated_ancestor_git_is_not_adopted(repository, monkeypatch):
    root, commit = repository
    origin = root / "untracked/site-packages/package/__init__.py"
    origin.parent.mkdir(parents=True)
    origin.write_text("ordinary package\n")
    monkeypatch.setattr(
        source.importlib.util,
        "find_spec",
        lambda _: SimpleNamespace(origin=str(origin)),
    )
    with source.selected_checkout("package", root.as_uri(), commit) as selected:
        assert selected != root and not (selected / "untracked").exists()


def test_absent_client_fails_without_fetch(monkeypatch):
    monkeypatch.setattr(source.importlib.util, "find_spec", lambda _: None)
    monkeypatch.setattr(
        source.subprocess,
        "run",
        lambda *a, **kw: pytest.fail("No fetch for absent client"),
    )
    with pytest.raises(ValueError, match="Install the selected"):
        with source.selected_checkout(
            "missing", "https://example.invalid/source", "0" * 40
        ):
            pass
