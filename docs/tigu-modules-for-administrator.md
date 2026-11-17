# Tigu shared modules and per-user installation

The deployment target is a set of versioned shared modules for the scientific
programs used by the Empa apps. Per-user installations are the initial test path
and the fallback when a suitable shared module is absent. An administrator must
choose the site package/module directories and access groups; user setup does
not require permission to write there.

Use the same source, dependency, data and validation records for the per-user
installation and the later shared module. Do not copy Linux ARM64 Docker
prefixes onto Tigu: record Tigu's actual architecture, compilers, scheduler/MPI
integration and compute-node library environment first.

## Same executable installer for private and shared deployment

This deployment reuses `scripts/install-local-runtime.py` and the existing
per-family recipes. Block2 retains its standard prefix and owned launcher;
Julia/ITensor retains the selected backend's exact committed Project/Manifest
and preparation script. BandUPpy and the standalone ORCA helpers retain their
separate Python workers. ORCA/Gaussian reuse the licensed site installations.
The Tigu-specific work selects native x86_64 artifacts and writes modulefiles;
it does not replace application workflows or reconstruct their scientific
environments from a new, unconstrained dependency selection.

Completed matching installations are reused. Architecture-specific wheel/MPI
dependencies and source-build requirements are recorded in
`runtime-recipes/tigu/`; an ARM64 installation result does not qualify those
x86_64 artifacts. Failed attempts remain available for diagnosis.

`scripts/install-tigu-modules.sh` is the common entry point. It bootstraps a
checksum-locked Python3.12/micromamba toolchain from Tigu's existing Python3,
then installs native x86_64 runtime closures and writes Tcl modulefiles accepted
by the actual site Lmod. It needs no sudo or changes to the system Python,
AiiDA, existing software, shell startup or default module paths.

The November16 inventory found Ubuntu20.04/x86_64, Lmod initialized by
`/etc/profile.d/lmod.sh`, Slurm `debug`, old CP2K8.1/QE6.7 modules, and accessible
licensed ORCA6.1.1/OpenMPI4.1.1 and Gaussian16 site installations. Those old
scientific modules are not substituted for the selected modern runtimes.
Site identity and permissions must still be checked by the receiving admin.

After checking out the reviewed catalog commit, preview without changes:

```console
./scripts/install-tigu-modules.sh --root /store/ACCOUNT/opt/empa-stack-20261116
```

Run installation on an allocated compute node, initially two CPUs/one process:

```console
srun --mpi=none --ntasks=1 --cpus-per-task=2 --mem=12G \
  --time=02:00:00 --cpu-bind=cores \
  ./scripts/install-tigu-modules.sh \
  --root /store/ACCOUNT/opt/empa-stack-20261116 --execute
```

Sasha uses the same command with an authorized shared `--root` and optional
`--module-root /SHARED/MODULEFILES`. No per-user prefix is moved or copied:
Conda, Python and Julia paths are built for their final destination. The script
keeps old modules/prefixes intact and refuses an unrelated or incomplete target.
Select one family with `--families banduppy`, or install the complete selection.
Model automatically includes its official native Julia and frozen engine/depot;
it never writes a GUI home binding on Tigu.

ORCA/Gaussian modulefiles expose the existing licensed site programs without
copying them. Alternate authorized site locations can be supplied with
`--orca-root`, `--orca-mpi`, and `--gaussian-root`. Licence/access limitations
remain real prerequisites; the installer cannot grant them. Native MPI/API and
scientific qualification remain separate from installation/module load.

Receipts and failed-attempt logs stay under the chosen root. Each successful
module has an exact recipe, executable and modulefile identity. Inspect a saved
provider without installation with `--root PREFIX --check-family banduppy`.
For a job use the recorded init file, `module use PREFIX/modulefiles`, and the
exact module name; no dependency installation runs inside scientific jobs.

## Inventory to deliver to Sasha

| Family | Required contents and checks |
| --- | --- |
| CP2K | Selected official binary/source release; matching MPI; BASIS/POTENTIAL and D3 data; exported CP2K_DATA_DIR; native Standard/Low app tests and parsed outputs. |
| QE | Matching pw, pp, projwfc, dos and pw2wannier90 executables; one MPI/toolchain; source/version records and a tiny bands/post-processing path. |
| SPM | Reviewed released source, or explicitly named qualification commit; mpi4py linked to the same MPI as its launcher; STM/overlap/sparse-overlap/unfolding CLIs and basis/WFN compatibility tests. |
| ORCA | Licensed site distribution and its exact vendor-required MPI, including Fortran numeric types; orca, orca_plot and orca_2json; serial/parallel RIJCOSX and CASCI checks. |
| Gaussian | Existing licensed Gaussian 16 site distribution, supported compute-node instruction set, access group, scratch/data settings and launcher environment. Preserve its licence restrictions; do not redistribute the binary or assume the Linux ARM64 localhost recipes apply. |
| ORCA helpers | Matching orca-tools/orca-dyson package sources, released Dyson library and numerical dependencies; actual stored-file export/map/figure checks. |
| Block2 | Adapter-supported official Block2 release, owned block2main launcher, numerical libraries and artifact identity; analytic and molecular DMRG/checkpoint tests. |
| Julia/ITensor | Official native Julia and the selected backend's complete committed engine, Project/Manifest and verified depot; ground-state/spectral and selected Model execution checks. |
| BandUPpy | Separate Python worker with BandUPpy/irrep/ASE/NumPy/SciPy/cloudpickle; meaningful unfolded bands versus a matching primitive reference. |
| Rendering | Selected CubeHandler source/release, compatible VTK/PyVista and a working headless CPU graphics backend; full-grid geometry/camera/slice/render comparison. |
| Other support | Bader, Wannier90, SKEAF, Critic2 with its installed data, PPAFM native libraries and wrappers, and Phonopy where used. Record the actual supplying package for every executable. |

