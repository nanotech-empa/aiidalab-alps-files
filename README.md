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
