import QtQuick 2.6
import "QuickShareI18n.js" as I18n
import Sailfish.Silica 1.0
import Sailfish.TransferEngine 1.0

Column {
    id: root
    property var shareAction
    width: parent.width
    spacing: Theme.paddingMedium
    SailfishTransfer { id: transfer }
    QuickShareBus { id: api }
    Component.onCompleted: transfer.loadConfiguration(shareAction.toConfiguration())
    Image {
        anchors.horizontalCenter: parent.horizontalCenter
        width: Theme.iconSizeLarge
        height: width
        source: "file:///usr/share/sfos-quickshare/icons/quick-share-logo.png"
        fillMode: Image.PreserveAspectFit
    }
    Timer {
        interval: 5000; repeat: true
        running: root.visible && api.status.ready && !api.status.discovering
        triggeredOnStart: true
        onTriggered: api.invoke("Discover", [])
    }
    Label {
        x: Theme.horizontalPageMargin
        width: parent.width - 2*x
        wrapMode: Text.Wrap
        text: api.status.ready ? I18n.tr("Choose a device on the same local network with Quick Share receiving enabled.") : I18n.tr("Quick Share is not ready. Check the network and protocol runtime.")
    }
    Button {
        anchors.horizontalCenter: parent.horizontalCenter
        text: api.status.discovering ? I18n.tr("Searching…") : I18n.tr("Search for devices")
        enabled: api.status.ready && !api.status.discovering
        onClicked: api.invoke("Discover", [])
    }
    Repeater {
        model: api.status.peers
        delegate: BackgroundItem {
            width: root.width
            Label { x: Theme.horizontalPageMargin; width: parent.width - 2*x; anchors.verticalCenter: parent.verticalCenter; text: modelData.name; elide: Text.ElideRight }
            onClicked: {
                transfer.userData = {peer: modelData.id}
                transfer.start()
                shareAction.done()
            }
        }
    }
    Label {
        x: Theme.horizontalPageMargin; width: parent.width - 2*x
        text: api.error; wrapMode: Text.Wrap; color: Theme.highlightColor
    }
}
