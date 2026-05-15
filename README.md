# aiidalab-alps-files
Files needed to set up codes for AiiDAlab on ALPS

## Configuration schema

`config.yml` contains a top-level `schema_version`. Only change this value when
the structure of the YAML changes in a way that requires support in the setup
app.

Routine configuration edits, such as adding a user, changing a uenv, or updating
a code definition, do not need a manual version bump. The setup app uses the Git
commit hash of this repository as the automatic configuration revision.
