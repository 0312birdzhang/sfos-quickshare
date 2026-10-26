Name: sfos-quickshare
%global __provides_exclude_from ^%{_libdir}/nemo-transferengine/plugins/.*$
Version: 0.2.2
Release: 1
Summary: Quick Share local-network file sharing for Sailfish OS
License: GPLv3+ and Apache-2.0
Group: Communications
URL: https://github.com/kyujin-cho/LibreDrop
Source0: %{name}-%{version}.tar.gz
BuildRequires: pkgconfig(Qt5Core)
BuildRequires: pkgconfig(openssl)
BuildRequires: pkgconfig(Qt5DBus)
BuildRequires: pkgconfig(Qt5Gui)
BuildRequires: pkgconfig(Qt5Qml)
BuildRequires: pkgconfig(nemotransferengine-qt5)
Requires(pre): systemd
Requires(preun): systemd
Requires(postun): systemd
Requires(posttrans): systemd
Requires: python3-base >= 3.8
Requires: sfos-quickshare-runtime >= 2.0.0
Requires: python3-dbus
Requires: python3-gobject
Requires: nemo-transferengine-qt5
Requires: declarative-transferengine-qt5
Requires: jolla-settings

%description
Standalone Quick Share LAN sharing and receiving through Sailfish system
settings and Transfer Engine. Native C++ handles the wire protocol; vendored
Python discovery dependencies are provided by sfos-quickshare-runtime.
Incoming transfers require explicit PIN confirmation.
Devices must share a reachable local network. Bluetooth discovery, Wi-Fi Direct
and iPhone AirDrop interoperability are not included in this test release.

%package runtime
Version: 2.0.0
Release: 1
Summary: Pinned Python discovery dependencies for Sailfish Quick Share
Requires: python3-base >= 3.8
Requires: glibc >= 2.34

%description runtime
Pinned zeroconf and related Python discovery dependencies. Native file transfers
use the application binary and system OpenSSL. This package contains no JVM.

%prep
%setup -q

%build
chmod 644 LICENSE native/NOTICE native/LICENSE-APACHE-2.0
python3 tools/build-translations.py
%qmake5
%make_build

%install
%qmake5_install
install -Dm755 bin/sfos-quickshared %{buildroot}%{_bindir}/sfos-quickshared
install -Dm644 data/org.sailfishos.QuickShare.service %{buildroot}%{_datadir}/dbus-1/services/org.sailfishos.QuickShare.service
install -Dm644 data/sfos-quickshare.service %{buildroot}%{_userunitdir}/sfos-quickshare.service
install -Dm644 data/quickshare.json %{buildroot}%{_datadir}/jolla-settings/entries/quickshare.json
install -Dm644 qml/QuickShareSettings.qml %{buildroot}%{_datadir}/jolla-settings/pages/quickshare/QuickShareSettings.qml
install -m644 qml/QuickShareBus.qml %{buildroot}%{_datadir}/jolla-settings/pages/quickshare/
install -m644 qml/QuickShareI18n.js %{buildroot}%{_datadir}/jolla-settings/pages/quickshare/
install -Dm644 qml/QuickShareShare.qml %{buildroot}%{_datadir}/nemo-transferengine/plugins/sharing/QuickShareShare.qml
install -m644 qml/QuickShareBus.qml %{buildroot}%{_datadir}/nemo-transferengine/plugins/sharing/
install -m644 qml/QuickShareI18n.js %{buildroot}%{_datadir}/nemo-transferengine/plugins/sharing/
install -Dm644 assets/quick-share-logo.png %{buildroot}%{_datadir}/sfos-quickshare/icons/quick-share-logo.png
for icon in assets/theme/z*/icon-m-quickshare.png; do
    scale=$(basename "$(dirname "$icon")")
    install -Dm644 "$icon" %{buildroot}%{_datadir}/themes/sailfish-default/silica/$scale/icons-monochrome/icon-m-quickshare.png
    install -Dm644 "$icon" %{buildroot}%{_datadir}/themes/sailfish-default/meegotouch/$scale/icons/icon-m-quickshare.png
