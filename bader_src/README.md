# Bader source bundle

This directory vendors the source files for the grid-based Bader analysis code
used by the `nanotech_empa.bader` AiiDA plugin.

The code header identifies it as:

- `GRID BASED BADER ANALYSIS (Version 1.05 08/19/23)`
- Copyright 2006-2020 Wenjie Tang, Andri Arnaldsson, Wenrui Chai,
  Samuel T. Chill, and Graeme Henkelman
- GNU General Public License, version 3 or later

Only source files and makefiles are stored here. Object files, module files, and
compiled binaries are intentionally excluded.

## Third-party numerical routine

`dsyevj3_mod.f` separately credits Joachim Kopp (copyright 2006) and carries
GNU Lesser General Public License version 2.1 or later notices. Preserve those
notices alongside the Bader source's GPL-3.0-or-later notices. The parent
repository's MIT licence does not replace either component's terms.

The source headers in `main.f90` also identify the original Bader authors,
contributors and scientific algorithm references; preserve those credits and
cite the methods actually used.
