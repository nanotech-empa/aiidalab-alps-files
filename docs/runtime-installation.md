# Runtime installation and selected deployments

This catalog uses configuration **schema5** and the matching [nanotech-empa/aiidalab-empa-setup#14](https://github.com/nanotech-empa/aiidalab-empa-setup/pull/14).
Use both merged `main` branches and record the complete selected commits. Older
setup consumers refuse this protocol. Fresh-instance installation, registration
and scientific qualification remain separate from source integration.

The app first inspects a selection. Apply runs only its selected tasks, verifies
programs/dependencies, then registers Codes. It preserves unselected/custom
resources and scientific data. Existing computer replacement is opt-in.

## Personal Docker: Linux ARM64

`mac-localhost` registers AiiDA `localhost` with core.local/core.direct; it is
Linux inside Docker, not macOS. No CSCS certificate or SSH is needed. Set local
MPI tasks/machine and memory to the actual container allocation.

Install the corresponding applications/plugins with AiiDAlab's normal app manager
first. The setup app diagnoses missing plugins rather than creating fake Codes.
PythTB models, orbitals and Wannier use the same native `empa_tb.calculate`
route on Localhost and Tigu; see the [deployment matrix](deployment-matrix.md).
The local installer builds the worker from merged app source
`902d3b00023f6d21a09c261cccc65bd72aaaff39`, reuses the locked ARM64 dependency
artifacts and checks the full manifest before Code registration. Planning alone
never fetches source, builds or installs the worker.

Installed apps determine required Codes and runtimes automatically. Matching
existing programs are verified and reused; the normal UI has no Code/path selector. Opening the app
and changing a configuration branch do not fetch. **Inspect updates** synchronizes
and records the chosen revision. Changed choices/revision require inspection again.

| Family | Selected maintained recipe / installation |
| --- | --- |
| CP2K/SPM | cp2k-2026.2-linux-aarch64: complete official conda-forge closure, Python/MPI, basis/potential/D3 data, exact selected SPM source. |
| QE7.5 | Supplied and registered by the official QE app. EMPA setup preserves/reuses those Codes and does not run a second QE installer. |
| QE-PP Python | Dedicated hashed Python3.12 wheel closure with cloudpickle, NumPy/SciPy, pymatgen and scikit-image; required PythonJob Code. |
| BandUPpy | banduppy-1.0.0-cp312-aarch64: isolated venv and full hashed official wheel closure, separate from AiiDA. |
| PythTB | pythtb-2.0.2-cp312-aarch64: source-matching native worker, locked official dependencies, model/postprocessing hashes and solve/orbital/wannier capability checks. |
| Block2 | block2-0.5.4-cp312-aarch64: standard pip prefix, official native wheel and numerical dependencies, native import checks and nested Code metadata. |
| Rendering | cube-render-linux-aarch64: official current PyVista/VTK/Mesa and selected CubeHandler source. CPU EGL/llvmpipe, one thread; no X server or copied old OSMesa path. |
| Julia/Model | Official Julia1.12.6 artifact, then exact backend4f7f2f963bacb5e870fc118842004e31609c7c55 source and committed Project/Manifest in a private depot. |
| ORCA | Your licensed ARM64 archive; source-built matching OpenMPI4.1.8 with native C/C++/Fortran and numeric-type probe. |
| Support | Official Bader1.0.5, Wannier904.0.3, SKEAF1.3.0; official Critic2 tag1.6 and PPAFM0.4.1 source builds with native compilers. |
| Quantum energy | Source-locked modern quantum-energy/v1 SDK worker, native numerical/SDK imports and manifest identity. No hardware-provider calls or credentials. |
| wan2skeaf | Official aiidaplugins/aiida-skeaf v0.2.1 converter source and licence with NumPy/SciPy; reuse the app-provided console command when already available. |

### Local QE codes provided by another app

**Inspect updates** recognizes existing local QE registrations by their Computer
transport and calculation plugin, including custom Code labels. They are kept
unchanged and are not offered for deactivation as unlisted resources. The 15 QE
roles come from the official QE app, including the `xspec.xspectra` entry point.
If any are missing, the setup points to the QE app: install that app and complete
its localhost code setup if you want to run QE locally. This is optional guidance,
not a blocker for other selected EMPA runtimes. No duplicate QE installer or Code
registration is scheduled.

Existing local `python3`/PythonJob and `critic2` registrations are also recognized
as QE postprocessing helpers. EMPA's explicitly selected versioned helper recipes
keep their own runtime checks. Hidden Codes or Codes on disabled Computers are
preserved but not counted as available. Inspect reports registration presence;
it does not claim to have executed or verified these external programs.

Versioned JSON recipes under `runtime-recipes/` contain complete artifact URLs,
versions/builds and SHA-256. `scripts/install-local-runtime.py` prints a plan by
default; `--execute` claims a new prefix, checks every downloaded/cached artifact,
installs the complete isolated runtime and records source/data/library fingerprints.
The same CLI is used by the GUI tasks and can be invoked during Docker preparation.
It imports no AiiDA and does not change the active app environment or services.

Native worker children explicitly use `MPLBACKEND=Agg`. This includes installation
checks and the BandUPpy Code prepend/module environment: the Jupyter inline
backend belongs to the notebook, not the separate worker. The notebook's plotting
backend is unchanged. BandUPpy still uses `nanotech_empa.qe_banduppy`, not PythonJob.

The official Critic2 source **tag1.6** resolves to
`c478bcb530aaf783788c21c85ddedc719b3d16a2`, whose `VERSION` file is **1.4.339**.
Consequently its native banner is `critic2 (development), version 1.4.339`.
The localhost Code checks that banner together with the completed selected support
recipe and executable hash. A source tag and a program's internal banner are
separate identities; this is not a downgrade or permission to accept another build.

Example plan (no installation):

```console
python scripts/install-local-runtime.py \
  --recipe runtime-recipes/python-worker-cp312-aarch64.json \
  --prefix /home/jovyan/opt/native-runtimes/qe-pp-python-cp312-aarch64
```

Use an architecture-native Python3.12 for cp312 wheel recipes. Other architectures
need separately qualified recipes; do not copy ARM64 binaries or emulate them
silently. Each family has its own prefix and MPI/BLAS/graphics dependencies.
Support tasks do not upgrade the main AiiDA interpreter. Source builds use the
selected native compiler and retain logs; they do not start scientific jobs.

## Installation identity and retry

New prefixes get a completed receipt only after checks pass. A reused matching
prefix is fingerprinted and checked; an unknown/modified/incomplete prefix is
refused. Output streams to the app, with logs/receipts retained next to the prefix.
A failure can leave owned installation files: review them and choose a new prefix
when needed. No rollback/deletion of someone else's files is claimed.

For an earlier failed BandUPpy import, retain its prefix/log and select a fresh
absent worker prefix in the GUI before Inspect/Apply. The parent artifact cache
is reused. A failed prefix is not silently relabelled as a completed installation.

The Block2 receipt supplies the exact nested `block2` version, official artifact
hash and owned-launcher hash consumed by the ORCA app. Setup verifies the receipt
and launcher before creating the Code; no later manual extras patch is needed.

Julia preparation uses the backend's committed environment, verifies its files
before/after instantiation, exports the app-owned local model runtime and binds
the supported fallback depot/config for fresh GUI kernels. It never updates an
existing project, overwrites another depot binding or registers fictional model
workers. Both local wrappers point at the same committed engine/depot as the GUI.

Model and local/remote PythTB preparation also support ordinary non-editable pip installs.
When no tracked source checkout backs the installed module, setup fetches the
exact selected canonical commit into a temporary checkout, verifies it, and
uses the same capsule/wheel maker. It never treats an unrelated ancestor Git
repository as the package checkout or transfers GitHub credentials to compute
nodes. The selected Model source is public; the PythTB source still requires
authorized repository access. Existing real checkouts retain their clean-source
and engine-content guards. No `pip install -e` workaround is required.

## Licensed ORCA and MPI

Supply the licensed ORCA6.1.1 Linux ARM64 archive yourself. The catalog records
SHA-256927c9f165ac6ec7547d543215a5d02c662c691c1659ba5bcd3d687817e8a6757
for that exact distribution. Other releases/archives need an explicit catalog
selection and validation, not relabelling as6.1.1. No licensed archive or secret
is in this repository.

The selected task validates the archive before installing MPI. OpenMPI4.1.8 is
built from its official hashed release source with native C/C++/Fortran, including
`--enable-mpi-fortran`. Do not substitute another MPI or disable Fortran: ORCA
uses numeric-type matching even when called from C/C++. The maintained probe is
retained from the ORCA app and checks integer4/8, real4/8 and complex8/16.

The ORCA driver is launched once (`with_mpi=False`); `%pal` launches workers.
Code prepend selects its matching MPI and one BLAS/OpenMP thread. The local
shared-window backing directory is the actual job workdir, not network scratch.
A native numeric probe does not replace serial/parallel RIJCOSX and CASCI tests.

## Source selections and releases

Fresh CP2K2026.2, graphics libraries and newer support programs need their own
installation/native/parser/GUI qualification. Existing execution on older
program versions is not automatically transferred to these recipes.

Selected SPM sourcea0e486a12ad0102c6af5f9a9572c2449ec26e81e and
CubeHandlersource245db38e6a01279c3d911b4217fdf3757033ae14 retain changes absent
from their currently published wheels. Those owned source selections are explicit
qualification candidates; replace them with official releases containing the
same functionality before final app publication. Keep other missing external
releases in the deployment handoff. Review-held widgets-base patches are not
installed, and the official QE app is not patched by this setup.

## Hosted and remote resources

The hosted Kubernetes profile keeps scientific execution remote. Existing Daint/
Eiger/Tigu runtime, uenv, account and proxy definitions remain separate from the
new localhost recipes. This localhost acceptance does not qualify a remote job.

For Tigu, the target provider policy is a compatible shared module first and a
complete per-user installation otherwise. Keep installation/test evidence for
the [administrator module handoff](tigu-modules-for-administrator.md). Module
names and paths must come from the verified site deployment; do not guess them
or assume permission to write system module directories.

Remote supporting tasks remain scoped to selected codes, including the existing
BandUPpy worker route and Eiger CP2K data. Setup does not replace remote .bashrc.
Inspect existing uenvs by actual mount/view checks; a listed but unmountable image
is not ready. On Ritom, report repository/quota/group/path failures using the
[CSCS guidance](https://docs.cscs.ch/software/uenv/management/#migration-to-ritom);
do not broaden scratch permissions or move old scientific data automatically.

`connection-help.yml` retains ALPS MFA certificate renewal and Tigu's established
Docker→ELA→jump host route. Existing Empa private keys may remain on ELA. New-key
preparation is an explicit action showing only the public-key request; the app
sends no email and cannot grant first access. Preserve unrelated SSH entries,
trusted host keys and existing registrations. Do not copy agent sockets or keys
between instances as an installation shortcut.

The selected modern quantum worker and modern DMRG/model capabilities remain
included. Older experimental/research-worker changes remain deferred; their
records are not a restore list.
Runtime checks, Code registration and actual tiny application execution are
separate verdicts; use the setup app's clean-instance acceptance checklist.

For the complete machine-by-machine ownership and actual remaining coverage, see [the deployment matrix](deployment-matrix.md).
