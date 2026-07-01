import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

/**
 * StatusBar.qml - Application status bar with reading progress and info.
 *
 * Displays at the bottom of the main window with:
 *   - Current reading progress (page/chapter and percentage)
 *   - Book title and format indicator
 *   - Word count / estimated reading time
 *   - General status messages
 *
 * Requirements: 14.1
 */
ToolBar {
    id: statusBar

    height: 28

    // Reading progress (0.0 to 1.0)
    property real readingProgress: 0.0

    // Current page/chapter display text
    property string positionText: ""

    // Current book title
    property string bookTitle: ""

    // Current book format (PDF, EPUB, AZW3)
    property string bookFormat: ""

    // General status message
    property string statusMessage: qsTr("Ready")

    // Word count for current book
    property int wordCount: 0

    background: Rectangle {
        color: "#f5f5f5"
        border.color: "#e0e0e0"
        border.width: 1
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        spacing: 12

        // ------------------------------------------------------------------
        // Left: Status message
        // ------------------------------------------------------------------
        Label {
            id: statusLabel
            text: statusBar.statusMessage
            font.pixelSize: 11
            color: "#666666"
            elide: Text.ElideRight
            Layout.preferredWidth: 200
        }

        // Separator
        Rectangle {
            Layout.preferredWidth: 1
            Layout.preferredHeight: 16
            color: "#dddddd"
            visible: statusBar.bookTitle !== ""
        }

        // ------------------------------------------------------------------
        // Center: Book info
        // ------------------------------------------------------------------
        Label {
            text: statusBar.bookTitle
            font.pixelSize: 11
            color: "#444444"
            elide: Text.ElideRight
            Layout.fillWidth: true
            visible: statusBar.bookTitle !== ""
        }

        // Format badge
        Rectangle {
            width: formatLabel.width + 8
            height: 16
            radius: 3
            color: {
                if (statusBar.bookFormat === "PDF") return "#e3f2fd"
                if (statusBar.bookFormat === "EPUB") return "#e8f5e9"
                if (statusBar.bookFormat === "AZW3") return "#fff3e0"
                return "transparent"
            }
            border.color: {
                if (statusBar.bookFormat === "PDF") return "#90caf9"
                if (statusBar.bookFormat === "EPUB") return "#a5d6a7"
                if (statusBar.bookFormat === "AZW3") return "#ffcc80"
                return "transparent"
            }
            border.width: statusBar.bookFormat !== "" ? 1 : 0
            visible: statusBar.bookFormat !== ""

            Label {
                id: formatLabel
                anchors.centerIn: parent
                text: statusBar.bookFormat
                font.pixelSize: 9
                font.bold: true
                color: {
                    if (statusBar.bookFormat === "PDF") return "#1565c0"
                    if (statusBar.bookFormat === "EPUB") return "#2e7d32"
                    if (statusBar.bookFormat === "AZW3") return "#e65100"
                    return "#666666"
                }
            }
        }

        // Spacer
        Item {
            Layout.fillWidth: true
            visible: statusBar.bookTitle === ""
        }

        // ------------------------------------------------------------------
        // Right: Reading progress
        // ------------------------------------------------------------------

        // Separator
        Rectangle {
            Layout.preferredWidth: 1
            Layout.preferredHeight: 16
            color: "#dddddd"
            visible: statusBar.positionText !== ""
        }

        // Position text (e.g., "Page 42 / 300" or "Chapter 5")
        Label {
            text: statusBar.positionText
            font.pixelSize: 11
            color: "#555555"
            visible: statusBar.positionText !== ""
        }

        // Progress bar
        ProgressBar {
            id: progressBar
            Layout.preferredWidth: 100
            Layout.preferredHeight: 8
            from: 0.0
            to: 1.0
            value: statusBar.readingProgress
            visible: statusBar.readingProgress > 0

            background: Rectangle {
                implicitWidth: 100
                implicitHeight: 6
                radius: 3
                color: "#e0e0e0"
            }

            contentItem: Item {
                implicitWidth: 100
                implicitHeight: 6

                Rectangle {
                    width: progressBar.visualPosition * parent.width
                    height: parent.height
                    radius: 3
                    color: "#1a73e8"
                }
            }
        }

        // Percentage text
        Label {
            text: statusBar.readingProgress > 0
                ? Math.round(statusBar.readingProgress * 100) + "%"
                : ""
            font.pixelSize: 11
            color: "#555555"
            visible: statusBar.readingProgress > 0
        }
    }
}
