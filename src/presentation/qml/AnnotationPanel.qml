import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

/**
 * AnnotationPanel.qml - Panel displaying all annotations for the current book.
 *
 * Shows annotations in chronological order, grouped by chapter/page.
 * Each annotation entry displays type, color indicator, selected text,
 * note content, and creation timestamp. Supports deletion and navigation.
 *
 * Requirements: 5.6, 2.8, 3.7
 */
Item {
    id: root

    // Reference to the annotation controller (set via context property)
    property var annotationController: null

    // Signal emitted when user clicks an annotation to navigate to its location
    signal annotationClicked(string annotationId, int page, string chapter)

    // Signal for requesting export
    signal exportRequested()

    // Panel header
    Rectangle {
        id: header
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: 44
        color: "#fafafa"
        border.color: "#e0e0e0"
        border.width: 1

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 12
            anchors.rightMargin: 12
            spacing: 8

            Label {
                text: qsTr("Annotations")
                font.pixelSize: 14
                font.bold: true
                color: "#333333"
                Layout.fillWidth: true
            }

            Label {
                text: annotationController ? annotationController.annotationCount.toString() : "0"
                font.pixelSize: 12
                color: "#666666"
                padding: 4
                background: Rectangle {
                    radius: 8
                    color: "#e8e8e8"
                }
            }

            Button {
                text: qsTr("Export")
                flat: true
                font.pixelSize: 11
                onClicked: {
                    if (annotationController) {
                        annotationController.exportAnnotations()
                    }
                    root.exportRequested()
                }
            }
        }
    }

    // Annotation list
    ListView {
        id: annotationListView
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        clip: true
        spacing: 1

        model: annotationController ? annotationController.annotationModel : null

        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        // Section headers for grouping by page/chapter
        section.property: "page"
        section.criteria: ViewSection.FullString
        section.delegate: Rectangle {
            width: annotationListView.width
            height: 28
            color: "#f0f0f0"
            border.color: "#e0e0e0"
            border.width: 1

            Label {
                anchors.left: parent.left
                anchors.leftMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                text: {
                    var pageVal = parseInt(section)
                    if (pageVal >= 0) {
                        return qsTr("Page %1").arg(pageVal + 1)
                    }
                    return qsTr("Chapter")
                }
                font.pixelSize: 11
                font.bold: true
                color: "#666666"
            }
        }

        delegate: Rectangle {
            id: annotationDelegate
            width: annotationListView.width
            height: contentColumn.height + 16
            color: delegateMouseArea.containsMouse ? "#f5f8ff" : "transparent"
            border.color: delegateMouseArea.containsMouse ? "#d0d8e8" : "transparent"
            border.width: 1

            ColumnLayout {
                id: contentColumn
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 8
                spacing: 4

                // Header row: type indicator + color + timestamp
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6

                    // Color/type indicator
                    Rectangle {
                        width: 12
                        height: 12
                        radius: 2
                        color: {
                            if (model.annotationColor === "yellow") return "#FFEB3B"
                            if (model.annotationColor === "green") return "#4CAF50"
                            if (model.annotationColor === "blue") return "#2196F3"
                            if (model.annotationColor === "pink") return "#E91E63"
                            if (model.annotationColor === "orange") return "#FF9800"
                            if (model.annotationType === "underline") return "#333333"
                            if (model.annotationType === "note") return "#9C27B0"
                            return "#FFEB3B"
                        }
                        border.color: Qt.darker(color, 1.2)
                        border.width: 1
                    }

                    // Type label
                    Label {
                        text: {
                            if (model.annotationType === "highlight") return qsTr("Highlight")
                            if (model.annotationType === "underline") return qsTr("Underline")
                            if (model.annotationType === "note") return qsTr("Note")
                            if (model.annotationType === "comment") return qsTr("Comment")
                            return model.annotationType
                        }
                        font.pixelSize: 11
                        font.bold: true
                        color: "#555555"
                    }

                    Item { Layout.fillWidth: true }

                    // Timestamp
                    Label {
                        text: {
                            if (!model.createdAt) return ""
                            var d = new Date(model.createdAt)
                            return Qt.formatDateTime(d, "yyyy-MM-dd hh:mm")
                        }
                        font.pixelSize: 10
                        color: "#999999"
                    }

                    // Delete button
                    Button {
                        text: "\u2715"
                        flat: true
                        font.pixelSize: 10
                        implicitWidth: 20
                        implicitHeight: 20
                        onClicked: {
                            if (annotationController) {
                                annotationController.deleteAnnotation(model.annotationId)
                            }
                        }
                        ToolTip.text: qsTr("Delete annotation")
                        ToolTip.visible: hovered
                    }
                }

                // Selected text (quoted)
                Label {
                    Layout.fillWidth: true
                    text: model.selectedText ? "\u201C" + model.selectedText + "\u201D" : ""
                    font.pixelSize: 12
                    font.italic: true
                    color: "#444444"
                    wrapMode: Text.WordWrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                    visible: model.selectedText !== ""
                }

                // Note content
                Label {
                    Layout.fillWidth: true
                    text: model.noteContent || ""
                    font.pixelSize: 12
                    color: "#333333"
                    wrapMode: Text.WordWrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                    visible: model.noteContent !== ""
                }
            }

            MouseArea {
                id: delegateMouseArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                // Prevent capturing clicks on the delete button
                propagateComposedEvents: true

                onClicked: function(mouse) {
                    root.annotationClicked(
                        model.annotationId,
                        model.page,
                        model.chapter
                    )
                }
            }
        }

        // Empty state
        Label {
            anchors.centerIn: parent
            text: qsTr("No annotations yet.\nSelect text to highlight or add notes.")
            font.pixelSize: 13
            color: "#999999"
            horizontalAlignment: Text.AlignHCenter
            visible: annotationListView.count === 0
        }
    }
}
