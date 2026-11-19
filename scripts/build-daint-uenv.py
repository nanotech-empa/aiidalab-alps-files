"""Build public, source-locked EMPA uenvs using the CSCS shared service.

Default mode only reports the selected recipe. Execution stages regular files
under an immutable source hash, invokes ``uenv build`` once and saves the real
service response. No AiiDA, scientific jobs, installed Codes or SSH edits.
Private/licensed sources must never be included in service recipes.
"""

import argparse
import hashlib
import io
import json
import re
import shlex
import subprocess
import tarfile
from pathlib import Path
from typing import NoReturn


def fail(message: str) -> NoReturn:
    raise ValueError(message)


STAGE = r"""
import hashlib, io, json, os, pathlib, sys, tarfile
root = pathlib.Path(sys.argv[1])
identity = sys.argv[2]
if not root.is_absolute() or root == pathlib.Path('/') or '..' in root.parts:
    raise ValueError('Use an absolute non-root build directory')
for path in (root, *root.parents):
    if path.is_symlink():
        raise ValueError('Preserve symlinked build paths')
with tarfile.open(fileobj=io.BytesIO(sys.stdin.buffer.read())) as archive:
    members = archive.getmembers()
    if any(
        not m.isfile() or pathlib.Path(m.name).is_absolute()
        or '..' in pathlib.Path(m.name).parts for m in members
    ):
        raise ValueError('Only regular contained recipe files are allowed')
    data = {m.name: archive.extractfile(m).read() for m in members}
hashes = {name: hashlib.sha256(content).hexdigest() for name, content in data.items()}
if hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest() != identity:
    raise ValueError('Recipe identity mismatch')
dest = root / identity
if dest.exists():
    current = {
        p.relative_to(dest).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in dest.rglob('*')
        if p.is_file() and not p.name.startswith('empa-build')
    }
    if current != hashes:
        raise ValueError('Existing staged recipe differs; preserve it')
else:
    dest.mkdir(parents=True)
    for name, content in data.items():
        path = dest / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(content)
        path.chmod(0o755 if path.name == 'post-install' else 0o644)
print(json.dumps({'recipe': str(dest), 'source_id': identity}))
"""

BUILD = r"""
import datetime, json, pathlib, subprocess, sys
path = pathlib.Path(sys.argv[1])
label = sys.argv[2]
receipt = path / 'empa-build-submission.json'
if receipt.exists():
    previous = json.loads(receipt.read_text())
    if (len(sys.argv) != 4 or sys.argv[3] != '--resume-unstarted'
        or previous.get('status') != 'SUBMISSION_FAILED'
        or previous.get('control_performed') is not False):
        raise ValueError(
            'A submission receipt already exists; inspect it '
            'rather than duplicate the build'
        )
    # Preserve the exact failed receipt; only a demonstrably unstarted command
    # can be retried by this explicitly selected recovery path.
    history = path / 'empa-build-unstarted-failure.json'
    with history.open('x') as stream:
        json.dump(previous, stream, indent=2)
    receipt.unlink()
data = {
    'label': label, 'status': 'SUBMITTING',
    'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'control_performed': False, 'scientific_jobs': 0,
}
with receipt.open('x') as stream:
    json.dump(data, stream, indent=2)
try:
    process = subprocess.Popen(
        ['uenv', 'build', str(path), label], stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, universal_newlines=True,
    )
    data.update(control_performed=True, status='BUILD_CLIENT_RUNNING')
    receipt.write_text(json.dumps(data, indent=2) + '\n')
    stdout, stderr = process.communicate()
    data.update(
        returncode=process.returncode,
        status='SUBMITTED' if process.returncode == 0 else 'BUILD_SERVICE_REJECTED',
        response=stdout + stderr,
    )
    (path / 'empa-build.log').write_text(data['response'])
except BaseException as error:
    data.update(status='SUBMISSION_FAILED', error=str(error))
    raise
finally:
    receipt.write_text(json.dumps(data, indent=2) + '\n')
print(json.dumps(data))
"""


def recipe_bundle(recipe):
    files = {}
    for path in sorted(recipe.rglob("*")):
        if path.is_symlink():
            fail("Recipes must not contain symlinks")
        if path.is_file():
            files[path.relative_to(recipe).as_posix()] = path.read_bytes()
    required = {"config.yaml", "compilers.yaml", "environments.yaml"}
    if not required <= files.keys():
        fail("Incomplete uenv recipe")
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    identity = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return identity, stream.getvalue(), hashes


def ssh(host, arguments, data=None):
    return subprocess.run(
        ["ssh", "-oBatchMode=yes", "-oConnectTimeout=20", host, shlex.join(arguments)],
        input=data,
        capture_output=True,
        check=True,
    )


def build(
    recipe,
    label,
    root,
    execute=False,
    host="daint.alps.cscs.ch",
    resume_unstarted=False,
):
    if not re.fullmatch(r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+@daint%gh200", label):
        fail("Use a named version for daint%gh200")
    identity, payload, hashes = recipe_bundle(recipe)
    result = {
        "status": "PLAN",
        "label": label,
        "source_id": identity,
        "files": hashes,
        "host": host,
        "build_root": root,
        "scientific_jobs": 0,
        "registry_visibility": "all CSCS users",
    }
    if execute:
        staged = json.loads(
            ssh(host, ["python3", "-c", STAGE, root, identity], payload).stdout
        )
        result.update(status="SUBMISSION_REQUESTED", remote_recipe=staged["recipe"])
        try:
            arguments = ["python3", "-c", BUILD, staged["recipe"], label]
            if resume_unstarted:
                arguments.append("--resume-unstarted")
            reply = ssh(host, arguments)
            result.update(json.loads(reply.stdout))
        except subprocess.CalledProcessError as error:
            result.update(
                status="SUBMISSION_OBSERVATION_FAILED",
                control_performed="unknown; inspect remote receipt",
                returncode=error.returncode,
                response=error.stderr.decode(errors="replace"),
            )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--remote-root", required=True)
    parser.add_argument("--host", default="daint.alps.cscs.ch")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume-unstarted", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = build(
        args.recipe,
        args.label,
        args.remote_root,
        args.execute,
        args.host,
        args.resume_unstarted,
    )
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    print(text)
    if result["status"] not in ("PLAN", "SUBMITTED"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
