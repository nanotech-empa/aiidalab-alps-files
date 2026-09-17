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

## Configuration schema

`config.yml` contains a top-level `schema_version`. Only change this value when
the structure of the YAML changes in a way that requires support in the setup
app.

Routine configuration edits, such as adding a user, changing a uenv, or updating
a code definition, do not need a manual version bump. The setup app uses the Git
commit hash of this repository as the automatic configuration revision.
