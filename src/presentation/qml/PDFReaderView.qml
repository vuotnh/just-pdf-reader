import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

/**
 * PDFReaderView.qml - PDF document reader with page display, zoom, and search.
 *
 * Displays rendered PDF pages using the image provider, supports zoom controls,
 * page navigation, view mode switching (single/continuous), and text search
 * with match navigation.
 *
 * Requirements: 2.1–2.6, 14.1
 */
Item {
    id: root

    // Reference to the PDF reader controller (set via context property)
    property var pdfController: null

    // Signals for external communication
    signal pageNavigated(int pageNumber)
    signal textSelected(string selectedText, real x, real y)

    // ------------------------------------------------------------------
    // Toolbar with zoom and navigation controls
    // ------------------------------------------------------------------
    Rectangle {
        id: toolbar
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: 44
        color: "#f5f5f5"
        border.color: "#e0e0e0"
        border.width: 1

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 8
            anchors.rightMargin: 8
            spacing: 8

            // Page navigation
            Button {
                text: "\u25C0"
                flat: true
                enabled: pdfController && pdfController.currentPage > 0
                onClicked: {
                    if (pdfController) {
                        pdfController.goToPage(pdfController.currentPage - 1)
                    }
                }
            }

            Label {
                text: pdfController
                    ? (pdfController.currentPage + 1) + " / " + pdfController.pageCount
                    : "0 / 0"
                font.pixelSize: 13
            }

            Button {
                text: "\u25B6"
                flat: true
                enabled: pdfController && pdfController.currentPage < pdfController.pageCount - 1
                onClicked: {
                    if (pdfController) {
                        pdfController.goToPage(pdfController.currentPage + 1)
                    }
                }
            }

            // Separator
            Rectangle { width: 1; height: 28; color: "#d0d0d0" }

            // Zoom controls
            Button {
                text: "\u2212"
                flat: true
                onClicked: {
                    if (pdfController) {
                        pdfController.setZoom(pdfController.zoomLevel - 0.1)
                    }
                }
            }

            Label {
                text: pdfController ? Math.round(pdfController.zoomLevel * 100) + "%" : "100%"
                font.pixelSize: 13
                Layout.preferredWidth: 50
                horizontalAlignment: Text.AlignHCenter
            }

            Button {
                text: "+"
                flat: true
                onClicked: {
                    if (pdfController) {
                        pdfController.setZoom(pdfController.zoomLevel + 0.1)
                    }
                }
            }

            Button {
                text: qsTr("Fit Width")
                flat: true
                font.pixelSize: 11
                onClicked: {
                    if (pdfController) {
                        pdfController.zoomFitWidth()
                    }
                }
            }

            Button {
                text: qsTr("Fit Page")
                flat: true
                font.pixelSize: 11
                onClicked: {
                    if (pdfController) {
                        pdfController.zoomFitPage()
                    }
                }
            }

            // Separator
            Rectangle { width: 1; height: 28; color: "#d0d0d0" }

            // View mode toggle
            Button {
                text: pdfController && pdfController.viewMode === "single_page"
                    ? qsTr("Continuous")
                    : qsTr("Single Page")
                flat: true
                font.pixelSize: 11
                onClicked: {
                    if (pdfController) {
                        var newMode = pdfController.viewMode === "single_page"
                            ? "continuous_scroll" : "single_page"
                        pdfController.setPageMode(newMode)
                    }
                }
            }

            Item { Layout.fillWidth: true }

            // Search controls
            TextField {
                id: searchField
                Layout.preferredWidth: 200
                placeholderText: qsTr("Search...")
                font.pixelSize: 12

                onAccepted: {
                    if (pdfController) {
                        pdfController.search(text)
                    }
                }
            }

            Button {
                text: "\u25B2"
                flat: true
                enabled: pdfController && pdfController.searchMatchCount > 0
                onClicked: {
                    if (pdfController) {
                        pdfController.prevMatch()
                    }
                }
                ToolTip.text: qsTr("Previous match")
                ToolTip.visible: hovered
            }

            Button {
                text: "\u25BC"
                flat: true
                enabled: pdfController && pdfController.searchMatchCount > 0
                onClicked: {
                    if (pdfController) {
                        pdfController.nextMatch()
                    }
                }
                ToolTip.text: qsTr("Next match")
                ToolTip.visible: hovered
            }

            Label {
                text: pdfController && pdfController.searchMatchCount > 0
                    ? (pdfController.currentMatchIndex + 1) + "/" + pdfController.searchMatchCount
                    : ""
                font.pixelSize: 11
                color: "#666666"
            }
        }
    }

    // ------------------------------------------------------------------
    // Page display area
    // ------------------------------------------------------------------
    Flickable {
        id: pageFlickable
        anchors.top: toolbar.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        clip: true
        contentWidth: pageImage.width
        contentHeight: pageImage.height
        boundsBehavior: Flickable.StopAtBounds

        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AsNeeded
        }
        ScrollBar.horizontal: ScrollBar {
            policy: ScrollBar.AsNeeded
        }

        // Single page image rendered by the image provider
        Image {
            id: pageImage
            anchors.horizontalCenter: parent.horizontalCenter
            cache: false
            source: pdfController && pdfController.pageCount > 0
                ? "image://pdfpage/" + pdfController.currentPage
                : ""
            fillMode: Image.Pad

            // Trigger reload when zoom or page changes
            property int watchPage: pdfController ? pdfController.currentPage : -1
            property real watchZoom: pdfController ? pdfController.zoomLevel : 1.0

            onWatchPageChanged: {
                // Force image reload by toggling source
                var src = source
                source = ""
                source = "image://pdfpage/" + watchPage
                root.pageNavigated(watchPage)
            }

            onWatchZoomChanged: {
                if (pdfController && pdfController.pageCount > 0) {
                    source = ""
                    source = "image://pdfpage/" + pdfController.currentPage
                }
            }
        }

        // Mouse interaction for text selection
        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            propagateComposedEvents: true

            onPressed: function(mouse) {
                mouse.accepted = false
            }
        }
    }

    // ------------------------------------------------------------------
    // Viewport resize tracking
    // ------------------------------------------------------------------
    onWidthChanged: {
        if (pdfController) {
            pdfController.setViewport(pageFlickable.width, pageFlickable.height)
        }
    }
    onHeightChanged: {
        if (pdfController) {
            pdfController.setViewport(pageFlickable.width, pageFlickable.height)
        }
    }

    // ------------------------------------------------------------------
    // Keyboard navigation
    // ------------------------------------------------------------------
    Keys.onLeftPressed: {
        if (pdfController && pdfController.currentPage > 0) {
            pdfController.goToPage(pdfController.currentPage - 1)
        }
    }
    Keys.onRightPressed: {
        if (pdfController && pdfController.currentPage < pdfController.pageCount - 1) {
            pdfController.goToPage(pdfController.currentPage + 1)
        }
    }
    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Plus && event.modifiers & Qt.ControlModifier) {
            if (pdfController) pdfController.setZoom(pdfController.zoomLevel + 0.1)
            event.accepted = true
        } else if (event.key === Qt.Key_Minus && event.modifiers & Qt.ControlModifier) {
            if (pdfController) pdfController.setZoom(pdfController.zoomLevel - 0.1)
            event.accepted = true
        } else if (event.key === Qt.Key_F && event.modifiers & Qt.ControlModifier) {
            searchField.forceActiveFocus()
            event.accepted = true
        }
    }
}
