// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <QObject>
#include <sharingplugininterface.h>
#include <sharingplugininfo.h>
class QuickShareInfo : public SharingPluginInfo {
    Q_OBJECT
public:
    QList<SharingMethodInfo> info() const override;
    void query() override { emit infoReady(); }
};
class QuickShareSharePlugin : public QObject, public SharingPluginInterface {
    Q_OBJECT
    Q_PLUGIN_METADATA(IID "org.sailfishos.quickshare.sharing")
    Q_INTERFACES(SharingPluginInterface)
public:
    SharingPluginInfo *infoObject() override { return new QuickShareInfo; }
    QString pluginId() const override { return QStringLiteral("QuickShare"); }
};
