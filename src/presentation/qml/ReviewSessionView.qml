import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

/**
 * ReviewSessionView.qml - Main review session interface.
 *
 * Displays the current review card with mode-specific content
 * (flashcard, MCQ, typing, cloze), rating buttons, session progress,
 * and mode switching controls.
 *
 * Requirements: 8.2–8.6, 14.1
 */
Item {
    id: root

    // Reference to the review controller (set via context property)
    property var reviewController: null

    // Signal emitted when session ends
    signal sessionCompleted()

    // Connect to controller signals
    Connections {
        target: reviewController

        function onSessionEnded() {
            root.sessionCompleted()
        }

        function onErrorOccurred(message) {
            errorLabel.text = message
            errorLabel.visible = true
            errorTimer.restart()
        }
    }

    // Error message auto-hide timer
    Timer {
        id: errorTimer
        interval: 4000
        onTriggered: errorLabel.visible = false
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 12

        // Session header with progress and mode switcher
        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            // Progress indicator
            Label {
                text: reviewController
                    ? qsTr("%1 / %2").arg(reviewController.cardsReviewed).arg(reviewController.totalCards)
                    : "0 / 0"
                font.pixelSize: 13
                color: "#555555"
            }

            // Progress bar
            ProgressBar {
                id: progressBar
                Layout.fillWidth: true
                Layout.preferredHeight: 6
                from: 0.0
                to: 1.0
                value: reviewController ? reviewController.progressPercent : 0.0
            }

            // Mode switcher combo
            ComboBox {
                id: modeCombo
                Layout.preferredWidth: 120
                font.pixelSize: 11
                model: [
                    qsTr("Flashcard"),
                    qsTr("MCQ"),
                    qsTr("Typing"),
                    qsTr("Cloze")
                ]
                currentIndex: {
                    if (!reviewController) return 0
                    var modes = ["flashcard", "mcq", "typing", "cloze"]
                    return Math.max(0, modes.indexOf(reviewController.reviewMode))
                }
                onActivated: function(index) {
                    if (!reviewController) return
                    var modes = ["flashcard", "mcq", "typing", "cloze"]
                    reviewController.setReviewMode(modes[index])
                }
            }

            // End session button
            Button {
                text: qsTr("End Session")
                flat: true
                font.pixelSize: 11
                onClicked: {
                    if (reviewController) {
                        reviewController.endSession()
                    }
                }
            }
        }

        // Error message
        Label {
            id: errorLabel
            Layout.fillWidth: true
            visible: false
            text: ""
            color: "#d32f2f"
            font.pixelSize: 12
            horizontalAlignment: Text.AlignHCenter
            background: Rectangle {
                color: "#ffebee"
                radius: 4
            }
            padding: 6
        }

        // Card area
        Rectangle {
            id: cardArea
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: 12
            color: "#ffffff"
            border.color: "#e0e0e0"
            border.width: 1

            // Drop shadow effect
            layer.enabled: true

            // No cards state
            Label {
                anchors.centerIn: parent
                visible: reviewController && reviewController.isSessionActive
                         && reviewController.currentWord === ""
                text: qsTr("Session complete! All cards reviewed.")
                font.pixelSize: 16
                color: "#666666"
                horizontalAlignment: Text.AlignHCenter
            }

            // Session not started state
            Label {
                anchors.centerIn: parent
                visible: !reviewController || !reviewController.isSessionActive
                text: qsTr("No active session.\nStart a review to begin.")
                font.pixelSize: 14
                color: "#999999"
                horizontalAlignment: Text.AlignHCenter
            }

            // Card content (visible when session active and card available)
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 24
                spacing: 16
                visible: reviewController && reviewController.isSessionActive
                         && reviewController.currentWord !== ""

                Item { Layout.fillHeight: true }

                // Flashcard mode
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 12
                    visible: reviewController && reviewController.reviewMode === "flashcard"

                    // Word (front of card)
                    Label {
                        Layout.fillWidth: true
                        text: reviewController ? reviewController.currentWord : ""
                        font.pixelSize: 28
                        font.bold: true
                        color: "#222222"
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                    }

                    // Pronunciation
                    Label {
                        Layout.fillWidth: true
                        text: reviewController && reviewController.currentPronunciation
                              ? "[" + reviewController.currentPronunciation + "]"
                              : ""
                        font.pixelSize: 14
                        font.italic: true
                        color: "#666666"
                        horizontalAlignment: Text.AlignHCenter
                        visible: reviewController && reviewController.currentPronunciation !== ""
                    }

                    // Reveal divider
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        color: "#e0e0e0"
                        visible: reviewController && reviewController.cardRevealed
                    }

                    // Definition (revealed)
                    Label {
                        Layout.fillWidth: true
                        text: reviewController ? reviewController.currentDefinition : ""
                        font.pixelSize: 18
                        color: "#444444"
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                        visible: reviewController && reviewController.cardRevealed
                    }

                    // Example sentence (revealed)
                    Label {
                        Layout.fillWidth: true
                        text: reviewController && reviewController.currentExample
                              ? "\u201C" + reviewController.currentExample + "\u201D"
                              : ""
                        font.pixelSize: 13
                        font.italic: true
                        color: "#666666"
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                        visible: reviewController && reviewController.cardRevealed
                                 && reviewController.currentExample !== ""
                    }
                }

                // MCQ mode
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 12
                    visible: reviewController && reviewController.reviewMode === "mcq"

                    Label {
                        Layout.fillWidth: true
                        text: reviewController ? reviewController.currentWord : ""
                        font.pixelSize: 24
                        font.bold: true
                        color: "#222222"
                        horizontalAlignment: Text.AlignHCenter
                    }

                    Label {
                        Layout.fillWidth: true
                        text: qsTr("Select the correct definition:")
                        font.pixelSize: 13
                        color: "#666666"
                        horizontalAlignment: Text.AlignHCenter
                    }

                    // MCQ options
                    Repeater {
                        model: {
                            if (!reviewController) return []
                            try {
                                return JSON.parse(reviewController.mcqOptionsJson)
                            } catch(e) {
                                return []
                            }
                        }

                        delegate: Button {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 44
                            text: modelData
                            font.pixelSize: 12
                            onClicked: {
                                if (!reviewController) return
                                // Check if correct (matches definition)
                                var isCorrect = (modelData === reviewController.currentDefinition)
                                // Rate based on correctness
                                reviewController.rateCard(isCorrect ? 3 : 1)
                            }
                        }
                    }
                }

                // Typing mode
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 12
                    visible: reviewController && reviewController.reviewMode === "typing"

                    Label {
                        Layout.fillWidth: true
                        text: reviewController ? reviewController.currentDefinition : ""
                        font.pixelSize: 16
                        color: "#444444"
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                    }

                    Label {
                        Layout.fillWidth: true
                        text: qsTr("Type the word:")
                        font.pixelSize: 13
                        color: "#666666"
                        horizontalAlignment: Text.AlignHCenter
                    }

                    TextField {
                        id: typingInput
                        Layout.fillWidth: true
                        Layout.preferredWidth: 300
                        Layout.alignment: Qt.AlignHCenter
                        font.pixelSize: 16
                        horizontalAlignment: Text.AlignHCenter
                        placeholderText: qsTr("Type your answer...")
                        onAccepted: {
                            if (!reviewController) return
                            var correct = reviewController.checkTypingAnswer(text)
                            reviewController.rateCard(correct ? 3 : 1)
                            text = ""
                        }
                    }

                    Button {
                        Layout.alignment: Qt.AlignHCenter
                        text: qsTr("Submit")
                        onClicked: {
                            typingInput.accepted()
                        }
                    }
                }

                // Cloze mode
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 12
                    visible: reviewController && reviewController.reviewMode === "cloze"

                    Label {
                        Layout.fillWidth: true
                        text: reviewController ? reviewController.currentClozeText : ""
                        font.pixelSize: 18
                        color: "#333333"
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                    }

                    // Reveal divider
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        color: "#e0e0e0"
                        visible: reviewController && reviewController.cardRevealed
                    }

                    // Answer (revealed)
                    Label {
                        Layout.fillWidth: true
                        text: reviewController
                              ? qsTr("Answer: %1").arg(reviewController.currentWord)
                              : ""
                        font.pixelSize: 16
                        font.bold: true
                        color: "#2e7d32"
                        horizontalAlignment: Text.AlignHCenter
                        visible: reviewController && reviewController.cardRevealed
                    }
                }

                Item { Layout.fillHeight: true }
            }
        }

        // Action buttons row
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 48
            spacing: 12
            visible: reviewController && reviewController.isSessionActive
                     && reviewController.currentWord !== ""

            // Reveal button (flashcard and cloze modes)
            Button {
                Layout.fillWidth: true
                Layout.preferredHeight: 44
                text: qsTr("Show Answer")
                font.pixelSize: 14
                visible: reviewController
                         && !reviewController.cardRevealed
                         && (reviewController.reviewMode === "flashcard"
                             || reviewController.reviewMode === "cloze")
                onClicked: {
                    if (reviewController) {
                        reviewController.revealCard()
                    }
                }
            }

            // Rating buttons (visible after reveal, for flashcard and cloze)
            Button {
                Layout.fillWidth: true
                Layout.preferredHeight: 44
                text: qsTr("Again")
                font.pixelSize: 12
                visible: reviewController && reviewController.cardRevealed
                palette.button: "#ffcdd2"
                onClicked: {
                    if (reviewController) reviewController.rateCard(1)
                }
            }

            Button {
                Layout.fillWidth: true
                Layout.preferredHeight: 44
                text: qsTr("Hard")
                font.pixelSize: 12
                visible: reviewController && reviewController.cardRevealed
                palette.button: "#fff9c4"
                onClicked: {
                    if (reviewController) reviewController.rateCard(2)
                }
            }

            Button {
                Layout.fillWidth: true
                Layout.preferredHeight: 44
                text: qsTr("Good")
                font.pixelSize: 12
                visible: reviewController && reviewController.cardRevealed
                palette.button: "#c8e6c9"
                onClicked: {
                    if (reviewController) reviewController.rateCard(3)
                }
            }

            Button {
                Layout.fillWidth: true
                Layout.preferredHeight: 44
                text: qsTr("Easy")
                font.pixelSize: 12
                visible: reviewController && reviewController.cardRevealed
                palette.button: "#bbdefb"
                onClicked: {
                    if (reviewController) reviewController.rateCard(4)
                }
            }
        }
    }
}
