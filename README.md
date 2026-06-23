# aiidalab-alps-files
Files needed to set up codes for AiiDAlab on ALPS

## CP2K post-processing codes on ALPS

The setup configuration installs a few helper executables in `/users/<cscsuser>/bin`
and registers the corresponding AiiDA codes:

- `bader-{bader_version}` for the `nanotech_empa.bader` plugin. The Bader source
  is vendored in `bader_src/` and compiled on the remote machine by
  `scripts/install_bader.sh` using `gfortran` or `ftn`.
- `cp2k-unfolding-{unfolding_version}` for the
  `nanotech_empa.cp2k_unfolding` plugin. The executable is a wrapper around the
  `useful_notebooks_cp2k_unfolding` Python package from
  `https://github.com/nanotech-empa/useful-notebooks.git`.
- Utility wrappers `cp2k-overlap-to-sparse-npz` and `cp2k-unfold-wfn-sparse` are
  installed alongside the MPI unfolding wrapper for manual debugging.

The unfolding wrappers intentionally use the existing `cp2k-spm-tools` uenv and
set `PYTHONPATH=/users/$USER/src/useful-notebooks`, so the uenv itself does not
need to be modified.
