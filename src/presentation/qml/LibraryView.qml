import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

/**
 * LibraryView.qml - Main library view with grid and list display modes.
 *
 * Displays the user's book collection as either a grid of cover thumbnails
 * or a detailed list with metadata columns. Supports drag-and-drop import
 * from the file manager.
 *
 * Requirements: 1.8, 1.9, 1.10, 14.1
 */
Item {
    id: root

    // Whether to show grid view (true) or list view (false)
    property bool gridMode: true

    // Reference to the library controller (set via context property)
    property var libraryController: null

    // Reference to the book list model from the controller
    property var bookModel: libraryController ? libraryController.bookModel : null

    // Signals for external communication
    signal bookOpened(string bookId)
    signal bookFavoriteToggled(string bookId, bool isFavorite)

    // ------------------------------------------------------------------
    // Toolbar
    // ------------------------------------------------------------------
    LibraryToolbar {
        id: toolbar
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: 48

        gridMode: root.gridMode

        onViewToggled: {
            root.gridMode = !root.gridMode
        }
        onSortChanged: function(criterion) {
            // Forward sort request to controller
            if (root.libraryController) {
                root.libraryController.sortBooks(criterion)
            }
        }
        onFilterChanged: function(filterText) {
            if (root.libraryController) {
                root.libraryController.filterBooks(filterText)
            }
        }
        onImportClicked: {
            fileDialog.open()
        }
    }

    // ------------------------------------------------------------------
    // Content area - switches between grid and list
    // ------------------------------------------------------------------
    StackLayout {
        id: viewStack
        anchors.top: toolbar.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.topMargin: 8

        currentIndex: root.gridMode ? 0 : 1

        // Grid View (cover thumbnails)
        GridView {
            id: gridView
            Layout.fillWidth: true
            Layout.fillHeight: true
            cellWidth: 180
            cellHeight: 260
            clip: true

            model: root.bookModel

            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            delegate: Item {
                width: gridView.cellWidth
                height: gridView.cellHeight

                Rectangle {
                    id: gridCard
                    anchors.fill: parent
                    anchors.margins: 8
                    radius: 6
                    color: mouseAreaGrid.containsMouse ? "#f0f0f0" : "#ffffff"
                    border.color: "#e0e0e0"
                    border.width: 1

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 4

                        // Cover image placeholder or actual image
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 160
                            color: "#e8e8e8"
                            radius: 4

                            Image {
                                anchors.fill: parent
                                source: model.coverImage || ""
                                fillMode: Image.PreserveAspectFit
                                visible: model.coverImage !== ""
                            }

                            // Placeholder icon when no cover
                            Text {
                                anchors.centerIn: parent
                                text: "\uD83D\uDCD6"
                                font.pixelSize: 48
                                visible: !model.coverImage || model.coverImage === ""
                            }

                            // Favorite indicator
                            Text {
                                anchors.top: parent.top
                                anchors.right: parent.right
                                anchors.margins: 4
                                text: model.isFavorite ? "\u2605" : ""
                                font.pixelSize: 18
                                color: "#f5a623"
                            }
                        }

                        // Title
                        Text {
                            Layout.fillWidth: true
                            text: model.title || ""
                            font.pixelSize: 12
                            font.bold: true
                            elide: Text.ElideRight
                            maximumLineCount: 2
                            wrapMode: Text.Wrap
                        }

                        // Author
                        Text {
                            Layout.fillWidth: true
                            text: model.author || ""
                            font.pixelSize: 11
                            color: "#666666"
                            elide: Text.ElideRight
                        }
                    }

                    MouseArea {
                        id: mouseAreaGrid
                        anchors.fill: parent
                        hoverEnabled: true
                        acceptedButtons: Qt.LeftButton | Qt.RightButton

                        onDoubleClicked: {
                            if (root.libraryController) {
                                root.libraryController.openBook(model.bookId)
                                root.bookOpened(model.bookId)
                            }
                        }

                        onClicked: function(mouse) {
                            if (mouse.button === Qt.RightButton) {
                                contextMenu.bookId = model.bookId
                                contextMenu.isFavorite = model.isFavorite
                                contextMenu.popup()
                            }
                        }
                    }
                }
            }

            // Empty state
            Text {
                anchors.centerIn: parent
                text: qsTr("No books in library.\nDrag and drop files here or click Import.")
                font.pixelSize: 14
                color: "#999999"
                horizontalAlignment: Text.AlignHCenter
                visible: gridView.count === 0
            }
        }

        // List View (metadata columns)
        ListView {
            id: listView
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 1

            model: root.bookModel

            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            header: Rectangle {
                width: listView.width
                height: 36
                color: "#f5f5f5"
                border.color: "#e0e0e0"
                border.width: 1

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    spacing: 8

                    Text {
                        Layout.preferredWidth: 280
                        text: qsTr("Title")
                        font.bold: true
                        font.pixelSize: 12
                    }
                    Text {
                        Layout.preferredWidth: 180
                        text: qsTr("Author")
                        font.bold: true
                        font.pixelSize: 12
                    }
                    Text {
                        Layout.preferredWidth: 80
                        text: qsTr("Format")
                        font.bold: true
                        font.pixelSize: 12
                    }
                    Text {
                        Layout.preferredWidth: 80
                        text: qsTr("Pages")
                        font.bold: true
                        font.pixelSize: 12
                    }
                    Text {
                        Layout.preferredWidth: 120
                        text: qsTr("Language")
                        font.bold: true
                        font.pixelSize: 12
                    }
                    Item { Layout.fillWidth: true }
                }
            }

            delegate: Rectangle {
                width: listView.width
                height: 44
                color: mouseAreaList.containsMouse ? "#f8f8f8" : "#ffffff"
                border.color: "#eeeeee"
                border.width: 1

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    spacing: 8

                    // Favorite star + Title
                    RowLayout {
                        Layout.preferredWidth: 280
                        spacing: 4

                        Text {
                            text: model.isFavorite ? "\u2605" : "\u2606"
                            font.pixelSize: 14
                            color: model.isFavorite ? "#f5a623" : "#cccccc"

                            MouseArea {
                                anchors.fill: parent
                                onClicked: {
                                    if (root.libraryController) {
                                        root.libraryController.setFavorite(model.bookId, !model.isFavorite)
                                        root.bookFavoriteToggled(model.bookId, !model.isFavorite)
                                    }
                                }
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            text: model.title || ""
                            font.pixelSize: 13
                            elide: Text.ElideRight
                        }
                    }

                    Text {
                        Layout.preferredWidth: 180
                        text: model.author || ""
                        font.pixelSize: 12
                        color: "#555555"
                        elide: Text.ElideRight
                    }
                    Text {
                        Layout.preferredWidth: 80
                        text: (model.format || "").toUpperCase()
                        font.pixelSize: 12
                        color: "#777777"
                    }
                    Text {
                        Layout.preferredWidth: 80
                        text: model.pageCount > 0 ? model.pageCount.toString() : "-"
                        font.pixelSize: 12
                        color: "#777777"
                    }
                    Text {
                        Layout.preferredWidth: 120
                        text: model.language || ""
                        font.pixelSize: 12
                        color: "#777777"
                        elide: Text.ElideRight
                    }
                    Item { Layout.fillWidth: true }
                }

                MouseArea {
                    id: mouseAreaList
                    anchors.fill: parent
                    hoverEnabled: true
                    acceptedButtons: Qt.LeftButton | Qt.RightButton

                    onDoubleClicked: {
                        if (root.libraryController) {
                            root.libraryController.openBook(model.bookId)
                            root.bookOpened(model.bookId)
                        }
                    }

                    onClicked: function(mouse) {
                        if (mouse.button === Qt.RightButton) {
                            contextMenu.bookId = model.bookId
                            contextMenu.isFavorite = model.isFavorite
                            contextMenu.popup()
                        }
                    }
                }
            }

            // Empty state
            Text {
                anchors.centerIn: parent
                text: qsTr("No books in library.\nDrag and drop files here or click Import.")
                font.pixelSize: 14
                color: "#999999"
                horizontalAlignment: Text.AlignHCenter
                visible: listView.count === 0
            }
        }
    }

    // ------------------------------------------------------------------
    // Drag-and-drop import from file manager
    // ------------------------------------------------------------------
    DropArea {
        anchors.fill: parent
        keys: ["text/uri-list"]

        onEntered: function(drag) {
            dropOverlay.visible = true
            drag.accepted = true
        }

        onExited: {
            dropOverlay.visible = false
        }

        onDropped: function(drop) {
            dropOverlay.visible = false
            if (drop.hasUrls) {
                var filePaths = []
                for (var i = 0; i < drop.urls.length; i++) {
                    var path = drop.urls[i].toString()
                    // Remove file:// or file:/// prefix
                    if (Qt.platform.os === "windows") {
                        path = path.replace(/^file:\/\/\//, "")
                    } else {
                        path = path.replace(/^file:\/\//, "")
                    }
                    path = decodeURIComponent(path)
                    filePaths.push(path)
                }
                if (root.libraryController && filePaths.length > 0) {
                    root.libraryController.importFiles(filePaths)
                }
            }
        }
    }

    // Drop overlay indicator
    Rectangle {
        id: dropOverlay
        anchors.fill: parent
        color: "#4400aaff"
        border.color: "#0088ff"
        border.width: 3
        radius: 8
        visible: false
        z: 100

        Text {
            anchors.centerIn: parent
            text: qsTr("Drop files here to import")
            font.pixelSize: 20
            font.bold: true
            color: "#0066cc"
        }
    }

    // ------------------------------------------------------------------
    // Context Menu
    // ------------------------------------------------------------------
    Menu {
        id: contextMenu

        property string bookId: ""
        property bool isFavorite: false

        MenuItem {
            text: qsTr("Open")
            onTriggered: {
                if (root.libraryController) {
                    root.libraryController.openBook(contextMenu.bookId)
                    root.bookOpened(contextMenu.bookId)
                }
            }
        }
        MenuItem {
            text: contextMenu.isFavorite ? qsTr("Remove from Favorites") : qsTr("Add to Favorites")
            onTriggered: {
                if (root.libraryController) {
                    root.libraryController.setFavorite(contextMenu.bookId, !contextMenu.isFavorite)
                }
            }
        }
        MenuSeparator {}
        MenuItem {
            text: qsTr("Add Tag...")
            onTriggered: {
                tagDialog.bookId = contextMenu.bookId
                tagDialog.open()
            }
        }
    }

    // ------------------------------------------------------------------
    // Tag input dialog
    // ------------------------------------------------------------------
    Dialog {
        id: tagDialog
        title: qsTr("Add Tag")
        anchors.centerIn: parent
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel

        property string bookId: ""

        ColumnLayout {
            spacing: 12
            width: 300

            Label {
                text: qsTr("Enter a tag name:")
            }

            TextField {
                id: tagInput
                Layout.fillWidth: true
                placeholderText: qsTr("Tag name")
            }
        }

        onAccepted: {
            var tag = tagInput.text.trim()
            if (tag.length > 0 && root.libraryController) {
                root.libraryController.addTag(tagDialog.bookId, tag)
            }
            tagInput.text = ""
        }

        onRejected: {
            tagInput.text = ""
        }
    }

    // ------------------------------------------------------------------
    // File dialog for import
    // ------------------------------------------------------------------
    // Note: Uses Qt.labs.platform or Dialogs depending on Qt version
    // This is a placeholder component; actual FileDialog requires
    // import Qt.labs.platform 1.1 or QtQuick.Dialogs
    Loader {
        id: fileDialog
        active: false
        sourceComponent: Component {
            Item {} // Placeholder - actual FileDialog configured at app level
        }
        function open() {
            // In a real app, this triggers the platform file dialog
            // via the controller or a native dialog bridge
            if (root.libraryController) {
                // Controller handles native file dialog via Python
                root.libraryController.showImportDialog()
            }
        }
    }
}
