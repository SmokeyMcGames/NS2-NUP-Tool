# Data and privacy

Game files are processed locally. NS2 NUP Tool does not upload dumps, run
telemetry, require an account, or install an automatic updater.

The optional Nintendo US lookup is enabled by default. It sends the detected
title ID or search title to Nintendo's public storefront/search service and
downloads product information and selected artwork. As with any web request,
those services can receive network information such as your IP address. Their
own terms and privacy policies apply. Disable automatic lookup in Create's
Source tab to keep that scan offline; manual lookup also makes network requests.

Names, publisher information, and artwork are imported only according to the
matching/review rules in [the user guide](GUIDE.md#automatic-metadata-and-nintendo-lookup).
Website artwork remains the property of its respective rights holders; the app's
GPLv3 license does not grant rights to redistribute it.

Preferences and last selected paths are stored locally using Qt QSettings.
Downloaded artwork is cached locally. Operation logs may contain paths, title
IDs, and file names. Review and redact them before sharing a bug report.

Development setup and builds download code and packages from GitHub and Python
package services. GitHub's policies govern use of this public repository.
