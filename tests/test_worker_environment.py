"""Native workers do not inherit the notebook's interactive graphics backend."""

import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "worker_install", ROOT / "scripts/install-local-runtime.py"
)
assert SPEC is not None and SPEC.loader is not None
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


def test_install_and_probe_use_headless_child_without_changing_notebook(
    tmp_path, monkeypatch
):
    notebook = "module://matplotlib_inline.backend_inline"
    monkeypatch.setenv("MPLBACKEND", notebook)
    env = installer.isolated_environment(tmp_path / "runtime")
    installer.run(
        [
            sys.executable,
            "-c",
            "import os; assert os.environ['MPLBACKEND']=='Agg'; print('worker-ready')",
        ],
        env,
        tmp_path / "installation.log",
    )
    assert "worker-ready" in (tmp_path / "installation.log").read_text()
    assert os.environ["MPLBACKEND"] == notebook


def test_tigu_module_sets_native_backend_and_preserves_other_modules(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "worker_module", ROOT / "scripts/deploy-tigu-modules.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    text = module.module_text("banduppy", tmp_path / "runtime", tmp_path)
    assert "setenv MPLBACKEND Agg" in text
    assert "setenv MPLBACKEND" not in module.module_text(
        "qe", tmp_path / "qe", tmp_path
    )
