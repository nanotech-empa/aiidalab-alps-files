# aiidalab-alps-files
Files needed to set up codes for AiiDAlab on ALPS

## CP2K post-processing codes on ALPS

The setup configuration installs a few helper executables in `/users/<cscsuser>/bin`
and registers the corresponding AiiDA codes:

- `bader-{bader_version}` for the `nanotech_empa.bader` plugin. The Bader source
  is vendored in `bader_src/` and compiled on the remote machine by
  `scripts/install_bader.sh` using `gfortran` or `ftn`. The source code
  comes from https://theory.cm.utexas.edu/henkelman/code/bader/.
- `stm-{spm_version}` and `overlap-{spm_version}` for the `nanotech_empa.stm`
  and `nanotech_empa.overlap` plugins. Their executables are wrappers around
  `/users/<cscsuser>/src/cp2k-spm-tools`, using the existing `cp2k-spm-tools`
  uenv for dependencies while taking the Python sources from the cloned repo.
- `cp2k-unfolding-{unfolding_version}` for the
  `nanotech_empa.cp2k_unfolding` plugin. The executable is a wrapper around the
  `useful_notebooks_cp2k_unfolding` Python package from
  `https://github.com/nanotech-empa/useful-notebooks.git`.
- Utility wrappers `cp2k-overlap-to-sparse-npz` and `cp2k-unfold-wfn-sparse` are
  installed alongside the MPI unfolding wrapper for manual debugging.

The unfolding wrappers intentionally use the existing `cp2k-spm-tools` uenv and
set `PYTHONPATH=/users/$USER/src/useful-notebooks`, so the uenv itself does not
need to be modified.

The SPM and overlap wrappers follow the same pattern for `cp2k-spm-tools`: the
setup clones the configured branch into `/users/<cscsuser>/src/cp2k-spm-tools`
and the wrappers prepend that path to `PYTHONPATH`, so fixes can be deployed
without rebuilding the uenv.
