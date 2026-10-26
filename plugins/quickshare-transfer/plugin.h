// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <QObject>
#include <QTimer>
#include <QDBusInterface>
#include <mediatransferinterface.h>
#include <transferplugininterface.h>
class QuickShareTransfer : public MediaTransferInterface {
    Q_OBJECT
public:
    QuickShareTransfer();
    QString displayName() const override { return QStringLiteral("Quick Share"); }
    QUrl serviceIcon() const override { return QUrl("file:///usr/share/sfos-quickshare/icons/quick-share-logo.png"); }
    bool cancelEnabled() const override { return true; }
    bool restartEnabled() const override { return false; }
public slots:
    void start() override;
    void cancel() override;
private:
    QDBusInterface bus;
    QTimer timer;
    QString job;
    void poll();
};
class QuickShareTransferPlugin : public QObject, public TransferPluginInterface {
    Q_OBJECT
    Q_PLUGIN_METADATA(IID "org.sailfishos.quickshare.transfer")
    Q_INTERFACES(TransferPluginInterface)
public:
    MediaTransferInterface *transferObject() override { return new QuickShareTransfer; }
    QString pluginId() const override { return QStringLiteral("QuickShare"); }
};
