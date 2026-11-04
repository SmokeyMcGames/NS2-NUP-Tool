# Changelog

## 0.3.0 — 2026-11-03

- Public source repository, GPLv3 license for original project files, and contribution policies.
- Original GPLv3 NUP reader, writer, discovery, metadata codec, and verification backend.
- Removed the unlicensed reference implementation from runtime dependencies and bundles.
- Added bidirectional reference compatibility tests and malformed-container rejection coverage.
- Aligned new TOCs to 16 bytes while accepting legacy unpadded reference TOCs.
- Windows GitHub Actions build and release workflow with matching dependency source archives and license notices.
- Project overview, dashboard preview, user guide, and release documentation.

## 0.2.6 — 2026-11-03

- Ignore dump-tool `.listing` files by default when scanning, creating NUPs, and adding decrypted updates.
- Ignore stray listing files alongside update and DLC package folders during discovery.
- Keep explicit listing inclusion and complete extraction of already-stored files.

## 0.2.5 — 2026-11-03

- Extract the entire NUP by default: base, updates, DLC, and metadata needed for repacking.
- Retain selected-package and subtree extraction.
- Preserve empty files/directories, duplicate package identities, localized artwork, and metadata.
- Include loose dump-root content and reject unassigned update/DLC content instead of silently omitting it.
- Add the Selected Package dropdown heading.

## 0.2.4 — 2026-11-03

- Offer complete replacement of base ExeFS/RomFS with an update that contains its own main executable.
- Retain the confirmation prompt and preserve the choice for future update replacement.
- Suggest `Game Title [TITLEID].nup` without overwriting manually chosen paths.

## Earlier development

The initial local versions introduced the animated Classic Red dashboard, scan
and metadata discovery, optional Nintendo US lookup, update replacement, V0
fallback warnings, dump layout correction, and inspection/editing/verification.
Versions before the public repository were local development builds, not GitHub releases.
