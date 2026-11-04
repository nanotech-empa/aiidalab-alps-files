# aiidalab-alps-files
Files needed to set up codes for AiiDAlab on ALPS

## Daint and Eiger scratch directories

Daint and Eiger computer definitions use
`/ritom/scratch/cscs/{username}/aiida/`. Computer and code labels are unchanged.
The production and development setup apps read these shared definitions; after
updating this repository, inspect and apply the computer updates in the setup app
when no affected workflows are active.

This configuration change does not move existing calculation folders, checkpoints
or uenv images, and does not rewrite existing AiiDA `RemoteData` paths. Relocated
calculations need a separately verified continuation from their new location.

## CP2K band unfolding on Daint

The `cp2kunfolding` code runs the `nanotech_empa.cp2k_unfolding` CalcJob with
the `cp2k-spm-tools` MPI unfolding CLI.

The current `cp2k-spm-tools/1.5.0` uenv provides the Python and MPI runtime but
does not contain that CLI. Until
[`cp2k-spm-tools#24`](https://github.com/nanotech-empa/cp2k-spm-tools/pull/24)
is merged and released, setup therefore checks out the exact tested #24 commit
under `/users/<cscsuser>/src/cp2k-spm-tools`, and the wrapper prepends that
source tree to `PYTHONPATH`. Replace this temporary source override with the
first released version containing the CLI before making the code production.

## Surfaces v2 preview codes

Four optional STM, overlap, sparse-overlap and unfolding codes use
`cp2k-spm-tools` commit `a0e486a12ad0102c6af5f9a9572c2449ec26e81e` from
[nanotech-empa/cp2k-spm-tools#42](https://github.com/nanotech-empa/cp2k-spm-tools/pull/42),
matching the Surfaces preview's local source. Code labels and wrapper names
contain `surfaces-v2-a0e486a`. The remote source directory includes the complete
commit hash, and setup refuses to retarget or reuse a modified checkout. Earlier
preview executables and production `1.5.0` definitions retain their own paths.
Sparse-overlap conversion remains serial (`withmpi=False`).

The wrappers reuse the existing `cp2k-spm-tools/1.5.0:1658742098` uenv and
`default` view. Its Python is 3.11.9, as verified on Daint on 2026-10-13; this
is separate from the application's Python >=3.12 target. The source override is
experimental and requires runtime validation and review before deployment.
Replace it with a released uenv containing the reviewed CLI before production.

## Bader analysis on Daint

The setup installs `bader-{bader_version}` for the `nanotech_empa.bader`
CalcJob plugin. The source in `bader_src/` is compiled remotely by
`scripts/install_bader.sh` with `gfortran` or `ftn`.

The vendored source is grid-based Bader analysis version 1.05 (2023-08-19),
copyright Wenjie Tang, Andri Arnaldsson, Wenrui Chai, Samuel T. Chill, and
Graeme Henkelman, under GPL-3.0-or-later. It originates from
https://theory.cm.utexas.edu/henkelman/code/bader/.


## Selective setup and personal Docker catalog

The schema-2 configuration requires the companion setup-app branch
`feature/selective-safe-setup`. Its configuration branch is
`feature/setup-readiness-checks`; keep both PRs unmerged until the new-instance
acceptance test. `runtime-catalog.yml` adds optional personal Linux-container
codes and Tigu ORCA/BandUPpy definitions. The hosted profile keeps scientific
execution remote; PythTB is an app dependency rather than an AiiDA Code.

Installation tasks are scoped to the selected computer/code subset. The setup
no longer replaces a user's remote `.bashrc`, and selected Eiger CP2K setup
installs its own data files. Quantum-worker updates are deferred.

Read [runtime installation and the deployment matrix](docs/runtime-installation.md)
for what the app installs, native/licensed prerequisites, and the SSH/Ritom
failure handling. A catalog entry does not establish a qualified deployment.
