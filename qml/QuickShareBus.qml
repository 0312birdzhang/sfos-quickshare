import QtQuick 2.6
import "QuickShareI18n.js" as I18n
import Nemo.DBus 2.0

DBusInterface {
    id: root
    bus: DBus.SessionBus
    service: "org.sailfishos.QuickShare"
    iface: "org.sailfishos.QuickShare"
    path: "/org/sailfishos/QuickShare"
    property var status: ({ready: false, receiving: false, peers: [], pending: []})
    property string error: ""
    function invoke(method, args) {
        call(method, args, function() { refresh() }, function(message) { root.error = I18n.tr("Request failed: %1", String(message)) })
    }
    function refresh() {
        call("GetStatus", [], function(result) { status = JSON.parse(result); if (status.error) root.error = status.error },
             function(message) { root.error = I18n.tr("Request failed: %1", String(message)) })
    }
    Component.onCompleted: call("SetLanguage", [Qt.locale().name], function() { root.refresh() }, function() { root.refresh() })
    property Timer pollTimer: Timer { interval: 1000; repeat: true; running: true; onTriggered: root.refresh() }
}
