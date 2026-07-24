# aiidalab-alps-files
Files needed to set up codes for AiiDAlab on ALPS

## Bader analysis on Daint

The setup installs `bader-{bader_version}` for the `nanotech_empa.bader`
CalcJob plugin. The source in `bader_src/` is compiled remotely by
`scripts/install_bader.sh` with `gfortran` or `ftn`.

The vendored source is grid-based Bader analysis version 1.05 (2023-08-19),
copyright Wenjie Tang, Andri Arnaldsson, Wenrui Chai, Samuel T. Chill, and
Graeme Henkelman, under GPL-3.0-or-later. It originates from
https://theory.cm.utexas.edu/henkelman/code/bader/.
