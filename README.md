# Quick Share for SailfishOS

Standalone Quick Share **local-network** file sharing through SailfishOS system
settings and Transfer Engine. Incoming transfers require explicit PIN confirmation.

The test RPMs target **aarch64**, require **glibc >= 2.34**, and have been tested on
SailfishOS 5.2 / Xiaomi Pad 5. Bluetooth discovery, Wi-Fi Direct, automatic hotspots
and iPhone AirDrop interoperability are not implemented. Settings, sharing pages,
notifications and common errors support English, Simplified Chinese, Traditional
Chinese, German, French and Russian; other locales fall back to English.

Open Settings → Connectivity → Quick Share to enable receiving for ten minutes.
To send, select a file in the system share menu and choose Quick Share. Both devices
must be on a mutually reachable LAN. Files are saved under Downloads/QuickShare.
Finished, failed and canceled sends disappear from settings after one minute;
the corresponding system upload records are removed after about one minute.
Active transfers and received-file history are retained.

Install both `sfos-quickshare` (C++ protocol worker, service, UI and plugins) and
`sfos-quickshare-runtime` 2.0.0 (pinned Python discovery dependencies only).
The default backend needs no JVM. Upgrade both packages together when migrating
from runtime 1.0.0; its old private JRE and JARs are removed by that upgrade.
The JVM backend and its optional package have been removed as of 0.2.2.
Upgrade an old all-in-one package and install the runtime in the same transaction.
AirDrop is optional and separate. Its old mixed 0.3.0 RPM must first be upgraded
to the AirDrop-only 0.4.0 package to avoid duplicate Quick Share files.
The [compatibility packaging patch](docs/compatibility/README.md) preserves the
AirDrop-only build changes for users of that old source tree.

Since 0.1.6, RPM transactions stop and temporarily mask the user service while
files change, then reload units and restore on-demand activation. Uninstall stops
the service and its workers. Reopen hosted settings/sharing pages after an update
to reload their QML; service outages clear cached UI state. Existing user masks
are preserved.

See [installation and testing instructions](docs/testing-zh-CN.md).

The [C++ protocol worker](native/README.md) handles UKEY2, PIN verification,
encrypted LAN file streaming, consent, cancellation and private atomic storage.
Python retains discovery, D-Bus and Sailfish integration. Backend selection occurs
before connecting; native failures never silently retry through another backend.

## Build

Prerequisites: Python 3, network access to the pinned Python dependencies, and a configured
Sailfish SDK aarch64 build target. Downloads honor HTTP_PROXY / HTTPS_PROXY; no
machine-specific proxy settings are included.

```sh
python3 tools/fetch-dependencies.py
python3 tools/build-translations.py
python3 -m unittest discover -s tests -v
```

Use qmake/mb2 with `rpm/sfos-quickshare.spec` in the Sailfish SDK, or invoke the
included helper from Windows Git Bash:

```sh
SDK_USER=pc tools/sailfish-wsl-build.sh /path/to/sfos-quickshare
```

The helper stages sources in WSL and builds with mb2. SDK_USER, SDK_ROOT,
SFOS_TARGET and other paths are configurable; see `--help`. RPMs go into `RPMS/`.
Fetched Python dependencies, build outputs and RPMs are not committed.
The spec produces the application and Python runtime RPMs only.
Native code updates change the application package; only Python vendor dependency
changes require a runtime version bump. No Java/Kotlin/Gradle tools are required.

## Translations

Edit `quickshare/locales/*.json`, retaining every English key and its `%1`, `%2`
placeholders. Run `python3 tools/build-translations.py` and commit the generated
`qml/QuickShareI18n.js` alongside the catalogs. RPM builds regenerate this module.
Both the Python service and the hosted QML pages use these shared catalogs; the
pages synchronize their Qt locale with the session service. Reopen the settings
or sharing page after changing the system language. Unknown protocol diagnostics
remain verbatim beneath localized failure summaries. Device/file names are not
translated. Node.js is optional for additional Python/JavaScript parity tests.

## Source layout

- `quickshare/`: Python D-Bus service, LAN discovery, worker and file-history integration.
- `native/`: C++11/OpenSSL protocol, LAN worker and safety/interoperability tests.
- `native/proto/`, `native/UPSTREAM.json`: retained wire schemas and source provenance.
- `plugins/`: native Sailfish sharing and transfer plugins.
- `qml/`, `data/`, `bin/`: system settings, sharing UI and session-service integration.
- `tests/`, `tools/`, `rpm/`: regression tests and repeatable packaging.

## Validation and limits

The native worker passed bidirectional file transfers against the independent
pinned JVM implementation, including an ARM64 Sailfish receiver, matching PINs,
Unicode/empty/multiple files, SHA256 checks and rejection. Native TCP tests cover
interruption, cancellation and destination safety. See [validation](native/VALIDATION.md).
The user confirmed official Windows/native bidirectional transfers and the 0.2.1
receive-error fix. Stock Android interoperability still needs testing. Automated tests do not cover
visible UI interaction. This is a test release, not store certification.

Old `sfos-airdrop` mixed packages below 0.4.0 conflict with this package because
they own the same Quick Share plugin/service names; uninstall them before migration.
No WLAN kernel modules or driver changes are included.

## Licensing and provenance

Integration code is GPL-3.0-or-later; see [LICENSE](LICENSE) and per-file notices.
The Bada/LibreDrop protocol modules retain their Apache-2.0 notices and pinned
revision in [UPSTREAM.json](native/UPSTREAM.json). Python dependencies retain
their own licenses when fetched. No Java runtime is bundled.
No Google APK, Apple binary, credentials or device captures are included.
