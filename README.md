# aiidalab-alps-files
Files needed to set up codes for AiiDAlab on ALPS

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

## Surfaces v2 prerelease codes

The `integration/surfaces-v2.0.0a0` branch also creates opt-in STM, overlap,
sparse-overlap, and unfolding codes whose labels contain
`surfaces-v2.0.0a0`. Their wrappers load the exact `cp2k-spm-tools` commit
recorded by `spm_preview_source_ref` from a separate remote source directory.
Existing `1.5.0` code labels and the source checkout used by the earlier
unfolding preview are not modified. Sparse overlap is deliberately serial;
the workflow sets `withmpi=False` for that CalcJob.
## Bader analysis on Daint

The setup installs `bader-{bader_version}` for the `nanotech_empa.bader`
CalcJob plugin. The source in `bader_src/` is compiled remotely by
`scripts/install_bader.sh` with `gfortran` or `ftn`.

The vendored source is grid-based Bader analysis version 1.05 (2023-08-19),
copyright Wenjie Tang, Andri Arnaldsson, Wenrui Chai, Samuel T. Chill, and
Graeme Henkelman, under GPL-3.0-or-later. It originates from
https://theory.cm.utexas.edu/henkelman/code/bader/.
