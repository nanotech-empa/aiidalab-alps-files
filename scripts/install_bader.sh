#!/usr/bin/env bash
set -euo pipefail

remote_user="${USER:-$(id -un)}"
src_dir="${1:-/users/${remote_user}/src/bader_src}"
bin_dir="${2:-/users/${remote_user}/bin}"

mkdir -p "${bin_dir}"

if [[ ! -d "${src_dir}" ]]; then
    echo "Bader source directory not found: ${src_dir}" >&2
    exit 1
fi

cd "${src_dir}"

if command -v gfortran >/dev/null 2>&1; then
    fc=gfortran
elif command -v ftn >/dev/null 2>&1; then
    fc=ftn
else
    echo "Neither gfortran nor ftn was found on PATH." >&2
    exit 1
fi

make -f makefile.osx_gfortran clean >/dev/null 2>&1 || true
make -f makefile.osx_gfortran FC="${fc}" LINK="" bader

cp bader "${bin_dir}/bader"
chmod +x "${bin_dir}/bader"

echo "Installed Bader executable at ${bin_dir}/bader"