PythTB's local solver uses the application dependency. Its source-matching
Tigu worker is paired with the maintained app CalcJob/parser in
[nanotech-empa/aiidalab-tb#8](https://github.com/nanotech-empa/aiidalab-tb/pull/8).
Install that client plugin in AiiDAlab separately from the native compute
program. GUI-local execution still needs its local runtime; a Tigu module alone
does not install that runtime inside an AiiDAlab container.

For each row provide repository/release/full source SHA, official artifact URLs
and checksums, compiler and Python versions, native architecture, dependency/MPI
versions, data paths/licences, the installation recipe, log and actual test
results. Include failed/incomplete tests honestly. Keep missing official releases
separate from qualification commits; a distribution version string alone is not
source-content proof. No licensed archive or credential belongs in this handoff.

## Shared installation contract

1. Use an immutable versioned prefix visible on compute nodes. Preserve earlier
   prefixes still referenced by existing Codes, checkpoints or research work.
2. Expose executables as actual paths, not only interactive aliases. The setup
   must be able to resolve an absolute executable inside the loaded module.
3. Provide exact versioned module names and dependencies. The module should set
   PATH, required libraries/data and its matching MPI/Python environment. Do not
   require rewriting users' .bashrc or installing packages during each job.
4. Validate on a compute node using the normal Tigu scheduler route. A login-node
   import/version check is insufficient. Keep ORCA's driver launch separate from
   its internal PAL/MPI workers; do not launch the driver repeatedly with MPI.
5. Keep module names/prefixes stable after qualification. A source/library change
   needs a new version/identity and affected validation, not a silent replacement.
6. Return module names, resolved program/data paths and the validation manifest
   to the configuration maintainer for the canonical catalog update.

The existing Tigu ORCA definition references its site's actual distribution/MPI.
The ARM64 Docker archive's MPI4.1.8 requirement is not automatically the MPI
requirement of a different Tigu vendor archive. Match the real distribution and
repeat numeric-type/library checks. Likewise, keep Slurm and local direct MPI
launch settings distinct.

## Setup provider selection

The selected Tigu AiiDA Computers use the supported `core.ssh_async` transport
with its **OpenSSH backend**, reusing the app-managed `Host tigu` proxy route.
That route enforces BatchMode and StrictHostKeyChecking; trusted host keys and
the user's normal CSCS certificate remain prerequisites. Both released AiiDA2.8
and2.9.4 provide this backend. The plain Paramiko3.5.1 transport can fail for
certificate-bearing agent keys ([upstream2462](https://github.com/paramiko/paramiko/issues/2462));
the fixed Paramiko5 line is outside AiiDA2.9.4's `paramiko~=3.0` requirement.
No private Paramiko wheel, forced dependency upgrade or relaxed host-key policy
is used by this selection. Existing Computers are preserved unless their
replacement is explicitly selected in Inspect/Apply; module registration alone
does not prove transport or scheduler submission.

The intended policy is **compatible shared module first; complete selected
per-user installation otherwise**. Resolve the provider during setup and retain
it in the Code/deployment receipt, rather than switching silently inside a job.

- Probe only exact catalog module names in the normal login environment. A
  successful module load must also pass version/API/data/MPI checks.
- When suitable, use its resolved executable and a matching `module load` in
  every Code job environment. Do not assume a module loaded in an earlier SSH
  session remains loaded for AiiDA jobs. Avoid an unconditional module purge
  that removes site scheduler/toolchain prerequisites.
- When unavailable or incompatible, show the per-user prefix and complete
  selected installation in the inspected plan. Do not use sudo or write into
  the shared module tree. An SSH/authentication failure is an access problem,
  not evidence that a module is absent.
- Register only after verification. Preserve old provenance-linked Codes and
  their executable prefixes; changes create a new reviewed identity.

The first localhost Docker test and the Tigu installation/module test are
separate evidence. Native x86_64 installation and module checks have now run on
Tigu for all15 selected families; actual app scientific jobs and GUI acceptance
are still distinct. An ARM64 installation result does not qualify Tigu.

## Complete private delivery

`make-tigu-handoff.py` takes both `--checkout` (the frozen private Model backend)
and `--pythtb-checkout` (the clean source-matching app). It includes the private
Model capsule and compute-only PythTB wheel, so the administrator does not need
GitHub credentials on compute nodes. Keep the archive private. Both workers are
detected automatically by the same module installer.

The selected family list now includes a separate QE-PP Python worker, native
PythTB and modern quantum energy worker. The Python Code is required by the
official QE-PP property plugin; native BandUPpy and PythTB do not use PythonJob.
The CP2K2026.2 prebuilt dependency closure initially exposed a Tigu ABI mismatch.
The maintained CPU recipe now rebuilds exactly the same TREXIO2.6.1, libxs1.0.0,
libxsmm2.0.0, SpFFT1.1.1 and SPLA1.6.1 with the native GCC9.4.0/glibc2.31.
Source archives, checksums, licences and build logs are retained. CP2K itself,
its data and scientific settings are unchanged; no GPU support, system glibc
upgrade or older CP2K is substituted. The repaired installation, native version,
SPM/MPI imports and module checks passed on an allocated Tigu compute node.

The complete selection is15 families: CP2K/SPM, QE, BandUPpy, Block2, rendering,
support tools, ORCA helpers, Julia, frozen Model, licensed ORCA, licensed
Gaussian, QE-PP Python, PythTB, quantum SDK and wan2skeaf conversion. Keep the
per-family installation/module receipts with this delivery. Previously failed
prefixes remain intact and are not selected by the new catalog.
