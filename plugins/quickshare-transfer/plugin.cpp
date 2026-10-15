// SPDX-License-Identifier: GPL-3.0-or-later
#include "plugin.h"
#include <mediaitem.h>
#include <QDBusReply>
#include <QJsonDocument>
#include <QJsonObject>
QuickShareTransfer::QuickShareTransfer()
    : bus("org.sailfishos.QuickShare", "/org/sailfishos/QuickShare", "org.sailfishos.QuickShare", QDBusConnection::sessionBus()) {
    timer.setInterval(500);
    connect(&timer, &QTimer::timeout, this, &QuickShareTransfer::poll);
}
void QuickShareTransfer::start() {
    const QUrl source(mediaItem()->value(MediaItem::Url).toString());
    if (!source.isLocalFile()) { setStatus(TransferInterrupted); return; }
    const QString peer = mediaItem()->value(MediaItem::UserData).toMap().value("peer").toString();
    QDBusReply<QString> reply = bus.call("Send", source.toLocalFile(), peer);
    if (!reply.isValid()) { setStatus(TransferInterrupted); return; }
    job = reply.value();
    setStatus(TransferStarted);
    timer.start();
}
void QuickShareTransfer::poll() {
    QDBusReply<QString> reply = bus.call("GetJob", job);
    if (!reply.isValid()) { timer.stop(); setStatus(TransferInterrupted); return; }
    const auto data = QJsonDocument::fromJson(reply.value().toUtf8()).object();
    setProgress(data.value("progress").toDouble());
    const QString state = data.value("state").toString();
    if (state == "finished" || state == "failed" || state == "canceled") {
        timer.stop();
        setStatus(state == "finished" ? TransferFinished : state == "canceled" ? TransferCanceled : TransferInterrupted);
    }
}
void QuickShareTransfer::cancel() {
    if (!job.isEmpty()) bus.call("Cancel", job);
}
