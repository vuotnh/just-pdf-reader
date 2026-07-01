import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

/**
 * CollectionPanel.qml - Side panel for managing book collections.
 *
 * Allows users to create, rename, and delete collections, and to
 * browse collections to filter the library view.
 *
 * Requirements: 1.4, 1.10, 14.1
 */
Rectangle {
    id: collectionPanel

    // Reference to the library controller (set via context property)
    property var libraryController: null

    // Currently selected collection ID (empty string = all books)
    property string selectedCollectionId: ""

    // Model for collections list
    property var collectionsModel: ListModel {}

    signal collectionSelected(string collectionId, string collectionName)

    color: "#ffffff"
    border.color: "#e0e0e0"
    border.width: 1

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 8
        spacing: 8

        // Header
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Label {
                text: qsTr("Collections")
                font.pixelSize: 14
                font.bold: true
                Layout.fillWidth: true
            }

            Button {
                id: addCollectionButton
                text: "+"
                flat: true
                Layout.preferredWidth: 28
                Layout.preferredHeight: 28

                onClicked: {
                    newCollectionDialog.open()
                }

                ToolTip.visible: hovered
                ToolTip.text: qsTr("Create new collection")
            }
        }

        // Separator
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: "#e8e8e8"
        }

        // "All Books" entry
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 36
            radius: 4
            color: selectedCollectionId === "" ? "#e3f2fd" : (allBooksMouseArea.containsMouse ? "#f5f5f5" : "transparent")

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                spacing: 8

                Text {
                    text: "\uD83D\uDCDA"
                    font.pixelSize: 16
                }

                Label {
                    text: qsTr("All Books")
                    font.pixelSize: 13
                    font.bold: selectedCollectionId === ""
                    Layout.fillWidth: true
                }
            }

            MouseArea {
                id: allBooksMouseArea
                anchors.fill: parent
                hoverEnabled: true
                onClicked: {
                    collectionPanel.selectedCollectionId = ""
                    collectionPanel.collectionSelected("", "All Books")
                }
            }
        }

        // "Favorites" entry
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 36
            radius: 4
            color: selectedCollectionId === "__favorites__" ? "#e3f2fd" : (favoritesMouseArea.containsMouse ? "#f5f5f5" : "transparent")

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                spacing: 8

                Text {
                    text: "\u2605"
                    font.pixelSize: 16
                    color: "#f5a623"
                }

                Label {
                    text: qsTr("Favorites")
                    font.pixelSize: 13
                    font.bold: selectedCollectionId === "__favorites__"
                    Layout.fillWidth: true
                }
            }

            MouseArea {
                id: favoritesMouseArea
                anchors.fill: parent
                hoverEnabled: true
                onClicked: {
                    collectionPanel.selectedCollectionId = "__favorites__"
                    collectionPanel.collectionSelected("__favorites__", "Favorites")
                }
            }
        }

        // Separator
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: "#e8e8e8"
        }

        // Collections list
        ListView {
            id: collectionsList
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 2

            model: collectionPanel.collectionsModel

            delegate: Rectangle {
                width: collectionsList.width
                height: 36
                radius: 4
                color: collectionPanel.selectedCollectionId === model.collectionId
                       ? "#e3f2fd"
                       : (collectionMouseArea.containsMouse ? "#f5f5f5" : "transparent")

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 8
                    anchors.rightMargin: 8
                    spacing: 8

                    Text {
                        text: "\uD83D\uDCC1"
                        font.pixelSize: 14
                    }

                    Label {
                        text: model.name || ""
                        font.pixelSize: 13
                        font.bold: collectionPanel.selectedCollectionId === model.collectionId
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }

                    // Delete button (visible on hover)
                    Button {
                        text: "\u2715"
                        flat: true
                        visible: collectionMouseArea.containsMouse
                        Layout.preferredWidth: 24
                        Layout.preferredHeight: 24
                        font.pixelSize: 10

                        onClicked: {
                            deleteConfirmDialog.collectionId = model.collectionId
                            deleteConfirmDialog.collectionName = model.name
                            deleteConfirmDialog.open()
                        }
                    }
                }

                MouseArea {
                    id: collectionMouseArea
                    anchors.fill: parent
                    hoverEnabled: true
                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                    // Prevent mouse events from being eaten by child buttons
                    propagateComposedEvents: true

                    onClicked: function(mouse) {
                        if (mouse.button === Qt.LeftButton) {
                            collectionPanel.selectedCollectionId = model.collectionId
                            collectionPanel.collectionSelected(model.collectionId, model.name)
                        }
                    }
                }
            }

            // Empty state for collections
            Text {
                anchors.centerIn: parent
                text: qsTr("No collections yet.\nClick + to create one.")
                font.pixelSize: 12
                color: "#999999"
                horizontalAlignment: Text.AlignHCenter
                visible: collectionsList.count === 0
            }
        }
    }

    // ------------------------------------------------------------------
    // New Collection Dialog
    // ------------------------------------------------------------------
    Dialog {
        id: newCollectionDialog
        title: qsTr("New Collection")
        anchors.centerIn: parent
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel

        ColumnLayout {
            spacing: 12
            width: 300

            Label {
                text: qsTr("Collection name:")
            }

            TextField {
                id: collectionNameInput
                Layout.fillWidth: true
                placeholderText: qsTr("Enter collection name")
                focus: true
            }
        }

        onAccepted: {
            var name = collectionNameInput.text.trim()
            if (name.length > 0 && collectionPanel.libraryController) {
                var collectionId = collectionPanel.libraryController.createCollection(name)
                collectionPanel.collectionsModel.append({
                    "collectionId": collectionId,
                    "name": name
                })
            }
            collectionNameInput.text = ""
        }

        onRejected: {
            collectionNameInput.text = ""
        }
    }

    // ------------------------------------------------------------------
    // Delete Collection Confirmation Dialog
    // ------------------------------------------------------------------
    Dialog {
        id: deleteConfirmDialog
        title: qsTr("Delete Collection")
        anchors.centerIn: parent
        modal: true
        standardButtons: Dialog.Yes | Dialog.No

        property string collectionId: ""
        property string collectionName: ""

        Label {
            text: qsTr("Are you sure you want to delete the collection \"%1\"?\nBooks will not be removed from the library.").arg(deleteConfirmDialog.collectionName)
            wrapMode: Text.Wrap
            width: 300
        }

        onAccepted: {
            // Remove from model
            for (var i = 0; i < collectionPanel.collectionsModel.count; i++) {
                if (collectionPanel.collectionsModel.get(i).collectionId === deleteConfirmDialog.collectionId) {
                    collectionPanel.collectionsModel.remove(i)
                    break
                }
            }
            // Reset selection if deleted collection was selected
            if (collectionPanel.selectedCollectionId === deleteConfirmDialog.collectionId) {
                collectionPanel.selectedCollectionId = ""
                collectionPanel.collectionSelected("", "All Books")
            }
        }
    }
}
