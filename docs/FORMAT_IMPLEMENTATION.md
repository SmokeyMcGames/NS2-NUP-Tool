# Format implementation and provenance

NS2 NUP Tool 0.3.0 introduces **nup_core**, original project code licensed under
GPL-3.0-only. It replaces the previous runtime dependency on the unlicensed NUP
reference implementation.

The implementation was written for this project using the published NUP v1 binary
format's field layouts and functional requirements. It is not a copy or relicensing
of reference source. Wire constants, layout offsets, metadata tags, and compatible
interface names describe interoperability. The NUP format and reference project
remain credited to [a55uka and contributors](https://github.com/a55uka/nup).

This is an independently authored implementation, not a claim of a formally
separated clean-room process. The development history included using the reference
implementation, and optional tests still run it as an external oracle. The
reference source/specification text is not vendored or included in released assets.

## Implementation boundaries

- format.py describes binary fields and package records.
- discover.py discovers layouts and builds deterministic directory trees.
- meta.py encodes/decodes TLVs and localized records while retaining unknown tags.
- read.py validates header/TOC bounds and hashes, graph references, regions,
  metadata, names, and supported record values before exposing the index.
- pack.py serializes aligned tables and assembles containers with an explicit
  streaming-writer callback; no dependency monkeypatching is used.
- access.py and verify.py provide tree/metadata access and payload verification.
- The desktop's existing streaming, transaction, extraction, update, and cancellation
  logic remains in ns2_nup_tool.

New TOC sizes are aligned to 16 bytes. Older reference files with an unpadded TOC
remain readable. Unknown supported-range metadata tags are preserved. Unsafe
Windows extraction names, invalid child references, cycles, region overlaps,
duplicate names, invalid codecs, and malformed metadata are rejected.

## Compatibility evidence

Optional tests use the pinned reference revision
744fb7e30ce3ace787f1839ee3e7f8a010e36c04. Both readers compare every synthetic
payload, directory, package identity, and metadata record from both writers,
with and without listing retention. The reference verifier also accepts outputs
after update replacement and metadata editing. Tests are opt-in via
NUP_REFERENCE_TESTS=1; the reference checkout is development-only.

The ordinary regression suite runs without the reference dependency. Release
packaging inspects embedded modules and fails if the upstream nup package or its
metadata/reference documents appear in the bundle. Source archives are generated
from Git's tracked project files and exclude the ignored reference checkout.
