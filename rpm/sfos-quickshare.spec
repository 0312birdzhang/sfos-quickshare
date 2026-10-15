Name: sfos-quickshare
%global __requires_exclude_from ^%{_libdir}/sfos-quickshare/runtime/.*$
%global __provides_exclude_from ^(%{_libdir}/sfos-quickshare/runtime/.*|%{_libdir}/nemo-transferengine/plugins/.*)$
Version: 0.1.4
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
Requires: glibc >= 2.34
Requires: python3-dbus
Requires: python3-gobject
Requires: nemo-transferengine-qt5
Requires: declarative-transferengine-qt5
Requires: jolla-settings
Conflicts: sfos-airdrop < 0.4.0

%description
Standalone Quick Share LAN sharing and receiving through Sailfish system
settings and Transfer Engine. Includes the Bada protocol core and an isolated
ARM64 Java runtime. Incoming transfers require explicit PIN confirmation.
Devices must share a reachable local network. Bluetooth discovery, Wi-Fi Direct
and iPhone AirDrop interoperability are not included in this test release.

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
%{_datadir}/sfos-quickshare
%{_libdir}/sfos-quickshare
%{_datadir}/dbus-1/services/org.sailfishos.QuickShare.service
%{_userunitdir}/sfos-quickshare.service
%{_datadir}/jolla-settings/entries/quickshare.json
%{_datadir}/jolla-settings/pages/quickshare
%{_datadir}/nemo-transferengine/plugins/sharing/QuickShareShare.qml
%{_datadir}/nemo-transferengine/plugins/sharing/QuickShareBus.qml
%{_datadir}/nemo-transferengine/plugins/sharing/QuickShareI18n.js

%changelog
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
