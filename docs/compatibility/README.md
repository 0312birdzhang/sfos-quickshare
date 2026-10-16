# Coexisting with the old AirDrop package

`sfos-airdrop-0.3.0` bundled its own Quick Share service and plugins. Removing
an RPM `Conflicts` entry alone cannot make those duplicate files coexist.

The accompanying `sfos-airdrop-0.4.0-packaging.patch` updates the old AirDrop
source tree to build an AirDrop-only 0.4.0 RPM. Apply it in that source tree:

```sh
git apply /path/to/sfos-quickshare/docs/compatibility/sfos-airdrop-0.4.0-packaging.patch
```

Then rebuild AirDrop with its existing Sailfish SDK workflow. Install the
AirDrop 0.4.0 upgrade, Quick Share main RPM and runtime RPM in one transaction
when migrating from the old mixed package. AirDrop is optional for new installs.

The patch changes only the AirDrop RPM spec and qmake subprojects. It removes
Quick Share payload ownership; it does not change wireless drivers or establish
Apple interoperability. Its result was checked against the built 0.4.0 sources.
