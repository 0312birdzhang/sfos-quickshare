# Quick Share for SailfishOS

Standalone Quick Share **local-network** file sharing through SailfishOS system
settings and Transfer Engine. Incoming transfers require explicit PIN confirmation.

The test RPM targets **aarch64**, requires **glibc >= 2.34**, and has been tested on
SailfishOS 5.2 / Xiaomi Pad 5. Bluetooth discovery, Wi-Fi Direct, automatic hotspots
and iPhone AirDrop interoperability are not implemented. The UI is mainly Chinese.

Open Settings → Connectivity → Quick Share to enable receiving for ten minutes.
To send, select a file in the system share menu and choose Quick Share. Both devices
must be on a mutually reachable LAN. Files are saved under Downloads/QuickShare.

See [installation and testing instructions](docs/testing-zh-CN.md).

## Build

Prerequisites: Python 3.10.12+ (including tarfile extraction filters), JDK 17,
network access to the pinned dependencies and Gradle repositories, and a configured
Sailfish SDK aarch64 build target. Downloads honor HTTP_PROXY / HTTPS_PROXY; no
machine-specific proxy settings are included.

```sh
python3 tools/fetch-dependencies.py
cd quickshare/jvm
sh gradlew :bridge:installDist :bridge:test :core-protocol:test
cd ../..
python3 tools/prepare-quickshare.py
python3 -m unittest discover -s tests -v
```

The preparation script verifies the runtime archive, extracts it and records built
JAR hashes. Run these steps on Linux/WSL; the generated runtime contains Unix links.
Use qmake/mb2 with `rpm/sfos-quickshare.spec` in the Sailfish SDK, or invoke the
included helper from Windows Git Bash:

```sh
SDK_USER=pc tools/sailfish-wsl-build.sh /path/to/sfos-quickshare
```

The helper stages sources in WSL and builds with mb2. SDK_USER, SDK_ROOT,
SFOS_TARGET and other paths are configurable; see `--help`. RPMs go into `RPMS/`.
Dependencies, runtime images, generated JARs and RPMs are not committed.

## Source layout

- `quickshare/`: Python D-Bus service, LAN discovery, worker and file-history integration.
- `quickshare/jvm/`: pinned Bada/LibreDrop protocol core, its tests and our JSON bridge.
- `plugins/`: native Sailfish sharing and transfer plugins.
- `qml/`, `data/`, `bin/`: system settings, sharing UI and session-service integration.
- `tests/`, `tools/`, `rpm/`: regression tests and repeatable packaging.

## Validation and limits

The independent package passed device installation, D-Bus activation, native plugin
and QML checks, bidirectional transfers with a controlled Linux peer, PIN checks,
file hashes and per-file history. Windows official Quick Share reception was
previously confirmed by a user in the combined prototype. Stock Android clients
and the reverse Windows direction still need tester verification. Automated checks
do not cover visible UI interaction. This is a test release, not store certification.

Old `sfos-airdrop` mixed packages below 0.4.0 conflict with this package because
they own the same Quick Share plugin/service names; uninstall them before migration.
No WLAN kernel modules or driver changes are included.

## Licensing and provenance

Integration code is GPL-3.0-or-later; see [LICENSE](LICENSE) and per-file notices.
The Bada/LibreDrop protocol modules retain their Apache-2.0 notices and pinned
revision in [UPSTREAM.json](quickshare/jvm/UPSTREAM.json). Python dependencies retain
their own licenses when fetched. The bundled-in-RPM Eclipse Temurin runtime is
GPLv2 with Classpath Exception; its archive hash and origin are pinned separately.
No Google APK, Apple binary, credentials or device captures are included.
