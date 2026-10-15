// SPDX-License-Identifier: GPL-3.0-or-later
#include "plugin.h"
QList<SharingMethodInfo> QuickShareInfo::info() const {
    SharingMethodInfo method;
    method.setDisplayName(QStringLiteral("Quick Share"));
    method.setMethodId(QStringLiteral("QuickShare"));
    method.setMethodIcon(QStringLiteral("image://theme/icon-m-share"));
    method.setCapabilities(QStringList() << QStringLiteral("*"));
    method.setShareUIPath(QStringLiteral("/usr/share/nemo-transferengine/plugins/sharing/QuickShareShare.qml"));
    return QList<SharingMethodInfo>() << method;
}
