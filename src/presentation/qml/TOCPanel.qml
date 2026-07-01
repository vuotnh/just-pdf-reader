import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

/**
 * TOCPanel.qml - Table of Contents panel for document outline navigation.
 *
 * Displays the hierarchical document outline extracted from PDF/EPUB
 * structure and allows navigation to any section by clicking.
 * Indentation reflects the nesting level of TOC entries.
 *
 * Requirements: 2.5, 14.1
 */
Item {
    id: root

    // The TOC list model (from controller.tocModel)
    property var tocModel: null

    // Signal emitted when user clicks a TOC entry to navigate
    signal entryClicked(int pageNumber)

    // Panel header
    Rectangle {
        id: header
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: 40
        color: "#fafafa"
        border.color: "#e0e0e0"
        border.width: 1

        Label {
            anchors.centerIn: parent
            text: qsTr("Table of Contents")
            font.pixelSize: 14
            font.bold: true
            color: "#333333"
        }
    }

    // TOC list
    ListView {
        id: tocListView
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        clip: true
        spacing: 1

        model: root.tocModel

        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        delegate: Rectangle {
            width: tocListView.width
            height: 36
            color: mouseArea.containsMouse ? "#e8f0fe" : "transparent"

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12 + (model.level - 1) * 16
                anchors.rightMargin: 8
                spacing: 8

                // Level indicator dot
                Rectangle {
                    width: 6
                    height: 6
                    radius: 3
                    color: model.level === 1 ? "#1a73e8" : "#999999"
                    Layout.alignment: Qt.AlignVCenter
                }

                // Entry title
                Label {
                    Layout.fillWidth: true
                    text: model.title || ""
                    font.pixelSize: model.level === 1 ? 13 : 12
                    font.bold: model.level === 1
                    color: "#333333"
                    elide: Text.ElideRight
                }

                // Page number
                Label {
                    text: (model.pageNumber + 1).toString()
                    font.pixelSize: 11
                    color: "#888888"
                    Layout.alignment: Qt.AlignVCenter
                }
            }

            MouseArea {
                id: mouseArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor

                onClicked: {
                    root.entryClicked(model.pageNumber)
                }
            }
        }

        // Empty state
        Label {
            anchors.centerIn: parent
            text: qsTr("No table of contents available")
            font.pixelSize: 13
            color: "#999999"
            visible: tocListView.count === 0
        }
    }
}
