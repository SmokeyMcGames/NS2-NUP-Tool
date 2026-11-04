# Contributing to NS2 NUP Tool

Bug reports, documentation improvements, and focused pull requests are welcome.
This project is maintained by [SmokeyMcGames](https://github.com/SmokeyMcGames).

## Before starting

Search existing issues, then describe the problem and the behavior you want.
Discuss broad changes before implementing them. Keep existing workflows and file
preservation guarantees intact. Use small changes with descriptive names; avoid
unrelated refactoring.

Do not attach game dumps, firmware, encryption keys, executable game content, or
download links to them. Reproduce problems with synthetic files whenever possible.
Redact personal paths and metadata from logs. Security reports belong in the
private channel described in [SECURITY.md](SECURITY.md).

## Set up and validate

Use Windows x64, Python 3.12, Git, and PowerShell:

```powershell
git clone https://github.com/SmokeyMcGames/NS2-NUP-Tool.git
cd NS2-NUP-Tool
.\Setup.ps1
.\.venv\Scripts\python.exe main.py
.\Build.ps1
```

Standard setup uses the project's own `nup_core` backend. To run optional
interoperability tests, run `Setup.ps1 -ReferenceTests`, set
`$env:NUP_REFERENCE_TESTS='1'`, then run the tests. This fetches the pinned reference
checkout into ignored `upstream/` for development only. Never bundle that code.

`Build.ps1` runs the unit/integration suite, packages the app, checks packaged GUI
startup and navigation, and exercises the executable's worker operations. Tests
use generated synthetic data and do not require Nintendo accounts or game dumps.
Keep assertions focused on behavior, including cancellation, hashes, package
identity, and failure cleanup. Visually check UI changes at both normal and small
window sizes; automated checks do not prove gameplay compatibility.

## Pull requests

Explain the problem, resulting behavior, and relevant validation. Add regression
coverage for data handling changes. Update the guide and changelog when behavior
changes. The pull-request template provides a short checklist.

By submitting a contribution, you confirm that you have the right to contribute
it and agree that your original contribution is available under this repository's
GPL-3.0-only license. Keep third-party attribution and license terms intact. No separate
copyright assignment or contributor license agreement is required.

## Releases

Only maintainers publish version tags. Follow [the release guide](docs/RELEASING.md)
to include matching dependency sources, license notices, and checksums. Do not
include reference implementation code or real game data in a release.
