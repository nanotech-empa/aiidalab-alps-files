"""The normal setup has a complete, explicit app-to-Code contract."""

from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def catalog():
    data = yaml.safe_load((ROOT / "config.yml").read_text())
    for name in data.pop("includes"):
        for section, values in yaml.safe_load((ROOT / name).read_text()).items():
            data.setdefault(section, {}).update(values)
    return data


def test_visible_targets_have_only_one_tigu():
    data = catalog()
    visible = {
        key: value
        for key, value in data["computers"].items()
        if value.get("user_visible", True)
    }
    assert set(visible) == {"mac-localhost", "tigu-modules", "daint.alps"}
    assert visible["tigu-modules"]["display_name"] == "Tigu"
    assert (
        visible["tigu-modules"]["setup"]["mpirun_command"]
        == "mpirun -np {tot_num_mpiprocs}"
    )
    assert data["computers"]["tigu"]["setup"]["mpirun_command"] == "srun"


def test_all_current_native_codes_have_an_app_owner():
    data = catalog()
    used = {key for spec in data["applications"].values() for key in spec["codes"]}
    assert used <= data["codes"].keys()
    legacy = {"stm", "overlap", "cp2kunfolding"}
    current = {
        key
        for key, value in data["codes"].items()
        if data["computers"][value["computer"]].get("user_visible", True)
        and key not in legacy
    }
    assert current <= used
    assert not any(data["codes"][key]["computer"] == "tigu" for key in used)


def test_machine_exclusions_and_official_qe_ownership_are_explicit():
    data = catalog()
    for spec in data["applications"].values():
        for key in spec["codes"]:
            code = data["codes"][key]
            if code["computer"] == "daint.alps":
                assert code["default_calc_job_plugin"] not in {
                    "orca.orca",
                    "gaussian",
                    "empa_tb.calculate",
                }
            if code["computer"] == "mac-localhost":
                assert not code["default_calc_job_plugin"].startswith(
                    "quantumespresso."
                )
    assert "tigu_module_pythtb" in data["applications"]["pythtb"]["codes"]
    assert data["applications"]["gaussian"]["codes"] == ["tigu_module_gaussian"]


def test_qe_properties_keep_pythonjob_and_require_the_host():
    data = catalog()
    for key in ["qe_pp", "qe_vibroscopy"]:
        app = data["applications"][key]
        assert app["requires_applications"] == ["qe"] and app["kind"] == "plugin"
        for computer in ["mac-localhost", "tigu-modules", "daint.alps"]:
            assert any(
                data["codes"][code]["computer"] == computer
                and data["codes"][code]["default_calc_job_plugin"]
                == "pythonjob.pythonjob"
                for code in app["codes"]
            )


def test_user_settings_do_not_expose_runtime_paths():
    data = catalog()
    visible = {
        key for key, spec in data["runtime_settings"].items() if spec.get("user_input")
    }
    assert visible == {"tigu_empa_username", "local_default_mpi", "local_memory_kib"}
    assert "tigu-modules" in data["runtime_settings"]["tigu_empa_username"]["computers"]
    assert "tigu-modules" in data["runtime_settings"]["tigu_ela_key"]["computers"]


def test_new_contract_requires_a_consumer_that_understands_apps():
    assert catalog()["schema_version"] == 5


def test_visible_native_installers_always_require_explicit_app_code_keys():
    data = catalog()
    for task in data["setup_tasks"].values():
        if data["computers"][task["computer"]].get("user_visible", True):
            assert (
                task.get("codes")
                or task.get("computer_preparation")
                or task.get("legacy_only")
            ), "A selected computer without apps must not install arbitrary runtimes"
