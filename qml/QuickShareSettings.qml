import QtQuick 2.6
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
                text: "允许接收（10 分钟）"
                description: "同一局域网内接收文件。核对双方 PIN 后确认；文件保存到 Downloads/QuickShare。"
                checked: api.status.receiving
                automaticCheck: false
                enabled: api.status.ready
                onClicked: api.invoke("SetReceiving", [!checked])
            }
            Label {
                x: Theme.horizontalPageMargin; width: parent.width - 2*x; wrapMode: Text.Wrap
                text: api.status.ready ? "局域网连接已就绪。此后端兼容 Quick Share 协议；iPhone AirDrop 支持尚未实现。" : "Quick Share 未就绪，请检查网络和协议运行时。"
            }
            Repeater {
                model: api.status.pending
                delegate: Column {
                    width: column.width
                    Label {
                        x: Theme.horizontalPageMargin; width: parent.width - 2*x; wrapMode: Text.Wrap
                        text: modelData.sender + "\nPIN: " + modelData.pin + "\n" + modelData.files.join("\n")
                    }
                    Row {
                        anchors.horizontalCenter: parent.horizontalCenter
                        Button { text: "PIN 一致，接收"; onClicked: api.invoke("Approve", [modelData.id, true]) }
                        Button { text: "拒绝"; onClicked: api.invoke("Approve", [modelData.id, false]) }
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
                        text: (modelData.pin ? "发送 PIN: " + modelData.pin + "\n" : "") +
                              (modelData.state === "finished" ? "发送完成" : modelData.state === "failed" ? "发送失败：" + modelData.error :
                               modelData.state === "canceled" ? "已取消" : modelData.state === "waiting" ? "请接收方核对 PIN 并确认" : "正在发送")
                    }
                    ProgressBar { width: parent.width; value: modelData.progress || 0; maximumValue: 1 }
                    Button {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "取消发送"
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
