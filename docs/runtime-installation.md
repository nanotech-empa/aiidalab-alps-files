# Runtime installation and deployment profiles

This configuration is schema 2 and requires the companion setup-app changes on
`feature/selective-safe-setup`. Keep both changes unmerged during review.
`config.yml` includes `runtime-catalog.yml`; the app reads both and displays the
full Git revision. `runtime_settings` supplies editable paths without rewriting
the shared catalog. Account selection is per computer, so Tigu/free and
Daint/project-account can be configured in one plan.

## Deployment matrix

| Family | Daint | Tigu | Personal Docker / ARM64 | CSCS pod |
| --- | --- | --- | --- | --- |
| CP2K, QE and their existing post-processing codes | Existing uenv definitions | Configure only actual available runtimes | Optional native code definitions | Remote execution |
| New SPM, sparse overlap, CP2K unfolding | Source-pinned `a0e486a...` wrappers | Qualify a separate native runtime before adding definitions | Optional same pinned SPM source + native MPI | Remote execution |
| ORCA SCF/CASCI, `orca_plot`, `orca_2json` | Excluded | Shared licensed ORCA 6.1.1/MPI paths, editable | Licensed Linux ARM64 ORCA 6.1.1 + Open MPI 4.1.8 | Remote Tigu execution |
| BandUPpy 1.0 | Separate Python worker inside SPM uenv | Separate native Python worker | Separate native Python worker | Remote worker |
| PythTB | No executable Code required | No executable Code required | App Python dependency | App Python dependency |
| ITensor/Julia | Preserve qualified chain/BLAS deployment | Requires qualification | App-owned model-runtime snapshot | Remote chain runtime; local preview is a separate decision |
| Quantum workers | Excluded | Preserve existing immutable deployments | Preserve existing immutable deployments | Remote Tigu execution |

Quantum-worker updates/new deployment are deferred by the user. This series has
no quantum installer and does not retarget worker Codes or source prefixes.
ITensor's general-graph/Hubbard production adapters and modern-stack qualification
are also still open; a successful local preview is not a generic production Code.
Unlisted historical/research registrations are retained by default.

## Before installing

Choose the deployment profile in the app. Hosted Kubernetes does not offer
`mac-localhost`; Personal Docker exposes it with AiiDA label `localhost`,
`core.local` transport and `core.direct` scheduler. It is Linux inside Docker,
not the Mac's host terminal. Local selection needs no CSCS certificate.

Resolve executables, architecture and linked libraries in the target environment.
Set each runtime path to that actual installation. Existing computer definitions
are kept unless the user explicitly enables their replacement. Local default
resources are conservative: adjust processes/memory to the container allocation
after testing. A registered path is insufficient when its shared libraries,
Python dependencies, MPI runtime or data files are missing.

The setup app installs selected supporting files and BandUPpy workers. Licensed
ORCA, the app Python stack and the other native runtime prefixes are prerequisites
prepared by the instance agent with the recipes below. Failed checks explain the
missing runtime and stop before changing AiiDA registrations. Do not interpret
the presence of a catalog definition as a claim of a tested deployment.

## BandUPpy workers

The backend's BandUPpy workflow uses a PythonJob interpreter with `banduppy`, ASE,
NumPy, SciPy and cloudpickle; BandUPpy is not a standalone native executable.
`install-banduppy-runtime.py` creates a new prefix using the selected native Python,
installs the tested BandUPpy 1.0.0 line, checks imports/version and records the full
installed package list. It never installs or loads AiiDA. Existing completed
prefixes are checked; an unknown or incomplete prefix is refused. Choose a new
prefix after reviewing a failed install rather than deleting someone else's files.

The app runs only the corresponding selected installation task:

- Daint: install inside the selected SPM uenv; keep that same uenv in the Code
  prepend text for future jobs.
- Tigu: use `tigu_python`, which must be native Python >=3.11. The dated verified
  Python 3.12.15 path is a default to inspect, not a download guarantee for every
  user. Provision that interpreter first if absent.
- Personal: use the selected `local_python` to create the separate worker prefix.

Remote worker Python versions are distinct from the app's Python >=3.12 policy.
The app/backend Python environment must also supply the matching PythonJob plugin.
Validate a small complete QE/BandUPpy app workflow after registration.

## ORCA on personal ARM64 Docker

The licensed ARM64 ORCA 6.1.1 package tested in the source instance requires Open
MPI 4.1.8. Obtain the licensed Linux archive for the actual architecture, verify
its vendor checksum and retain it privately. The source instance's archive had
SHA-256 `927c9f165ac6ec7547d543215a5d02c662c691c1659ba5bcd3d687817e8a6757`;
that value applies only to that exact ARM64 archive.

