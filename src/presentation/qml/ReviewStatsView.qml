import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

/**
 * ReviewStatsView.qml - Review statistics dashboard.
 *
 * Displays daily review stats (due today, reviewed, new cards)
 * and a 7-day forecast bar chart showing upcoming review load.
 *
 * Requirements: 8.5, 8.6, 14.1
 */
Item {
    id: root

    // Reference to the review controller (set via context property)
    property var reviewController: null

    // Signal to navigate to review session
    signal startReviewRequested(string mode)

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 16

        // Header
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Label {
                text: qsTr("Review Dashboard")
                font.pixelSize: 18
                font.bold: true
                color: "#222222"
                Layout.fillWidth: true
            }

            Button {
                text: qsTr("Refresh")
                flat: true
                font.pixelSize: 11
                onClicked: {
                    if (reviewController) {
                        reviewController.refreshStats()
                    }
                }
            }
        }

        // Daily stats cards row
        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            // Due today card
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 80
                radius: 8
                color: "#e3f2fd"
                border.color: "#90caf9"
                border.width: 1

                ColumnLayout {
                    anchors.centerIn: parent
                    spacing: 4

                    Label {
                        Layout.alignment: Qt.AlignHCenter
                        text: reviewController ? reviewController.dueToday.toString() : "0"
                        font.pixelSize: 28
                        font.bold: true
                        color: "#1565c0"
                    }

                    Label {
                        Layout.alignment: Qt.AlignHCenter
                        text: qsTr("Due Today")
                        font.pixelSize: 11
                        color: "#1976d2"
                    }
                }
            }

            // Reviewed today card
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 80
                radius: 8
                color: "#e8f5e9"
                border.color: "#a5d6a7"
                border.width: 1

                ColumnLayout {
                    anchors.centerIn: parent
                    spacing: 4

                    Label {
                        Layout.alignment: Qt.AlignHCenter
                        text: reviewController ? reviewController.reviewedToday.toString() : "0"
                        font.pixelSize: 28
                        font.bold: true
                        color: "#2e7d32"
                    }

                    Label {
                        Layout.alignment: Qt.AlignHCenter
                        text: qsTr("Reviewed")
                        font.pixelSize: 11
                        color: "#388e3c"
                    }
                }
            }

            // New cards card
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 80
                radius: 8
                color: "#fff3e0"
                border.color: "#ffcc80"
                border.width: 1

                ColumnLayout {
                    anchors.centerIn: parent
                    spacing: 4

                    Label {
                        Layout.alignment: Qt.AlignHCenter
                        text: reviewController ? reviewController.newCards.toString() : "0"
                        font.pixelSize: 28
                        font.bold: true
                        color: "#e65100"
                    }

                    Label {
                        Layout.alignment: Qt.AlignHCenter
                        text: qsTr("New Cards")
                        font.pixelSize: 11
                        color: "#f57c00"
                    }
                }
            }
        }

        // Start review button
        Button {
            Layout.fillWidth: true
            Layout.preferredHeight: 44
            text: reviewController && reviewController.dueToday > 0
                  ? qsTr("Start Review (%1 cards)").arg(reviewController.dueToday)
                  : qsTr("No Cards Due")
            font.pixelSize: 14
            font.bold: true
            enabled: reviewController && reviewController.dueToday > 0
            onClicked: {
                root.startReviewRequested("flashcard")
            }
        }

        // 7-Day Forecast section
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: 8
            color: "#fafafa"
            border.color: "#e0e0e0"
            border.width: 1

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 12

                Label {
                    text: qsTr("7-Day Forecast")
                    font.pixelSize: 14
                    font.bold: true
                    color: "#333333"
                }

                // Bar chart
                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    // Get forecast data
                    property var forecastData: {
                        if (!reviewController) return [0, 0, 0, 0, 0, 0, 0]
                        try {
                            return JSON.parse(reviewController.forecastJson)
                        } catch(e) {
                            return [0, 0, 0, 0, 0, 0, 0]
                        }
                    }

                    // Calculate max for scaling
                    property int maxValue: {
                        var max = 1
                        for (var i = 0; i < forecastData.length; i++) {
                            if (forecastData[i] > max) max = forecastData[i]
                        }
                        return max
                    }

                    // Day labels
                    property var dayLabels: {
                        var labels = []
                        var today = new Date()
                        for (var i = 1; i <= 7; i++) {
                            var d = new Date(today.getTime() + i * 86400000)
                            labels.push(Qt.formatDate(d, "ddd"))
                        }
                        return labels
                    }

                    Row {
                        anchors.fill: parent
                        anchors.bottomMargin: 24
                        spacing: 8

                        Repeater {
                            model: 7

                            delegate: Item {
                                width: (parent.width - 6 * 8) / 7
                                height: parent.height

                                // Bar
                                Rectangle {
                                    id: bar
                                    anchors.bottom: parent.bottom
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    width: Math.max(parent.width - 8, 20)
                                    height: {
                                        var data = parent.parent.parent.forecastData
                                        var maxVal = parent.parent.parent.maxValue
                                        if (!data || data.length <= index) return 0
                                        var ratio = data[index] / maxVal
                                        return Math.max(4, ratio * (parent.height - 30))
                                    }
                                    radius: 4
                                    color: "#42a5f5"

                                    Behavior on height {
                                        NumberAnimation { duration: 300; easing.type: Easing.OutCubic }
                                    }
                                }

                                // Value label above bar
                                Label {
                                    anchors.bottom: bar.top
                                    anchors.bottomMargin: 4
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: {
                                        var data = parent.parent.parent.forecastData
                                        if (!data || data.length <= index) return "0"
                                        return data[index].toString()
                                    }
                                    font.pixelSize: 10
                                    color: "#555555"
                                }

                                // Day label below bar
                                Label {
                                    anchors.top: parent.bottom
                                    anchors.topMargin: 4
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: {
                                        var labels = parent.parent.parent.dayLabels
                                        if (!labels || labels.length <= index) return ""
                                        return labels[index]
                                    }
                                    font.pixelSize: 10
                                    color: "#777777"
                                }
                            }
                        }
                    }
                }
            }
        }

        // Session stats (shown after session ends)
        Rectangle {
            id: sessionSummary
            Layout.fillWidth: true
            Layout.preferredHeight: 60
            radius: 8
            color: "#f3e5f5"
            border.color: "#ce93d8"
            border.width: 1
            visible: false

            property int lastReviewed: 0
            property real lastAccuracy: 0.0
            property real lastTime: 0.0

            RowLayout {
                anchors.fill: parent
                anchors.margins: 12
                spacing: 16

                Label {
                    text: qsTr("Last Session:")
                    font.pixelSize: 12
                    font.bold: true
                    color: "#6a1b9a"
                }

                Label {
                    text: qsTr("%1 cards").arg(sessionSummary.lastReviewed)
                    font.pixelSize: 12
                    color: "#7b1fa2"
                }

                Label {
                    text: qsTr("%1% accuracy").arg(Math.round(sessionSummary.lastAccuracy * 100))
                    font.pixelSize: 12
                    color: "#7b1fa2"
                }

                Label {
                    text: {
                        var seconds = Math.round(sessionSummary.lastTime)
                        var minutes = Math.floor(seconds / 60)
                        var secs = seconds % 60
                        return qsTr("%1m %2s").arg(minutes).arg(secs)
                    }
                    font.pixelSize: 12
                    color: "#7b1fa2"
                }

                Item { Layout.fillWidth: true }
            }
        }
    }

    // Update session summary when session ends
    Connections {
        target: reviewController

        function onSessionEnded() {
            if (!reviewController) return
            var statsJson = reviewController.getSessionStatsJson()
            try {
                var stats = JSON.parse(statsJson)
                sessionSummary.lastReviewed = stats.cards_reviewed || 0
                sessionSummary.lastAccuracy = stats.accuracy_rate || 0.0
                sessionSummary.lastTime = stats.time_spent_seconds || 0.0
                sessionSummary.visible = (stats.cards_reviewed > 0)
            } catch(e) {
                sessionSummary.visible = false
            }
        }
    }
}
