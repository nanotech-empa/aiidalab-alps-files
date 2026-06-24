#!/usr/bin/env bash
set -euo pipefail

remote_user="${USER:-$(id -un)}"
src_dir="${1:-/users/${remote_user}/src/bader_src}"
bin_dir="${2:-/users/${remote_user}/bin}"
bader_exe="${bin_dir}/bader"

mkdir -p "${bin_dir}"

if [[ -x "${bader_exe}" ]]; then
    echo "Bader executable already installed at ${bader_exe}; skipping compilation."
    exit 0
fi

if [[ ! -d "${src_dir}" ]]; then
    echo "Bader source directory not found: ${src_dir}" >&2
    exit 1
fi

if command -v gfortran >/dev/null 2>&1; then
    fc=gfortran
elif command -v ftn >/dev/null 2>&1; then
    fc=ftn
else
    echo "Neither gfortran nor ftn was found on PATH." >&2
    exit 1
fi

cd "${src_dir}"
make -f makefile.lnx_ifort clean >/dev/null 2>&1 || true
make -f makefile.lnx_ifort FC="${fc}" bader

cp bader "${bader_exe}"
chmod +x "${bader_exe}"

echo "Installed Bader executable at ${bader_exe}"
