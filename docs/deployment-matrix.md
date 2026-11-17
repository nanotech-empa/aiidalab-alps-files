# Complete EMPA deployment matrix

This is the selected setup/catalog scope, not an installation or scientific
qualification receipt. Localhost is **Linux aarch64 inside Docker on Apple
Silicon**, Tigu is Linux x86_64, and Daint is Linux aarch64/GH200. Use native
artifacts and machine-matched MPI. Never infer exclusion from a missing recipe.

| Runtime | Mac Docker localhost | Tigu | Daint |
| --- | --- | --- | --- |
| QE 7.5 and QE postprocessing executables | Installed/registered by the official QE app; preserve and reuse | Shared module first, personal recipe otherwise | Existing `quantumespresso/v7.5:v3` uenv |
| CP2K and its data | Native selected recipe | CP2K2026.2 **CPU-only psmp**, five same-version libraries rebuilt with native GCC9/glibc2.31 | Existing `cp2k/2026.2:v1` uenv |
| SPM: STM/STS, overlap, sparse overlap, CP2K unfolding | Exact selected modern SPM source | Shared module with matching MPI | Shared uenv from the maintained modern SPM recipe |
| QE-PP Python worker | Separate Python3.12 worker and `python@localhost` Code | Separate worker/module and Python Code on selected Tigu Computer | Shared Python worker uenv and Python Code |
| BandUPpy/irrep | Dedicated worker; native `nanotech_empa.qe_banduppy` | Dedicated module/worker, same native plugin | Shared worker uenv, same native plugin |
| Bader, Critic2, Wannier90, SKEAF and conversions | Install missing support programs; reuse verified existing ones | Support module | Existing suitable uenv or maintained shared support image |
| Phonopy, PPAFM | Native selected runtime | Support module | Suitable existing/shared uenv |
| CubeHandler/rendering | Native full graphics closure | Dedicated module | Modern shared headless rendering uenv |
| ORCA, plot, 2json | User-supplied licensed archive and exact matching MPI | Existing licensed site distribution exposed through module | **Excluded** |
| ORCA tools/Dyson | Selected modern helpers | Dedicated module | No ORCA runtime provisioned |
| Block2/modern DMRG | Standard prefix and required metadata | Native module | Shared standard prefix/native runtime; application qualification pending |
| Julia/ITensor/Model | Exact engine/Project/Manifest/depot and supported GUI bindings | Same frozen engine and native modules | Shared libraries/runtime; private engine remains access-controlled |
| Modern quantum-energy/simulator worker | Explicit source-locked native task and manifest check | Matching native module/task | Public native uenv build and manifest check |
| PythTB | Application's local solver | Native Python environment **and app-to-Slurm execution integration** | **Excluded** |
| Gaussian | **Excluded** | Existing licensed site distribution | **Excluded** |

PythTB being a Python library does not limit execution to the notebook host.
Installing its package on Tigu alone does not implement submission, result
retrieval or reopening in the app. Keep that connected app change explicit.
The connected candidate is
[nanotech-empa/aiidalab-tb#8](https://github.com/nanotech-empa/aiidalab-tb/pull/8).
Its numerical and builder tests pass; actual Tigu GUI/HPC qualification remains
pending. Wannier and interactive orbital operations remain on the notebook host.

The native quantum task selects the current public `quantum-energy/v1` source,
not the retained older research worker. It installs the SDK without credentials
or hardware-provider calls. Installation/Code-manifest verification and actual
simulator/application qualification must be recorded separately.

## PythonJob is a real consumer requirement

Do not globally remove `aiida-pythonjob` or its Codes. The official
`aiidalab/aiidalab-qe-pp` property plugin imports/submits PythonJob to reduce cube
files; its current builder also requires the Python Code. The remote interpreter
must provide compatible cloudpickle, NumPy/SciPy, `pymatgen.io.common.VolumetricData`
and `skimage.transform`/`skimage.metrics`, not only exist on PATH. Validate them
before registration. `aiida-phonopy` also declares PythonJob as a package
dependency; its ASE workflow uses it, while the normal QE Raman path uses native
QE/Phonopy calculations. Do not confuse those two requirements.

The native EMPA BandUPpy CalcJob does not use PythonJob. Its Code registration is
separate even when both workers use Python. Reuse an existing matching Code
(including an existing `python3@localhost`) rather than silently duplicating or
repointing it. Preserve all historical Codes and provenance.

## Daint shared uenv policy

Reuse an existing compatible uenv first. Build missing images with the CSCS
`uenv build` service using `uenv-recipes/daint/` and
`scripts/build-daint-uenv.py`. The service namespace is accessible to all CSCS
users; a group-only filesystem repository is a different supported distribution
route. Never include private repositories, licensed binaries, credentials or
research data in a public service build. In particular the Model engine's
private source is not a public uenv payload.

Record exact source hash, returned service URL/tag, image identity, view,
executable/data paths, import/MPI tests and the real qualification outcome. A
submitted build is not a completed image. Keep old images and historical
scientific fingerprints; do not overwrite their tags or repoint old Codes.

Installation, registration, a real tiny application calculation, and GUI
results/export/reopening are separate checks for every supported route.

## Built Daint images

The following immutable service builds completed on November17,2026. Image
builds execute the maintained recipe's native import/version checks; this does
not claim Slurm scientific or app GUI acceptance.

| Contents | Runtime label | Selected view |
| --- | --- | --- |
| QE7.5 and bundled Wannier90 3.1.0 | `quantumespresso/v7.5:v3` (existing official image) | `default` |
| CP2K2026.2 | `cp2k/2026.2:v1` (existing official image) | `cp2k` |
| SPM1.6.0/a0e486a, Python3.12, native Cray MPI | `empa-spm-native/1.6.0-a0e486a:3077571942` | `default` |
| PythonJob worker and BandUPpy1.0 | `empa-postprocess/2026.11:3075642218` | `default` |
| CubeHandler0.2.1/245db38 and headless EGL | `empa-render/0.2.1-245db38:3075642343` | `default` |
| Block2 0.5.4 and Julia1.12.6 | `empa-model-native/2026.11:3075642581` | `default` |
| Modern quantum SDK/4d92f718 | `empa-quantum/4d92f718:3075816173` | `default` |
| Bader, SKEAF, Critic2, PPAFM | `empa-support/2026.11-native:3077565151` | `default` |
| Official wan2skeaf0.2.1 converter | `empa-conversion/0.2.1:3077666140` | `default` |

Use `service::` only for registry download/lookup, for example
`uenv image pull service::empa-model-native/2026.11:3075642581`.
Run/inspect/Slurm labels omit that registry prefix, as in the table. The setup
app makes this distinction and verifies the selected view and programs.
Keep Daint Wannier90 bound to the QE image's matching vendor MPI, rather than
the separate support image's Conda OpenMPI build. Phonopy continues to reuse
the suitable existing `critic2/1.2:1952527021` image.

The Model native image contains only public Julia/Block2. Its selected private
engine, unchanged Project/Manifest and private depot are prepared by the scoped
Model task in an account-owned prefix, never embedded in the public image.
That per-user Daint preparation and actual Model GUI/Slurm jobs remain separate
acceptance items. ORCA, Gaussian and PythTB are not installed on Daint.
