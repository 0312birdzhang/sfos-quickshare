Name: sfos-quickshare
%global __requires_exclude_from ^%{_libdir}/sfos-quickshare/runtime/.*$
%global __provides_exclude_from ^(%{_libdir}/sfos-quickshare/runtime/.*|%{_libdir}/nemo-transferengine/plugins/.*)$
Version: 0.1.5
Release: 1
Summary: Quick Share local-network file sharing for Sailfish OS
License: GPLv3+ and Apache-2.0 and GPLv2 with exceptions
Group: Communications
URL: https://github.com/kyujin-cho/LibreDrop
Source0: %{name}-%{version}.tar.gz
BuildRequires: pkgconfig(Qt5Core)
BuildRequires: pkgconfig(Qt5DBus)
BuildRequires: pkgconfig(Qt5Gui)
BuildRequires: pkgconfig(Qt5Qml)
BuildRequires: pkgconfig(nemotransferengine-qt5)
Requires: python3-base >= 3.8
Requires: sfos-quickshare-runtime >= 1.0.0
Requires: python3-dbus
Requires: python3-gobject
Requires: nemo-transferengine-qt5
Requires: declarative-transferengine-qt5
Requires: jolla-settings

%description
Standalone Quick Share LAN sharing and receiving through Sailfish system
settings and Transfer Engine. The protocol core and private Java runtime are
provided by sfos-quickshare-runtime. Incoming transfers require explicit PIN confirmation.
Devices must share a reachable local network. Bluetooth discovery, Wi-Fi Direct
and iPhone AirDrop interoperability are not included in this test release.

%package runtime
Version: 1.0.0
Release: 1
Summary: Pinned protocol and private Java dependencies for Sailfish Quick Share
Requires: python3-base >= 3.8
Requires: glibc >= 2.34

%description runtime
Pinned Python dependencies, Bada protocol core, JSON bridge and isolated ARM64
Java runtime. Install once; ordinary sfos-quickshare updates reuse this package.
The runtime version changes only when these dependencies or the bridge change.

%prep
%setup -q

%build
chmod 644 LICENSE
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
mkdir -p %{buildroot}%{_datadir}/sfos-quickshare/quickshare
mkdir -p %{buildroot}%{_libdir}/sfos-quickshare/runtime
cp -r vendor %{buildroot}%{_datadir}/sfos-quickshare/
install -m644 quickshare/*.py %{buildroot}%{_datadir}/sfos-quickshare/quickshare/
cp -r quickshare/lib quickshare/licenses %{buildroot}%{_datadir}/sfos-quickshare/quickshare/
cp -r quickshare/locales %{buildroot}%{_datadir}/sfos-quickshare/quickshare/
cp -a quickshare/runtime-image/*/* %{buildroot}%{_libdir}/sfos-quickshare/runtime/
install -m644 quickshare/runtime.lock.json quickshare/artifacts.lock.json quickshare/jvm/UPSTREAM.json %{buildroot}%{_datadir}/sfos-quickshare/quickshare/
find %{buildroot}%{_datadir}/sfos-quickshare -type f -exec chmod 644 {} +
find %{buildroot}%{_datadir}/sfos-quickshare -type d -exec chmod 755 {} +
find %{buildroot}%{_libdir}/sfos-quickshare -type f -exec chmod 644 {} +
find %{buildroot}%{_libdir}/sfos-quickshare -type d -exec chmod 755 {} +
chmod 755 %{buildroot}%{_libdir}/sfos-quickshare/runtime/bin/*
chmod 755 %{buildroot}%{_libdir}/sfos-quickshare/runtime/lib/jspawnhelper %{buildroot}%{_libdir}/sfos-quickshare/runtime/lib/jexec

%files
%license LICENSE
%{_bindir}/sfos-quickshared
%{_libdir}/nemo-transferengine/plugins/sharing/libquickshareshareplugin.so
%{_libdir}/nemo-transferengine/plugins/transfer/libquicksharetransferplugin.so
%dir %{_datadir}/sfos-quickshare
%dir %{_datadir}/sfos-quickshare/quickshare
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
%dir %{_datadir}/sfos-quickshare/quickshare
%{_datadir}/sfos-quickshare/vendor
%{_datadir}/sfos-quickshare/quickshare/lib
%{_datadir}/sfos-quickshare/quickshare/licenses
%{_datadir}/sfos-quickshare/quickshare/runtime.lock.json
%{_datadir}/sfos-quickshare/quickshare/artifacts.lock.json
%{_datadir}/sfos-quickshare/quickshare/UPSTREAM.json
%{_libdir}/sfos-quickshare

%changelog
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
