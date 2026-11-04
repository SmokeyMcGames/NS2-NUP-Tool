# Validation and limits

The 0.3.0 local build passed **101 automated tests**, a packaged Qt startup,
navigation, and shutdown check, and **37 packaged operation checks**. The copied
portable app independently passed the same operation checks and matched the
build output by SHA-256. GitHub Actions provides a separate clean-runner result.

The suite includes bidirectional reference interoperability and malformed header,
TOC, graph, extent, and metadata rejection for the new original backend. The
packaged executable's module inventory contains nup_core and no upstream nup.

Coverage includes base/update/DLC discovery, full and selected extraction,
metadata preservation, hash verification, empty/duplicate packages, streamed
compression, update replacement, layout correction, V0 fallback, cancellation,
unsafe path rejection, optional listing inclusion, and actual Qt-to-worker flows.
All committed fixtures generate synthetic data; no game content is included.

The 0.3.0 packaged worker also extracted and repacked a local 8.77 GiB container:
all 3 packages, 53 files, 10,345,166,391 logical bytes, directory paths, package
identities, and payload SHA-256 values were preserved. Full verification passed;
the input's size and modification time were unchanged. The smaller compressed
output retained the same payloads. Temporary copies were removed after checking.
That private test data and its machine-specific logs are not published here.

These results establish the tested container and app behavior. They do not
establish emulator compatibility or successful gameplay. Clean Windows versions,
different hardware/DPI configurations, and future storefront changes may expose
additional issues. Report reproducible problems with synthetic inputs when possible.
