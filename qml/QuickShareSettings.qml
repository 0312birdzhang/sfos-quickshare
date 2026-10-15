import QtQuick 2.6
import "QuickShareI18n.js" as I18n
import Sailfish.Silica 1.0

Page {
    id: root
    QuickShareBus { id: api }
    SilicaFlickable {
        anchors.fill: parent
        contentHeight: column.height
        Column {
            id: column
            width: parent.width
            spacing: Theme.paddingMedium
            PageHeader { title: "Quick Share" }
            TextSwitch {
                text: api.status.receiving ? I18n.tr("Allow receiving (%1)",
                    Math.floor((api.status.receivingSeconds || 0) / 60) + ":" +
                    ("0" + (api.status.receivingSeconds || 0) % 60).slice(-2)) : I18n.tr("Allow receiving (10 minutes)")
                description: I18n.tr("Receive files on the same local network. Confirm matching PINs. Files are saved in Downloads/QuickShare.")
                checked: api.status.receiving
                automaticCheck: false
                enabled: api.status.ready
                onClicked: api.invoke("SetReceiving", [!checked])
            }
            Label {
                x: Theme.horizontalPageMargin; width: parent.width - 2*x; wrapMode: Text.Wrap
                text: api.status.ready ? I18n.tr("Local network ready. iPhone AirDrop is not supported yet.") : I18n.tr("Quick Share is not ready. Check the network and protocol runtime.")
            }
            Repeater {
                model: api.status.pending
                delegate: Column {
                    width: column.width
                    Label {
                        x: Theme.horizontalPageMargin; width: parent.width - 2*x; wrapMode: Text.Wrap
                        text: modelData.sender + "\n" + I18n.tr("PIN: %1", modelData.pin) + "\n" + modelData.files.join("\n")
                    }
                    Column {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: parent.width - 2 * Theme.horizontalPageMargin
                        spacing: Theme.paddingSmall
                        Button { width: parent.width; text: I18n.tr("PINs match, receive"); onClicked: api.invoke("Approve", [modelData.id, true]) }
                        Button { width: parent.width; text: I18n.tr("Reject"); onClicked: api.invoke("Approve", [modelData.id, false]) }
                    }
                }
            }
            Repeater {
                model: api.status.jobs || []
                delegate: Column {
                    width: column.width
                    visible: modelData.mode === "send"
                    Label {
                        x: Theme.horizontalPageMargin; width: parent.width - 2*x; wrapMode: Text.Wrap
                        text: (modelData.pin ? I18n.tr("Sending PIN: %1", modelData.pin) + "\n" : "") +
                              (modelData.state === "finished" ? I18n.tr("Transfer complete") : modelData.state === "failed" ? I18n.tr("Transfer failed: %1", modelData.error) :
                               modelData.state === "canceled" ? I18n.tr("Canceled") : modelData.state === "waiting" ? I18n.tr("Ask the recipient to verify the PIN and accept.") : I18n.tr("Sending…"))
                    }
                    ProgressBar { width: parent.width; value: modelData.progress || 0; maximumValue: 1 }
                    Button {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: parent.width - 2 * Theme.horizontalPageMargin
                        text: I18n.tr("Cancel transfer")
                        visible: modelData.state === "running" || modelData.state === "waiting"
                        onClicked: api.invoke("Cancel", [modelData.id])
                    }
                }
            }
            Label {
                x: Theme.horizontalPageMargin; width: parent.width - 2*x; wrapMode: Text.Wrap
                text: api.error; color: Theme.highlightColor
            }
        }
        VerticalScrollDecorator {}
    }
}
