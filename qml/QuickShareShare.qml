import QtQuick 2.6
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
    Label {
        x: Theme.horizontalPageMargin
        width: parent.width - 2*x
        wrapMode: Text.Wrap
        text: api.status.ready ? "选择接收设备（同一局域网，开启 Quick Share 接收）" : "Quick Share 未就绪，请检查网络和运行时。"
    }
    Button {
        anchors.horizontalCenter: parent.horizontalCenter
        text: api.status.discovering ? "正在搜索…" : "搜索设备"
        enabled: api.status.ready && !api.status.discovering
        onClicked: api.invoke("Discover", [])
    }
    Repeater {
        model: api.status.peers
        delegate: BackgroundItem {
            width: root.width
            Label { x: Theme.horizontalPageMargin; anchors.verticalCenter: parent.verticalCenter; text: modelData.name }
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