done
mkdir -p %{buildroot}%{_datadir}/sfos-quickshare/quickshare
cp -r vendor %{buildroot}%{_datadir}/sfos-quickshare/
install -m644 quickshare/*.py %{buildroot}%{_datadir}/sfos-quickshare/quickshare/
cp -r quickshare/locales %{buildroot}%{_datadir}/sfos-quickshare/quickshare/
find %{buildroot}%{_datadir}/sfos-quickshare -type f -exec chmod 644 {} +
find %{buildroot}%{_datadir}/sfos-quickshare -type d -exec chmod 755 {} +

%pre
# Block D-Bus activation while files are replaced, including upgrades from 0.1.5.
if command -v systemctl-user >/dev/null 2>&1; then
    state=$(systemctl-user is-enabled sfos-quickshare.service 2>/dev/null || :)
    case "$state" in
        masked*) systemctl-user stop sfos-quickshare.service >/dev/null 2>&1 || : ;;
        *)
            if systemctl-user mask --runtime sfos-quickshare.service >/dev/null 2>&1; then
                mkdir -p /run/sfos-quickshare-rpm
                chmod 700 /run/sfos-quickshare-rpm
                : > /run/sfos-quickshare-rpm/unmask
            fi
            systemctl-user stop sfos-quickshare.service >/dev/null 2>&1 || :
            ;;
    esac
fi

%preun
# The old package must not stop the new package during an upgrade.
if [ "$1" -eq 0 ]; then
    if command -v systemctl-user >/dev/null 2>&1; then
        state=$(systemctl-user is-enabled sfos-quickshare.service 2>/dev/null || :)
        case "$state" in
            masked*) systemctl-user stop sfos-quickshare.service >/dev/null 2>&1 || : ;;
            *)
                if systemctl-user mask --runtime sfos-quickshare.service >/dev/null 2>&1; then
                    mkdir -p /run/sfos-quickshare-rpm
                    chmod 700 /run/sfos-quickshare-rpm
                    : > /run/sfos-quickshare-rpm/unmask
                fi
                systemctl-user stop sfos-quickshare.service >/dev/null 2>&1 || :
                ;;
        esac
    fi
fi

%postun
if [ "$1" -eq 0 ]; then
    if command -v systemctl-user >/dev/null 2>&1; then
        systemctl-user daemon-reload >/dev/null 2>&1 || :
        if [ -f /run/sfos-quickshare-rpm/unmask ]; then
            systemctl-user unmask --runtime sfos-quickshare.service >/dev/null 2>&1 || :
            rm -f /run/sfos-quickshare-rpm/unmask
        fi
    fi
fi

%posttrans
# Preserve pre-existing masks; only undo a runtime mask made by this transaction.
if command -v systemctl-user >/dev/null 2>&1; then
    systemctl-user daemon-reload >/dev/null 2>&1 || :
    if [ -f /run/sfos-quickshare-rpm/unmask ]; then
        systemctl-user unmask --runtime sfos-quickshare.service >/dev/null 2>&1 || :
        rm -f /run/sfos-quickshare-rpm/unmask
    fi
fi

%files
%license LICENSE
%license native/NOTICE native/LICENSE-APACHE-2.0
%{_libexecdir}/sfos-quickshare-native-probe
%{_libexecdir}/sfos-quickshare-native
%{_bindir}/sfos-quickshared
%{_libdir}/nemo-transferengine/plugins/sharing/libquickshareshareplugin.so
%{_libdir}/nemo-transferengine/plugins/transfer/libquicksharetransferplugin.so
%dir %{_datadir}/sfos-quickshare
%dir %{_datadir}/sfos-quickshare/quickshare
%{_datadir}/sfos-quickshare/icons
%{_datadir}/themes/sailfish-default/silica/z*/icons-monochrome/icon-m-quickshare.png
%{_datadir}/themes/sailfish-default/meegotouch/z*/icons/icon-m-quickshare.png
%{_datadir}/sfos-quickshare/quickshare/*.py
%{_datadir}/sfos-quickshare/quickshare/locales
%{_datadir}/dbus-1/services/org.sailfishos.QuickShare.service
%{_userunitdir}/sfos-quickshare.service
%{_datadir}/jolla-settings/entries/quickshare.json
%{_datadir}/jolla-settings/pages/quickshare
%{_datadir}/nemo-transferengine/plugins/sharing/QuickShareShare.qml
%{_datadir}/nemo-transferengine/plugins/sharing/QuickShareBus.qml
%{_datadir}/nemo-transferengine/plugins/sharing/QuickShareI18n.js

%files runtime
%license LICENSE
%dir %{_datadir}/sfos-quickshare
%{_datadir}/sfos-quickshare/vendor

%changelog
* Mon Oct 26 2026 Sailfish sharing contributors - 0.2.2-1
- Remove JVM backend, JRE/JAR packaging and Java/Gradle build dependencies.

* Mon Oct 26 2026 Sailfish sharing contributors - 0.2.1-1
- Ignore probe EOF before a file offer; retain errors for interrupted transfers.
- Clear stale receive errors after a successful file batch.

* Mon Oct 26 2026 Sailfish sharing contributors - 0.2.0-1
- Use native LAN file send/receive, consent, streaming and private atomic batches.
- Remove the mandatory JVM; discovery runtime 2.0.0 contains only Python modules.
- Keep the old JVM implementation in an optional compatibility package.
* Mon Oct 26 2026 Sailfish sharing contributors - 0.1.9-1
- Add experimental native UKEY2 and authenticated SecureMessage protocol core.
- Keep the JVM file-transfer backend until native transfer parity is validated.
* Mon Oct 26 2026 Sailfish sharing contributors - 0.1.8-1
- Search automatically when opening sharing and keep valid cached peers during refresh.
* Sat Oct 17 2026 Sailfish sharing contributors - 0.1.7-1
- Add a monochrome theme glyph for settings and the supplied logo for sharing.
* Sat Oct 17 2026 Sailfish sharing contributors - 0.1.6-1
- Stop and mask the session service during package changes; reload after install.
- Clear hosted UI state while the D-Bus service is unavailable.
* Fri Oct 16 2026 Sailfish sharing contributors - 0.1.5-1
- Expire completed send records after one minute.
- Split pinned dependencies into independently versioned runtime 1.0.0.
- Remove the sfos-airdrop package conflict.
* Thu Oct 15 2026 Sailfish sharing contributors - 0.1.4-1
- Display the live remaining receiving time from the session service.
* Thu Oct 15 2026 Sailfish sharing contributors - 0.1.3-1
- Use the Bluetooth device name, with hostname fallback, for send and receive.
* Thu Oct 15 2026 Sailfish sharing contributors - 0.1.2-1
- Refresh discovery while the sharing panel is open and expire stale peer lists.
* Thu Oct 15 2026 Sailfish sharing contributors - 0.1.1-1
- Localize hosted QML pages, notifications and common errors in six languages.
* Thu Oct 15 2026 Sailfish sharing contributors - 0.1.0-1
- Split Quick Share into an independent LAN testing package.
