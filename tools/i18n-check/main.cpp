// SPDX-License-Identifier: GPL-3.0-or-later
#include <QGuiApplication>
#include <QLocale>
#include <QQmlEngine>
#include <QQmlComponent>
#include <QDebug>
#include <QScopedPointer>
#include <cstdio>
int main(int argc, char **argv) {
    QGuiApplication app(argc, argv);
    const QStringList locales = {"en_US", "zh_CN", "zh_TW", "de_DE", "fr_FR", "ru_RU", "es_ES"};
    const QStringList expected = {"Reject", QString::fromUtf8("拒绝"), QString::fromUtf8("拒絕"),
        "Ablehnen", "Refuser", QString::fromUtf8("Отклонить"), "Reject"};
    for (int i=0; i<locales.size(); i++) {
        QLocale::setDefault(QLocale(locales[i]));
        QQmlEngine engine;
        QQmlComponent component(&engine);
        component.setData("import QtQuick 2.6\nimport \"file:///usr/share/jolla-settings/pages/quickshare/QuickShareI18n.js\" as I18n\nQtObject { property string message: I18n.tr(\"Reject\") }", QUrl());
        QScopedPointer<QObject> object(component.create());
        if (!object || object->property("message").toString() != expected[i]) {
            qWarning() << locales[i] << component.errors(); return 1;
        }
        std::printf("Qt locale %s: PASS\n", qPrintable(locales[i]));
    }
    return 0;
}
