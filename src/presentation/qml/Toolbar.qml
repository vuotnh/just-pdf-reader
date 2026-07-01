import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

/**
 * Toolbar.qml - Primary application toolbar with action buttons.
 *
 * Provides quick access to primary actions: open book, toggle panels,
 * navigation, search, bookmarks, and settings. Sits at the top of
 * the main window.
 *
 * Requirements: 14.1, 14.6
 */
ToolBar {
    id: toolbar

    // Panel visibility state (bound from MainWindow)
    property bool navPanelVisible: true
    property bool sidePanelVisible: true

    // Signals for panel toggling
    signal toggleNavPanel()
    signal toggleSidePanel()

    // Signals for primary actions
    signal openBookRequested()
    signal searchRequested()
    signal bookmarkRequested()
    signal settingsRequested()

    height: 44

    background: Rectangle {
        color: "#ffffff"
        border.color: "#e0e0e0"
        border.width: 1
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 8
        anchors.rightMargin: 8
        spacing: 4

        // ------------------------------------------------------------------
        // Left section: Navigation panel toggle + Open book
        // ------------------------------------------------------------------

        // Toggle Navigation Panel
        ToolButton {
            id: navPanelToggle
            text: "\u2630"
            font.pixelSize: 16
            highlighted: toolbar.navPanelVisible
            implicitWidth: 36
            implicitHeight: 36

            onClicked: toolbar.toggleNavPanel()

            ToolTip.visible: hovered
            ToolTip.text: toolbar.navPanelVisible
                ? qsTr("Hide Navigation Panel")
                : qsTr("Show Navigation Panel")
        }

        // Separator
        Rectangle {
            Layout.preferredWidth: 1
            Layout.preferredHeight: 28
            color: "#e0e0e0"
        }

        // Open Book
        ToolButton {
            id: openBookBtn
            text: "\uD83D\uDCC2"
            font.pixelSize: 14
            implicitWidth: 36
            implicitHeight: 36

            onClicked: toolbar.openBookRequested()

            ToolTip.visible: hovered
            ToolTip.text: qsTr("Open Book (Ctrl+O)")
        }

        // Add Bookmark
        ToolButton {
            id: bookmarkBtn
            text: "\uD83D\uDD16"
            font.pixelSize: 14
            implicitWidth: 36
            implicitHeight: 36

            onClicked: toolbar.bookmarkRequested()

            ToolTip.visible: hovered
            ToolTip.text: qsTr("Add Bookmark (Ctrl+B)")
        }

        // ------------------------------------------------------------------
        // Center section: Navigation controls
        // ------------------------------------------------------------------

        Item { Layout.fillWidth: true }

        // Previous page
        ToolButton {
            id: prevPageBtn
            text: "\u25C0"
            font.pixelSize: 12
            implicitWidth: 32
            implicitHeight: 32

            ToolTip.visible: hovered
            ToolTip.text: qsTr("Previous Page")
        }

        // Page indicator
        Label {
            id: pageIndicator
            text: qsTr("Page 1")
            font.pixelSize: 12
            color: "#555555"
            horizontalAlignment: Text.AlignHCenter
            Layout.preferredWidth: 80
        }

        // Next page
        ToolButton {
            id: nextPageBtn
            text: "\u25B6"
            font.pixelSize: 12
            implicitWidth: 32
            implicitHeight: 32

            ToolTip.visible: hovered
            ToolTip.text: qsTr("Next Page")
        }

        Item { Layout.fillWidth: true }

        // ------------------------------------------------------------------
        // Right section: Search, Settings, Side panel toggle
        // ------------------------------------------------------------------

        // Search
        ToolButton {
            id: searchBtn
            text: "\uD83D\uDD0D"
            font.pixelSize: 14
            implicitWidth: 36
            implicitHeight: 36

            onClicked: toolbar.searchRequested()

            ToolTip.visible: hovered
            ToolTip.text: qsTr("Search (Ctrl+F)")
        }

        // Settings
        ToolButton {
            id: settingsBtn
            text: "\u2699"
            font.pixelSize: 16
            implicitWidth: 36
            implicitHeight: 36

            onClicked: toolbar.settingsRequested()

            ToolTip.visible: hovered
            ToolTip.text: qsTr("Settings")
        }

        // Separator
        Rectangle {
            Layout.preferredWidth: 1
            Layout.preferredHeight: 28
            color: "#e0e0e0"
        }

        // Toggle Side Panel
        ToolButton {
            id: sidePanelToggle
            text: "\u2261"
            font.pixelSize: 16
            highlighted: toolbar.sidePanelVisible
            implicitWidth: 36
            implicitHeight: 36

            onClicked: toolbar.toggleSidePanel()

            ToolTip.visible: hovered
            ToolTip.text: toolbar.sidePanelVisible
                ? qsTr("Hide Side Panel")
                : qsTr("Show Side Panel")
        }
    }
}
