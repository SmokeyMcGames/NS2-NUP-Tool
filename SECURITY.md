# Security policy

## Supported versions

Security fixes target the current `main` branch and the latest release when one
is available. Older versions may require upgrading. There is no guaranteed
response time or paid support agreement.

## Report a vulnerability privately

Use [GitHub private vulnerability reporting](https://github.com/SmokeyMcGames/NS2-NUP-Tool/security/advisories/new).
Include the affected version, a minimal synthetic reproduction, expected impact,
and relevant logs. Do not include copyrighted game files, keys, tokens, or
unredacted personal paths. Avoid public disclosure of exploitable details before
maintainers have had an opportunity to assess and fix the issue.

If private reporting is unavailable, open a public issue asking for a private
contact method without including exploit details.

## Security boundaries

The app parses local directories and NUP containers. It rejects unsafe extraction
paths and verifies file hashes, but this does not make untrusted input harmless.
It never executes game programs. Optional storefront lookup retrieves public
Nintendo pages and artwork over HTTPS. No account credentials are required.

GitHub Actions uses read-only permissions for pull-request builds. Only a
successful, distribution-cleared version-tag release receives permission to
publish assets. Do not add `pull_request_target` workflows that execute fork code.
