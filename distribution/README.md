# Release materials

sources.json pins corresponding-source archives to the versions shipped by the
Windows release. tools/prepare_dependencies.py downloads and hash-checks them,
then collects license/notice texts for the portable bundle. Generated archives
and notices stay outside version control; the release publishes the archives
alongside the app ZIP.

RELEASE_NOTES.md supplies the version-tag release body. Update it together with
the app version and changelog.

The release packager checks the executable's Python module archive to confirm
that nup_core is present and upstream nup is absent. The upstream checkout is only
an optional development oracle and must never enter source or binary assets.

See ../docs/RELEASING.md for the complete workflow and licensing boundaries.
