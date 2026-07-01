import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

/**
 * ReaderSettings.qml - Font and theme configuration panel for the EPUB reader.
 *
 * Provides controls for:
 * - Font family selection
 * - Font size adjustment (8–48pt range)
 * - Line height/spacing adjustment
 * - Dark/Light theme toggle
 * - View mode selection (paginated/continuous scroll)
 *
 * Requirements: 3.3, 3.4, 14.1
 */
Rectangle {
    id: settingsRoot

    // Reference to the EPUB reader controller
    property var epubController: null

    color: "#fafafa"
    border.color: "#e0e0e0"
    border.width: 1

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 16

        // Header
        Label {
            text: qsTr("Reader Settings")
            font.pixelSize: 16
            font.bold: true
            Layout.fillWidth: true
        }

        // Separator
        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: "#e0e0e0"
        }

        // ------------------------------------------------------------------
        // Font Family
        // ------------------------------------------------------------------
        Label {
            text: qsTr("Font Family")
            font.pixelSize: 13
            color: "#555555"
        }

        ComboBox {
            id: fontFamilyCombo
            Layout.fillWidth: true
            model: ["serif", "sans-serif", "Georgia", "Times New Roman", "Arial", "Verdana", "Courier New"]
            currentIndex: {
                if (!epubController) return 0
                var family = epubController.fontFamily
                var idx = model.indexOf(family)
                return idx >= 0 ? idx : 0
            }

            onActivated: function(index) {
                if (epubController) {
                    epubController.setFont(
                        model[index],
                        fontSizeSlider.value,
                        lineHeightSlider.value
                    )
                }
            }
        }

        // ------------------------------------------------------------------
        // Font Size
        // ------------------------------------------------------------------
        Label {
            text: qsTr("Font Size: %1 pt").arg(Math.round(fontSizeSlider.value))
            font.pixelSize: 13
            color: "#555555"
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Label {
                text: "A"
                font.pixelSize: 10
            }

            Slider {
                id: fontSizeSlider
                Layout.fillWidth: true
                from: 8
                to: 48
                stepSize: 1
                value: epubController ? epubController.fontSize : 16

                onMoved: {
                    if (epubController) {
                        epubController.setFont(
                            fontFamilyCombo.currentText,
                            value,
                            lineHeightSlider.value
                        )
                    }
                }
            }

            Label {
                text: "A"
                font.pixelSize: 20
            }
        }

        // ------------------------------------------------------------------
        // Line Height
        // ------------------------------------------------------------------
        Label {
            text: qsTr("Line Spacing: %1").arg(lineHeightSlider.value.toFixed(1))
            font.pixelSize: 13
            color: "#555555"
        }

        Slider {
            id: lineHeightSlider
            Layout.fillWidth: true
            from: 1.0
            to: 3.0
            stepSize: 0.1
            value: epubController ? epubController.lineHeight : 1.5

            onMoved: {
                if (epubController) {
                    epubController.setFont(
                        fontFamilyCombo.currentText,
                        fontSizeSlider.value,
                        value
                    )
                }
            }
        }

        // Separator
        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: "#e0e0e0"
        }

        // ------------------------------------------------------------------
        // Theme
        // ------------------------------------------------------------------
        Label {
            text: qsTr("Theme")
            font.pixelSize: 13
            color: "#555555"
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Button {
                text: qsTr("Light")
                flat: true
                highlighted: epubController && !epubController.darkMode
                onClicked: {
                    if (epubController) epubController.setTheme(false)
                }
            }

            Button {
                text: qsTr("Dark")
                flat: true
                highlighted: epubController && epubController.darkMode
                onClicked: {
                    if (epubController) epubController.setTheme(true)
                }
            }
        }

        // Separator
        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: "#e0e0e0"
        }

        // ------------------------------------------------------------------
        // View Mode
        // ------------------------------------------------------------------
        Label {
            text: qsTr("View Mode")
            font.pixelSize: 13
            color: "#555555"
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Button {
                text: qsTr("Scroll")
                flat: true
                highlighted: epubController && epubController.viewMode === "continuous_scroll"
                onClicked: {
                    if (epubController) epubController.setPageMode("continuous_scroll")
                }
            }

            Button {
                text: qsTr("Paginated")
                flat: true
                highlighted: epubController && epubController.viewMode === "paginated"
                onClicked: {
                    if (epubController) epubController.setPageMode("paginated")
                }
            }
        }

        // Spacer to push content up
        Item { Layout.fillHeight: true }
    }
}
