import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtWebEngine 1.10

/**
 * EPUBReaderView.qml - EPUB document reader with QWebEngineView and controls.
 *
 * Renders EPUB HTML content via QWebEngineView, supports chapter navigation,
 * font/theme customization, view mode switching (paginated/continuous),
 * text search with match navigation, and bookmarks.
 *
 * Requirements: 3.1–3.10, 14.1
 */
Item {
    id: root

    // Reference to the EPUB reader controller (set via context property)
    property var epubController: null

    // Signals for external communication
    signal chapterNavigated(int chapterIndex)
    signal textSelected(string selectedText, real x, real y)
    signal bookmarkRequested()

    // ------------------------------------------------------------------
    // Toolbar with navigation and controls
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

            // Chapter navigation
            Button {
                text: "\u25C0"
                flat: true
                enabled: epubController && epubController.currentChapter > 0
                onClicked: {
                    if (epubController) {
                        epubController.previousChapter()
                    }
                }
                ToolTip.text: qsTr("Previous Chapter")
                ToolTip.visible: hovered
            }

            Label {
                text: epubController
                    ? qsTr("Chapter %1 / %2").arg(epubController.currentChapter + 1).arg(epubController.chapterCount)
                    : qsTr("No document")
                font.pixelSize: 13
            }

            Button {
                text: "\u25B6"
                flat: true
                enabled: epubController && epubController.currentChapter < epubController.chapterCount - 1
                onClicked: {
                    if (epubController) {
                        epubController.nextChapter()
                    }
                }
                ToolTip.text: qsTr("Next Chapter")
                ToolTip.visible: hovered
            }

            // Separator
            Rectangle { width: 1; height: 28; color: "#d0d0d0" }

            // View mode toggle
            Button {
                text: epubController && epubController.viewMode === "paginated"
                    ? qsTr("Scroll")
                    : qsTr("Paginated")
                flat: true
                font.pixelSize: 11
                onClicked: {
                    if (epubController) {
                        var newMode = epubController.viewMode === "paginated"
                            ? "continuous_scroll" : "paginated"
                        epubController.setPageMode(newMode)
                    }
                }
                ToolTip.text: qsTr("Toggle view mode")
                ToolTip.visible: hovered
            }

            // Separator
            Rectangle { width: 1; height: 28; color: "#d0d0d0" }

            // Theme toggle (dark/light)
            Button {
                text: epubController && epubController.darkMode ? "\u2600" : "\u263D"
                flat: true
                font.pixelSize: 16
                onClicked: {
                    if (epubController) {
                        epubController.setTheme(!epubController.darkMode)
                    }
                }
                ToolTip.text: epubController && epubController.darkMode
                    ? qsTr("Switch to Light Mode")
                    : qsTr("Switch to Dark Mode")
                ToolTip.visible: hovered
            }

            // Settings button (opens ReaderSettings panel)
            Button {
                text: "\u2699"
                flat: true
                font.pixelSize: 16
                onClicked: settingsPanel.visible = !settingsPanel.visible
                ToolTip.text: qsTr("Reader Settings")
                ToolTip.visible: hovered
            }

            // Bookmark button
            Button {
                text: "\uD83D\uDD16"
                flat: true
                font.pixelSize: 14
                onClicked: {
                    if (epubController) {
                        epubController.addBookmark("")
                        root.bookmarkRequested()
                    }
                }
                ToolTip.text: qsTr("Add Bookmark")
                ToolTip.visible: hovered
            }

            Item { Layout.fillWidth: true }

            // Search controls
            TextField {
                id: searchField
                Layout.preferredWidth: 200
                placeholderText: qsTr("Search...")
                font.pixelSize: 12

                onAccepted: {
                    if (epubController) {
                        epubController.search(text)
                    }
                }
            }

            Button {
                text: "\u25B2"
                flat: true
                enabled: epubController && epubController.searchMatchCount > 0
                onClicked: {
                    if (epubController) {
                        epubController.prevMatch()
                    }
                }
                ToolTip.text: qsTr("Previous match")
                ToolTip.visible: hovered
            }

            Button {
                text: "\u25BC"
                flat: true
                enabled: epubController && epubController.searchMatchCount > 0
                onClicked: {
                    if (epubController) {
                        epubController.nextMatch()
                    }
                }
                ToolTip.text: qsTr("Next match")
                ToolTip.visible: hovered
            }

            Label {
                text: epubController && epubController.searchMatchCount > 0
                    ? (epubController.currentMatchIndex + 1) + "/" + epubController.searchMatchCount
                    : ""
                font.pixelSize: 11
                color: "#666666"
            }
        }
    }

    // ------------------------------------------------------------------
    // Main content area with WebEngineView
    // ------------------------------------------------------------------
    WebEngineView {
        id: webView
        anchors.top: toolbar.bottom
        anchors.left: parent.left
        anchors.right: settingsPanel.visible ? settingsPanel.left : parent.right
        anchors.bottom: parent.bottom

        // Load HTML content when contentReady signal fires
        Connections {
            target: epubController
            function onContentReady(htmlContent) {
                webView.loadHtml(htmlContent)
            }
            function onChapterChanged(chapterIndex) {
                root.chapterNavigated(chapterIndex)
            }
        }
    }

    // ------------------------------------------------------------------
    // Reader Settings panel (right side, toggleable)
    // ------------------------------------------------------------------
    ReaderSettings {
        id: settingsPanel
        visible: false
        anchors.top: toolbar.bottom
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        width: 280

        epubController: root.epubController
    }

    // ------------------------------------------------------------------
    // Viewport resize tracking
    // ------------------------------------------------------------------
    onWidthChanged: {
        if (epubController) {
            epubController.setViewport(webView.width, webView.height)
        }
    }
    onHeightChanged: {
        if (epubController) {
            epubController.setViewport(webView.width, webView.height)
        }
    }

    // ------------------------------------------------------------------
    // Keyboard navigation
    // ------------------------------------------------------------------
    Keys.onLeftPressed: {
        if (epubController && epubController.currentChapter > 0) {
            epubController.previousChapter()
        }
    }
    Keys.onRightPressed: {
        if (epubController && epubController.currentChapter < epubController.chapterCount - 1) {
            epubController.nextChapter()
        }
    }
    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_F && event.modifiers & Qt.ControlModifier) {
            searchField.forceActiveFocus()
            event.accepted = true
        } else if (event.key === Qt.Key_B && event.modifiers & Qt.ControlModifier) {
            if (epubController) epubController.addBookmark("")
            event.accepted = true
        } else if (event.key === Qt.Key_D && event.modifiers & Qt.ControlModifier) {
            if (epubController) epubController.setTheme(!epubController.darkMode)
            event.accepted = true
        }
    }
}
