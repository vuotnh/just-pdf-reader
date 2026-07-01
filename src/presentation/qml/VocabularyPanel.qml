import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

/**
 * VocabularyPanel.qml - Panel displaying saved vocabulary entries.
 *
 * Shows vocabulary words sorted by date added (most recent first),
 * with filtering by book, tag, or mastery level. Supports editing,
 * deleting entries, and exporting to CSV/Anki formats.
 *
 * Requirements: 7.3–7.7, 14.3
 */
Item {
    id: root

    // Reference to the vocabulary controller (set via context property)
    property var vocabularyController: null

    // Signal emitted when user clicks a word to navigate to its source
    signal wordClicked(string entryId, string bookId)

    // Signal emitted when export data is ready
    signal exportDataReady(string format, string content)

    // Connect to controller's exportReady signal
    Connections {
        target: vocabularyController
        function onExportReady(format, content) {
            root.exportDataReady(format, content)
        }
    }

    // Panel header
    Rectangle {
        id: header
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: 44
        color: "#fafafa"
        border.color: "#e0e0e0"
        border.width: 1

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 12
            anchors.rightMargin: 12
            spacing: 8

            Label {
                text: qsTr("Vocabulary")
                font.pixelSize: 14
                font.bold: true
                color: "#333333"
                Layout.fillWidth: true
            }

            Label {
                text: vocabularyController ? vocabularyController.entryCount.toString() : "0"
                font.pixelSize: 12
                color: "#666666"
                padding: 4
                background: Rectangle {
                    radius: 8
                    color: "#e8e8e8"
                }
            }

            // Export button with format selection
            Button {
                id: exportButton
                text: qsTr("Export")
                flat: true
                font.pixelSize: 11
                onClicked: exportMenu.open()

                Menu {
                    id: exportMenu
                    y: exportButton.height

                    MenuItem {
                        text: qsTr("Export as CSV")
                        onTriggered: {
                            if (vocabularyController) {
                                vocabularyController.exportVocabulary("csv")
                            }
                        }
                    }
                    MenuItem {
                        text: qsTr("Export for Anki")
                        onTriggered: {
                            if (vocabularyController) {
                                vocabularyController.exportVocabulary("anki")
                            }
                        }
                    }
                }
            }
        }
    }

    // Filter bar
    Rectangle {
        id: filterBar
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        height: 40
        color: "#f5f5f5"
        border.color: "#e0e0e0"
        border.width: 1

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 8
            anchors.rightMargin: 8
            spacing: 6

            // Mastery level filter
            ComboBox {
                id: masteryFilter
                Layout.preferredWidth: 110
                font.pixelSize: 11
                model: [
                    qsTr("All Levels"),
                    qsTr("New"),
                    qsTr("Learning"),
                    qsTr("Reviewing"),
                    qsTr("Mastered")
                ]
                onCurrentIndexChanged: {
                    if (!vocabularyController) return
                    var levels = ["", "new", "learning", "reviewing", "mastered"]
                    vocabularyController.setFilterMastery(levels[currentIndex])
                }
            }

            // Tag filter input
            TextField {
                id: tagFilter
                Layout.fillWidth: true
                placeholderText: qsTr("Filter by tag...")
                font.pixelSize: 11
                height: 28
                onAccepted: {
                    if (vocabularyController) {
                        vocabularyController.setFilterTag(text)
                    }
                }
                onTextChanged: {
                    if (text === "" && vocabularyController) {
                        vocabularyController.setFilterTag("")
                    }
                }
            }

            // Clear filters button
            Button {
                text: "\u2715"
                flat: true
                font.pixelSize: 10
                implicitWidth: 24
                implicitHeight: 24
                visible: vocabularyController && (
                    vocabularyController.filterBookId !== "" ||
                    vocabularyController.filterTag !== "" ||
                    vocabularyController.filterMastery !== ""
                )
                onClicked: {
                    masteryFilter.currentIndex = 0
                    tagFilter.text = ""
                    if (vocabularyController) {
                        vocabularyController.clearFilters()
                    }
                }
                ToolTip.text: qsTr("Clear filters")
                ToolTip.visible: hovered
            }
        }
    }

    // Vocabulary word list
    ListView {
        id: vocabListView
        anchors.top: filterBar.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        clip: true
        spacing: 1

        model: vocabularyController ? vocabularyController.vocabularyModel : null

        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        delegate: Rectangle {
            id: vocabDelegate
            width: vocabListView.width
            height: vocabContent.height + 16
            color: delegateMouseArea.containsMouse ? "#f5f8ff" : "transparent"
            border.color: delegateMouseArea.containsMouse ? "#d0d8e8" : "transparent"
            border.width: 1

            ColumnLayout {
                id: vocabContent
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 8
                spacing: 4

                // Header row: word + mastery badge + actions
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6

                    // Word
                    Label {
                        text: model.word || ""
                        font.pixelSize: 13
                        font.bold: true
                        color: "#222222"
                    }

                    // Pronunciation
                    Label {
                        text: model.pronunciation ? "[" + model.pronunciation + "]" : ""
                        font.pixelSize: 11
                        font.italic: true
                        color: "#666666"
                        visible: model.pronunciation !== ""
                    }

                    // Part of speech
                    Label {
                        text: model.partOfSpeech || ""
                        font.pixelSize: 10
                        color: "#888888"
                        visible: model.partOfSpeech !== ""
                    }

                    Item { Layout.fillWidth: true }

                    // Mastery level badge
                    Rectangle {
                        width: masteryLabel.width + 10
                        height: 18
                        radius: 9
                        color: {
                            if (model.masteryLevel === "new") return "#e3f2fd"
                            if (model.masteryLevel === "learning") return "#fff3e0"
                            if (model.masteryLevel === "reviewing") return "#e8f5e9"
                            if (model.masteryLevel === "mastered") return "#f3e5f5"
                            return "#e8e8e8"
                        }
                        border.color: {
                            if (model.masteryLevel === "new") return "#90caf9"
                            if (model.masteryLevel === "learning") return "#ffcc80"
                            if (model.masteryLevel === "reviewing") return "#a5d6a7"
                            if (model.masteryLevel === "mastered") return "#ce93d8"
                            return "#cccccc"
                        }
                        border.width: 1

                        Label {
                            id: masteryLabel
                            anchors.centerIn: parent
                            text: {
                                if (model.masteryLevel === "new") return qsTr("New")
                                if (model.masteryLevel === "learning") return qsTr("Learning")
                                if (model.masteryLevel === "reviewing") return qsTr("Reviewing")
                                if (model.masteryLevel === "mastered") return qsTr("Mastered")
                                return model.masteryLevel || ""
                            }
                            font.pixelSize: 9
                            font.bold: true
                            color: {
                                if (model.masteryLevel === "new") return "#1565c0"
                                if (model.masteryLevel === "learning") return "#e65100"
                                if (model.masteryLevel === "reviewing") return "#2e7d32"
                                if (model.masteryLevel === "mastered") return "#6a1b9a"
                                return "#666666"
                            }
                        }
                    }

                    // Edit button
                    Button {
                        text: "\u270E"
                        flat: true
                        font.pixelSize: 11
                        implicitWidth: 22
                        implicitHeight: 22
                        onClicked: {
                            editDialog.entryId = model.entryId
                            editDialog.wordText = model.word
                            editDialog.definitionText = model.definition
                            editDialog.pronunciationText = model.pronunciation || ""
                            editDialog.exampleText = model.exampleSentence || ""
                            editDialog.masteryValue = model.masteryLevel || "new"
                            editDialog.open()
                        }
                        ToolTip.text: qsTr("Edit entry")
                        ToolTip.visible: hovered
                    }

                    // Delete button
                    Button {
                        text: "\u2715"
                        flat: true
                        font.pixelSize: 10
                        implicitWidth: 20
                        implicitHeight: 20
                        onClicked: {
                            deleteDialog.entryId = model.entryId
                            deleteDialog.wordText = model.word
                            deleteDialog.open()
                        }
                        ToolTip.text: qsTr("Delete entry")
                        ToolTip.visible: hovered
                    }
                }

                // Definition
                Label {
                    Layout.fillWidth: true
                    text: model.definition || ""
                    font.pixelSize: 12
                    color: "#444444"
                    wrapMode: Text.WordWrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                }

                // Example sentence
                Label {
                    Layout.fillWidth: true
                    text: model.exampleSentence ? "\u201C" + model.exampleSentence + "\u201D" : ""
                    font.pixelSize: 11
                    font.italic: true
                    color: "#666666"
                    wrapMode: Text.WordWrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                    visible: model.exampleSentence !== ""
                }

                // Timestamp
                Label {
                    text: {
                        if (!model.createdAt) return ""
                        var d = new Date(model.createdAt)
                        return Qt.formatDateTime(d, "yyyy-MM-dd hh:mm")
                    }
                    font.pixelSize: 10
                    color: "#999999"
                }
            }

            MouseArea {
                id: delegateMouseArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                propagateComposedEvents: true

                onClicked: function(mouse) {
                    root.wordClicked(model.entryId, model.bookId)
                }
            }
        }

        // Empty state
        Label {
            anchors.centerIn: parent
            text: qsTr("No vocabulary entries yet.\nLook up words while reading to build your word bank.")
            font.pixelSize: 13
            color: "#999999"
            horizontalAlignment: Text.AlignHCenter
            visible: vocabListView.count === 0
        }
    }

    // Edit dialog
    Dialog {
        id: editDialog
        anchors.centerIn: parent
        width: Math.min(parent.width - 40, 400)
        title: qsTr("Edit Vocabulary Entry")
        modal: true
        standardButtons: Dialog.Save | Dialog.Cancel

        property string entryId: ""
        property string wordText: ""
        property string definitionText: ""
        property string pronunciationText: ""
        property string exampleText: ""
        property string masteryValue: "new"

        ColumnLayout {
            anchors.fill: parent
            spacing: 8

            Label {
                text: editDialog.wordText
                font.pixelSize: 14
                font.bold: true
                color: "#222222"
            }

            Label { text: qsTr("Definition:"); font.pixelSize: 11; color: "#555555" }
            TextArea {
                id: editDefinition
                Layout.fillWidth: true
                Layout.preferredHeight: 60
                text: editDialog.definitionText
                font.pixelSize: 12
                wrapMode: TextEdit.Wrap
            }

            Label { text: qsTr("Pronunciation:"); font.pixelSize: 11; color: "#555555" }
            TextField {
                id: editPronunciation
                Layout.fillWidth: true
                text: editDialog.pronunciationText
                font.pixelSize: 12
            }

            Label { text: qsTr("Example:"); font.pixelSize: 11; color: "#555555" }
            TextArea {
                id: editExample
                Layout.fillWidth: true
                Layout.preferredHeight: 40
                text: editDialog.exampleText
                font.pixelSize: 12
                wrapMode: TextEdit.Wrap
            }

            Label { text: qsTr("Mastery Level:"); font.pixelSize: 11; color: "#555555" }
            ComboBox {
                id: editMastery
                Layout.fillWidth: true
                model: ["new", "learning", "reviewing", "mastered"]
                currentIndex: {
                    var levels = ["new", "learning", "reviewing", "mastered"]
                    return Math.max(0, levels.indexOf(editDialog.masteryValue))
                }
            }
        }

        onAccepted: {
            if (vocabularyController) {
                vocabularyController.updateEntry(
                    editDialog.entryId,
                    editDefinition.text,
                    editPronunciation.text,
                    editExample.text,
                    editMastery.currentText
                )
            }
        }
    }

    // Delete confirmation dialog
    Dialog {
        id: deleteDialog
        anchors.centerIn: parent
        width: Math.min(parent.width - 40, 320)
        title: qsTr("Delete Vocabulary Entry")
        modal: true
        standardButtons: Dialog.Yes | Dialog.No

        property string entryId: ""
        property string wordText: ""

        Label {
            anchors.fill: parent
            text: qsTr("Are you sure you want to delete \"%1\"?\nThis will also remove all associated review schedules.").arg(deleteDialog.wordText)
            font.pixelSize: 12
            color: "#444444"
            wrapMode: Text.WordWrap
        }

        onAccepted: {
            if (vocabularyController) {
                vocabularyController.deleteEntry(deleteDialog.entryId)
            }
        }
    }
}
