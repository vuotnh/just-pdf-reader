import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

/**
 * LibraryToolbar.qml - Toolbar for library view with sort, filter,
 * view-toggle, and import controls.
 *
 * Requirements: 1.8, 1.9, 1.10, 14.1
 */
Rectangle {
    id: toolbar

    property bool gridMode: true

    signal viewToggled()
    signal sortChanged(string criterion)
    signal filterChanged(string filterText)
    signal importClicked()

    color: "#fafafa"
    border.color: "#e0e0e0"
    border.width: 1

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        spacing: 8

        // Sort combo box
        Label {
            text: qsTr("Sort:")
            font.pixelSize: 12
            color: "#555555"
        }

        ComboBox {
            id: sortCombo
            Layout.preferredWidth: 140
            model: [
                qsTr("Title"),
                qsTr("Author"),
                qsTr("Date Added"),
                qsTr("Last Read"),
                qsTr("File Size")
            ]

            // Map display names to criterion identifiers
            property var criterionMap: [
                "title", "author", "date_added", "last_read", "file_size"
            ]

            onCurrentIndexChanged: {
                toolbar.sortChanged(criterionMap[currentIndex])
            }
        }

        // Separator
        Rectangle {
            Layout.preferredWidth: 1
            Layout.preferredHeight: 28
            color: "#dddddd"
        }

        // Filter input
        Label {
            text: qsTr("Filter:")
            font.pixelSize: 12
            color: "#555555"
        }

        TextField {
            id: filterInput
            Layout.preferredWidth: 180
            placeholderText: qsTr("Search by tag or collection...")
            font.pixelSize: 12

            onTextChanged: {
                filterDebounce.restart()
            }
        }

        // Debounce timer for filter input
        Timer {
            id: filterDebounce
            interval: 300
            repeat: false
            onTriggered: {
                toolbar.filterChanged(filterInput.text.trim())
            }
        }

        // Clear filter button
        Button {
            text: "\u2715"
            flat: true
            visible: filterInput.text.length > 0
            Layout.preferredWidth: 28
            Layout.preferredHeight: 28

            onClicked: {
                filterInput.text = ""
                toolbar.filterChanged("")
            }

            ToolTip.visible: hovered
            ToolTip.text: qsTr("Clear filter")
        }

        // Spacer
        Item { Layout.fillWidth: true }

        // Separator
        Rectangle {
            Layout.preferredWidth: 1
            Layout.preferredHeight: 28
            color: "#dddddd"
        }

        // View toggle buttons
        Button {
            id: gridButton
            icon.name: "view-grid"
            text: "\u25A6"
            flat: true
            highlighted: toolbar.gridMode
            Layout.preferredWidth: 36
            Layout.preferredHeight: 36

            onClicked: {
                if (!toolbar.gridMode) {
                    toolbar.viewToggled()
                }
            }

            ToolTip.visible: hovered
            ToolTip.text: qsTr("Grid view")
        }

        Button {
            id: listButton
            icon.name: "view-list"
            text: "\u2630"
            flat: true
            highlighted: !toolbar.gridMode
            Layout.preferredWidth: 36
            Layout.preferredHeight: 36

            onClicked: {
                if (toolbar.gridMode) {
                    toolbar.viewToggled()
                }
            }

            ToolTip.visible: hovered
            ToolTip.text: qsTr("List view")
        }

        // Separator
        Rectangle {
            Layout.preferredWidth: 1
            Layout.preferredHeight: 28
            color: "#dddddd"
        }

        // Import button
        Button {
            id: importButton
            text: qsTr("Import")
            icon.name: "document-import"
            Layout.preferredHeight: 36

            onClicked: {
                toolbar.importClicked()
            }

            ToolTip.visible: hovered
            ToolTip.text: qsTr("Import books from files or folder")
        }
    }
}