Follow the app-owned
[ORCA/MPI build and validation guide](https://github.com/nanotech-empa/aiidalab-orca/blob/main/docs/local-orca-mpi.md).
Build matching Open MPI with native C/C++/**Fortran** compilers and
`--enable-mpi-fortran`. Do not use `--disable-mpi-fortran`: it previously passed
a tiny HF test but failed numeric-type lookup during parallel RIJCOSX startup.
Keep Conda cross-compiler variables out of a native system-toolchain build.

For an unpacked Open MPI 4.1.8 source tree, a native build uses:

```bash
env -u CC -u CXX -u FC -u F77 -u CFLAGS -u CXXFLAGS -u FCFLAGS -u CPPFLAGS \
  -u LDFLAGS -u AR -u AS -u LD -u HOST -u BUILD \
  CC=/usr/bin/gcc CXX=/usr/bin/g++ FC=/usr/bin/gfortran F77=/usr/bin/gfortran \
  ./configure --prefix=/home/jovyan/opt/openmpi-4.1.8-orca-fortran --enable-mpi-fortran
make -j2
make install
```

Verify compiler targets before this build. Set `local_orca_root` and
`local_orca_mpi` to the actual resulting prefixes. The Code launches the ORCA
driver once (`with_mpi=False`); ORCA's `%pal` starts MPI workers. Do not launch
the driver itself through `mpirun`. The local prepend limits BLAS/OpenMP threads
and places Open MPI's shared CI window backing files in the local job directory.
Docker must also have adequate RAM/disk/shared memory. This local shared-memory
choice is not an instruction to use network-mounted HPC scratch for MPI windows.

Check `ldd` on `orca_startup_mpi` and `mpirun`, run the app's
`scripts/check_orca_mpi.c` numeric-type probe, and use
`scripts/validate_orca_installation.py` for serial/parallel PBE0/RIJCOSX checks
through the app/daemon. Require normal termination, correct process counts,
raw/parsed energies within `1e-7` Hartree, and retrieved wavefunctions. Include a
parallel CASCI check before multireference use. These are runtime acceptance
checks, not validation of a scientific active space or protocol.

For Tigu, the dated shared path is `/store/amsp/ORCA_6_1_1` with the existing
`/opt/openmpi-4.1.1` runtime. Verify the real shared installation and its library
requirements; do not replace another user's installation. Configure the normal
Tigu SSH agent/proxy route and its actual Slurm partition/resources. Do not copy
Daint account/QoS/GPU assumptions to Tigu. The configuration installs no ORCA on
Daint and contains no licensed binaries.

## SPM and local support tools

The source-pinned SPM commit is
`a0e486a12ad0102c6af5f9a9572c2449ec26e81e`. It contains multi-file basis support
required by the modern Surfaces/backend combination. On Daint, the selected
setup tasks deploy its clean immutable source and four separate wrappers inside
the existing SPM uenv. Older production definitions remain available. Sparse
overlap conversion stays serial; STM/overlap/unfolding retain their reviewed MPI
and threading behavior.

On personal ARM64, install this exact source into the chosen real app/runtime
environment with native MPI available. The existing validated CP2K prefix is the
documented Ubuntu/Debian ARM64 fallback, not a universal path to copy blindly:

```bash
python -m pip install 'cp2k-spm-tools@git+https://github.com/nanotech-empa/cp2k-spm-tools.git@a0e486a12ad0102c6af5f9a9572c2449ec26e81e'
python -m pip check
```

Preview dependency resolution first. If this instance's tested stack uses a
newer immutable source, choose a new matching definition rather than relabelling
it as `a0e486a`. The setup checks the installed source identity, imports and
executable paths. Smoke-test all selected CLI wrappers and a small sparse-overlap
plus unfolding workflow.

The detailed, architecture-specific native recipes are maintained in
[local-development-codes.md](https://github.com/nanotech-empa/aiida-aiidalab-dev/blob/main/references/local-development-codes.md):

- **CP2K:** discover an existing executable first. The tested empty Ubuntu
  Noble ARM64 fallback extracts signed Debian Bookworm `cp2k=2023.1-2` and data
  plus dependencies into a private prefix, without compiling CP2K. Verify ELF
  architecture, MPI links, the prefix-local `mpirun` alternative and
  `CP2K_DATA_DIR`. Do not expose the extracted glibc directory globally.
- **QE:** use a native QE environment, with matching `pw.x`, `pp.x`, `projwfc.x`,
  `dos.x` and `pw2wannier90.x`. Match their MPI libraries to the Code environment.
- **Wannier90/Critic2:** the tested native support prefix includes Wannier90,
  SKEAF and a properly installed Critic2 1.2.2 with its atomic data directory.
  Critic2 is OpenMP, not MPI; Wannier90 needs its matching MPI prefix. SKEAF/
  `wan2skeaf` can be added after the chosen QE workflow requires them.
- **Bader/CubeHandler/Phonopy/PythonJob:** supply each executable and its matching
  AiiDA plugin. CubeHandler's modern plugin is `nanotech_empa.cubehandler`.

Never copy ARM64 native prefixes into an x86-64 container or Tigu. The catalog
only offers the architecture-specific CP2K/SPM/ORCA ARM64 recipes on ARM64.
Other personal architectures need their own qualified native definitions.

## SSH and scratch/uenv failures

`connection-help.yml` supplies a guide for every foreseen remote computer:
Daint/Eiger use the ALPS guide and Tigu has its own guide. The setup form shows
an expandable section for each selected remote computer, and a failed SSH
attempt prints that computer's instructions in the log.

For ALPS, install MFA CSCS if it is absent, open it and refresh/renew a valid
CSCS SSH key/certificate before retrying. Tigu also needs an Empa jump-host
identity distinct from those CSCS credentials. With the existing ELA-based route,
Docker connects through ELA and `jump1.empa.ch` to Tigu. The proxy forwards the
Docker agent to ELA and runs `ssh-add -t 5` there, temporarily adding ELA's key
to that forwarded agent. The Empa private-key file can remain on ELA.

A new container can reuse that route with fresh CSCS credentials, the same proxy
configuration and a working SSH agent. Its own `~/.ssh/id_rsa` may be a different
identity; copying that file is not equivalent to reusing the ELA key. Keep the
existing SCI-IT registration when reusing the same registered key/account.

For new access, check **Empa/Tigu username** (defaults to the CSCS username) and
click **Prepare new Tigu key on ELA**. This opt-in action creates/reuses a dedicated
unencrypted Ed25519 key at `~/.ssh/aiidalab-tigu/id_ed25519` on ELA, preserves default
keys, and selects that ELA path in the form. The private key stays on ELA, mode 600.
The form displays a copyable public-key request to `aliaksandr.yakutovich@empa.ch`
asking for jump-host activation and confirmation of authorization on Tigu. The
app sends no email. Both servers need authorization; registration on the jump
host alone is insufficient evidence of Tigu access. Adding the public key on Tigu
requires an existing working login or its administrator. Wait for confirmation,
then inspect/apply and test the route. Never send the private key.

The ELA key setting is blank by default, retaining the existing default-key route.
When explicitly selected, the dedicated path is inserted into both the OpenSSH and
AiiDA proxy commands. Both use the editable Empa username for the jump host and
Tigu; the ELA login still uses the CSCS username. Account/key values are validated
before entering proxy shell commands. The normal proxy temporarily loads the key
into the forwarded agent; preparation itself disables forwarding.
An existing AiiDA Computer keeps its saved definition unless the user explicitly
enables computer updates and reviews the replacement plan.

Configuration and help edits reach the form when the user clicks **Inspect
updates**, which synchronizes the selected branch before inspecting. Startup
reads the cached catalog; there is no background configuration-update polling.
Apply uses the inspected revision and performs no additional configuration fetch.

The app writes selected app-managed SSH blocks while retaining other entries and
making a backup. It bootstraps Daint's proxy and target host keys before checking
the connection, uses batch mode/connection timeouts, and refuses a changed trusted
key. It does not send empty passwords. Renew CSCS MFA certificates normally;
unlock passphrase-protected keys through the user's normal agent. Tigu's custom
multi-hop proxy requires trusted host-key entries for the jump host and Tigu on
first use. Obtain them from SCI-IT and install them according to its instructions;
strict batch SSH fails on missing or changed trusted keys.

Daint/Eiger's new workdir is Ritom. Changing it does not migrate historical
RemoteData, checkpoints or the uenv repository. The app prints the actual uenv
repository status, pulls only missing selected images, then **mounts** each image
and checks its view. This happens for already listed images and after a pull.
Registry availability is not required for an already installed image.

A `Permission denied` SquashFS failure on Ritom produces version/group/path
diagnostics and links to the
[current CSCS migration guidance](https://docs.cscs.ch/software/uenv/management/#migration-to-ritom).
CSCS documents correcting obsolete ownership to the user's current primary
group, and reports the fix in uenv 10.2.0. The app does not force repositories back
onto Capstor, recursively change ownership or make scratch directories
world-traversable. Those actions require reviewing the actual user's paths and
CSCS policy. Incomplete migrations, missing images and quota/space errors receive
separate guidance. After remediation, inspect again to resume configuration.

Login-host checks cannot certify compute-node mounts or Slurm launch. Before
production, run `verdi computer test`, `verdi code test` and an approved small
scheduler job on each chosen computer. Keep live deployment/compute acceptance
distinct from mocked tests and configuration review.
