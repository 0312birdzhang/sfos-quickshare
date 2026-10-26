// SPDX-License-Identifier: GPL-3.0-or-later
#include "plugin.h"
QList<SharingMethodInfo> QuickShareInfo::info() const {
    SharingMethodInfo method;
    method.setDisplayName(QStringLiteral("Quick Share"));
    method.setMethodId(QStringLiteral("QuickShare"));
    method.setMethodIcon(QStringLiteral("file:///usr/share/sfos-quickshare/icons/quick-share-logo.png"));
    method.setCapabilities(QStringList() << QStringLiteral("*"));
    method.setShareUIPath(QStringLiteral("/usr/share/nemo-transferengine/plugins/sharing/QuickShareShare.qml"));
    return QList<SharingMethodInfo>() << method;
}
