import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

/**
 * DictionaryPopup.qml - Floating popup displaying word definition.
 *
 * Shows pronunciation (IPA), definitions grouped by part of speech,
 * example sentences, synonyms, and a source selector. Includes a
 * "Save to Vocabulary" button for adding words to the review queue.
 *
 * Triggered by double-click word lookup with a 100ms response target.
 *
 * Requirements: 6.1–6.8, 12.2
 */
Popup {
    id: root

    // Reference to the dictionary controller (set via context property)
    property var dictionaryController: null

    // Parsed data from controller JSON properties
    property var definitions: []
    property var examples: []
    property var synonyms: []
    property var availableSources: []

    width: 380
    height: Math.min(contentColumn.implicitHeight + 32, 500)
    modal: false
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    padding: 16

    background: Rectangle {
        color: "#ffffff"
        radius: 10
        border.color: "#d0d0d0"
        border.width: 1
        layer.enabled: true
    }

    onOpened: {
        _parseControllerData()
    }

    onClosed: {
        if (dictionaryController) {
            dictionaryController.hidePopup()
        }
    }

    // Update parsed data when controller signals changes
    Connections {
        target: dictionaryController
        function onDefinitionsChanged() { _parseControllerData() }
        function onExamplesChanged() { _parseControllerData() }
        function onSynonymsChanged() { _parseControllerData() }
        function onAvailableSourcesChanged() { _parseControllerData() }
        function onPopupVisibleChanged(visible) {
            if (visible) {
                root.open()
            } else {
                root.close()
            }
        }
    }

    function _parseControllerData() {
        if (!dictionaryController) return

        try {
            root.definitions = JSON.parse(dictionaryController.definitionsJson)
        } catch (e) {
            root.definitions = []
        }
        try {
            root.examples = JSON.parse(dictionaryController.examplesJson)
        } catch (e) {
            root.examples = []
        }
        try {
            root.synonyms = JSON.parse(dictionaryController.synonymsJson)
        } catch (e) {
            root.synonyms = []
        }
        try {
            root.availableSources = JSON.parse(dictionaryController.availableSourcesJson)
        } catch (e) {
            root.availableSources = []
        }
    }

    Flickable {
        id: flickable
        anchors.fill: parent
        contentHeight: contentColumn.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        ColumnLayout {
            id: contentColumn
            width: flickable.width
            spacing: 12

            // ------------------------------------------------------------------
            // Header: Word + Pronunciation
            // ------------------------------------------------------------------
            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                // Word
                Label {
                    text: dictionaryController ? dictionaryController.word : ""
                    font.pixelSize: 20
                    font.bold: true
                    color: "#222222"
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }

                // Close button
                Button {
                    text: "\u2715"
                    flat: true
                    font.pixelSize: 12
                    implicitWidth: 24
                    implicitHeight: 24
                    onClicked: root.close()
                }
            }

            // Pronunciation (IPA)
            Label {
                text: dictionaryController ? dictionaryController.pronunciation : ""
                font.pixelSize: 14
                font.italic: true
                color: "#666666"
                visible: text !== ""
                Layout.fillWidth: true
            }

            // ------------------------------------------------------------------
            // Source selector
            // ------------------------------------------------------------------
            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                visible: root.availableSources.length > 1

                Label {
                    text: qsTr("Source:")
                    font.pixelSize: 11
                    color: "#888888"
                }

                ComboBox {
                    id: sourceCombo
                    model: root.availableSources.filter(function(s) { return s !== "cache" })
                    currentIndex: {
                        var src = dictionaryController ? dictionaryController.currentSource : ""
                        var filtered = root.availableSources.filter(function(s) { return s !== "cache" })
                        var idx = filtered.indexOf(src)
                        return idx >= 0 ? idx : 0
                    }
                    font.pixelSize: 11
                    implicitWidth: 140
                    implicitHeight: 28

                    onActivated: function(index) {
                        if (dictionaryController && index >= 0) {
                            var filtered = root.availableSources.filter(function(s) { return s !== "cache" })
                            dictionaryController.lookupFromSource(filtered[index])
                        }
                    }
                }
            }

            // ------------------------------------------------------------------
            // Separator
            // ------------------------------------------------------------------
            Rectangle {
                Layout.fillWidth: true
                height: 1
                color: "#e8e8e8"
            }

            // ------------------------------------------------------------------
            // Definitions by part of speech
            // ------------------------------------------------------------------
            Column {
                Layout.fillWidth: true
                spacing: 8
                visible: root.definitions.length > 0

                Repeater {
                    model: root.definitions

                    delegate: Column {
                        width: parent.width
                        spacing: 4

                        // Part of speech label
                        Label {
                            text: modelData.pos || ""
                            font.pixelSize: 12
                            font.bold: true
                            font.italic: true
                            color: "#4a90d9"
                            visible: text !== ""
                        }

                        // Definitions list
                        Column {
                            width: parent.width
                            spacing: 2

                            Repeater {
                                model: modelData.definitions || []

                                delegate: RowLayout {
                                    width: parent.width
                                    spacing: 6

                                    Label {
                                        text: (index + 1) + "."
                                        font.pixelSize: 12
                                        color: "#999999"
                                        Layout.alignment: Qt.AlignTop
                                    }

                                    Label {
                                        text: modelData
                                        font.pixelSize: 12
                                        color: "#333333"
                                        wrapMode: Text.WordWrap
                                        Layout.fillWidth: true
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Not found message
            Label {
                text: qsTr("Definition not found. Try a different source or check spelling.")
                font.pixelSize: 12
                color: "#cc4444"
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
                visible: root.definitions.length === 0 && (dictionaryController ? dictionaryController.word !== "" : false)
            }

            // ------------------------------------------------------------------
            // Examples
            // ------------------------------------------------------------------
            Column {
                Layout.fillWidth: true
                spacing: 4
                visible: root.examples.length > 0

                Label {
                    text: qsTr("Examples")
                    font.pixelSize: 11
                    font.bold: true
                    color: "#666666"
                }

                Repeater {
                    model: root.examples.slice(0, 3)  // Show up to 3 examples

                    delegate: Label {
                        width: parent.width
                        text: "\u201C" + modelData + "\u201D"
                        font.pixelSize: 11
                        font.italic: true
                        color: "#555555"
                        wrapMode: Text.WordWrap
                        leftPadding: 8
                    }
                }
            }

            // ------------------------------------------------------------------
            // Synonyms
            // ------------------------------------------------------------------
            Flow {
                Layout.fillWidth: true
                spacing: 4
                visible: root.synonyms.length > 0

                Label {
                    text: qsTr("Synonyms: ")
                    font.pixelSize: 11
                    font.bold: true
                    color: "#666666"
                }

                Repeater {
                    model: root.synonyms.slice(0, 8)  // Show up to 8 synonyms

                    delegate: Rectangle {
                        width: synLabel.width + 12
                        height: synLabel.height + 6
                        radius: 4
                        color: "#f0f4f8"
                        border.color: "#d0dce8"
                        border.width: 1

                        Label {
                            id: synLabel
                            anchors.centerIn: parent
                            text: modelData
                            font.pixelSize: 10
                            color: "#4a6a8a"
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                if (dictionaryController) {
                                    dictionaryController.lookupWord(modelData)
                                }
                            }
                        }
                    }
                }
            }

            // ------------------------------------------------------------------
            // Separator before action buttons
            // ------------------------------------------------------------------
            Rectangle {
                Layout.fillWidth: true
                height: 1
                color: "#e8e8e8"
                visible: root.definitions.length > 0
            }

            // ------------------------------------------------------------------
            // Save to Vocabulary button
            // ------------------------------------------------------------------
            Button {
                id: saveButton
                text: qsTr("Save to Vocabulary")
                Layout.fillWidth: true
                implicitHeight: 36
                enabled: root.definitions.length > 0
                visible: root.definitions.length > 0

                contentItem: Label {
                    text: saveButton.text
                    font.pixelSize: 12
                    font.bold: true
                    color: saveButton.enabled ? "#ffffff" : "#aaaaaa"
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }

                background: Rectangle {
                    radius: 6
                    color: {
                        if (!saveButton.enabled) return "#e0e0e0"
                        if (saveButton.pressed) return "#357abd"
                        if (saveButton.hovered) return "#4a9ae8"
                        return "#4a90d9"
                    }
                }

                onClicked: {
                    if (dictionaryController) {
                        var result = dictionaryController.saveToVocabulary()
                        if (result) {
                            saveButton.text = qsTr("\u2713 Saved!")
                            saveButton.enabled = false
                            // Reset after 2 seconds
                            saveResetTimer.start()
                        }
                    }
                }
            }

            Timer {
                id: saveResetTimer
                interval: 2000
                repeat: false
                onTriggered: {
                    saveButton.text = qsTr("Save to Vocabulary")
                    saveButton.enabled = root.definitions.length > 0
                }
            }
        }
    }
}
