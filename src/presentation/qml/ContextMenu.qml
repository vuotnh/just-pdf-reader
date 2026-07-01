import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

/**
 * ContextMenu.qml - Context menu for text selection actions.
 *
 * Displays a floating menu near the text selection with actions:
 * highlight (with color palette), underline, add note, copy, dictionary lookup.
 *
 * Requirements: 2.8, 3.7, 5.2, 5.3
 */
Popup {
    id: root

    // Reference to the annotation controller
    property var annotationController: null

    // The selected text to operate on
    property string selectedText: ""

    // Signals for actions that require external handling
    signal copyRequested(string text)
    signal dictionaryLookupRequested(string text)
    signal noteDialogRequested()

    width: contentLayout.width + 16
    height: contentLayout.height + 16
    modal: false
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    padding: 8

    background: Rectangle {
        color: "#ffffff"
        radius: 8
        border.color: "#d0d0d0"
        border.width: 1
        layer.enabled: true
    }

    onClosed: {
        colorPalette.visible = false
        if (annotationController) {
            annotationController.dismissContextMenu()
        }
    }

    ColumnLayout {
        id: contentLayout
        spacing: 4

        // ------------------------------------------------------------------
        // Main action buttons
        // ------------------------------------------------------------------
        RowLayout {
            spacing: 2

            // Highlight button with color indicator
            Button {
                id: highlightBtn
                text: "\uD83D\uDD8D"  // Crayon emoji as icon placeholder
                flat: true
                implicitWidth: 36
                implicitHeight: 36
                ToolTip.text: qsTr("Highlight")
                ToolTip.visible: hovered

                onClicked: {
                    colorPalette.visible = !colorPalette.visible
                }
            }

            // Underline button
            Button {
                text: "U\u0332"  // Underlined U character
                flat: true
                font.pixelSize: 14
                font.underline: true
                implicitWidth: 36
                implicitHeight: 36
                ToolTip.text: qsTr("Underline")
                ToolTip.visible: hovered

                onClicked: {
                    if (annotationController) {
                        annotationController.underlineSelection()
                    }
                    root.close()
                }
            }

            // Add note button
            Button {
                text: "\uD83D\uDCDD"  // Memo emoji as icon placeholder
                flat: true
                implicitWidth: 36
                implicitHeight: 36
                ToolTip.text: qsTr("Add Note")
                ToolTip.visible: hovered

                onClicked: {
                    root.noteDialogRequested()
                    root.close()
                }
            }

            // Separator
            Rectangle { width: 1; height: 24; color: "#e0e0e0" }

            // Copy button
            Button {
                text: "\uD83D\uDCCB"  // Clipboard emoji as icon placeholder
                flat: true
                implicitWidth: 36
                implicitHeight: 36
                ToolTip.text: qsTr("Copy")
                ToolTip.visible: hovered

                onClicked: {
                    root.copyRequested(root.selectedText)
                    root.close()
                }
            }

            // Dictionary lookup button
            Button {
                text: "\uD83D\uDCD6"  // Open book emoji as icon placeholder
                flat: true
                implicitWidth: 36
                implicitHeight: 36
                ToolTip.text: qsTr("Dictionary")
                ToolTip.visible: hovered

                onClicked: {
                    root.dictionaryLookupRequested(root.selectedText)
                    root.close()
                }
            }
        }

        // ------------------------------------------------------------------
        // Color palette (shown when highlight is clicked)
        // ------------------------------------------------------------------
        RowLayout {
            id: colorPalette
            visible: false
            spacing: 4
            Layout.alignment: Qt.AlignHCenter

            Repeater {
                model: [
                    { name: "yellow", color: "#FFEB3B" },
                    { name: "green", color: "#4CAF50" },
                    { name: "blue", color: "#2196F3" },
                    { name: "pink", color: "#E91E63" },
                    { name: "orange", color: "#FF9800" }
                ]

                delegate: Rectangle {
                    width: 24
                    height: 24
                    radius: 12
                    color: modelData.color
                    border.color: colorMouseArea.containsMouse
                        ? Qt.darker(modelData.color, 1.4)
                        : Qt.darker(modelData.color, 1.1)
                    border.width: colorMouseArea.containsMouse ? 2 : 1

                    MouseArea {
                        id: colorMouseArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor

                        onClicked: {
                            if (annotationController) {
                                annotationController.highlightSelection(modelData.name)
                            }
                            root.close()
                        }
                    }

                    ToolTip.text: modelData.name.charAt(0).toUpperCase() + modelData.name.slice(1)
                    ToolTip.visible: colorMouseArea.containsMouse
                }
            }
        }
    }
}
