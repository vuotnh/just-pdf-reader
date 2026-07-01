import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

/**
 * SearchPanel.qml - Global search panel with results grouped by category.
 *
 * Provides a search input with full-text search across Books, Annotations,
 * Vocabulary, and Notes. Results are displayed grouped by category with
 * click-to-navigate functionality.
 *
 * Keyboard shortcut: Ctrl+F activates the search input.
 *
 * Requirements: 10.1, 10.3, 10.4, 14.2, 14.6
 */
Item {
    id: root

    // Reference to the search controller (set via context property)
    property var searchController: null

    // Signal emitted when user clicks a result to navigate
    signal resultNavigated(string entityId, string category, string bookId, string positionData)

    // Connect to controller signals for navigation
    Connections {
        target: searchController

        function onSearchActivated() {
            searchInput.forceActiveFocus()
            searchInput.selectAll()
        }

        function onNavigateToBook(bookId, positionData) {
            root.resultNavigated(bookId, "Books", bookId, positionData)
        }

        function onNavigateToAnnotation(annotationId, bookId) {
            root.resultNavigated(annotationId, "Annotations", bookId, "")
        }

        function onNavigateToVocabulary(entryId) {
            root.resultNavigated(entryId, "Vocabulary", "", "")
        }
    }

    // Global keyboard shortcut for search (Ctrl+F)
    Shortcut {
        sequence: "Ctrl+F"
        onActivated: {
            if (searchController) {
                searchController.activateSearch()
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Search header with input field
        Rectangle {
            id: searchHeader
            Layout.fillWidth: true
            Layout.preferredHeight: 52
            color: "#fafafa"
            border.color: "#e0e0e0"
            border.width: 1

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                anchors.topMargin: 8
                anchors.bottomMargin: 8
                spacing: 8

                // Search icon
                Label {
                    text: "\uD83D\uDD0D"
                    font.pixelSize: 14
                    color: "#666666"
                }

                // Search input field
                TextField {
                    id: searchInput
                    Layout.fillWidth: true
                    placeholderText: qsTr("Search books, annotations, vocabulary...")
                    font.pixelSize: 13
                    selectByMouse: true

                    onAccepted: {
                        if (searchController && text.trim().length > 0) {
                            searchController.search(text.trim())
                        }
                    }

                    onTextChanged: {
                        // Clear results when input is cleared
                        if (text === "" && searchController) {
                            searchController.clearSearch()
                        }
                    }

                    Keys.onEscapePressed: {
                        text = ""
                        if (searchController) {
                            searchController.clearSearch()
                        }
                        focus = false
                    }
                }

                // Clear button
                Button {
                    text: "\u2715"
                    flat: true
                    font.pixelSize: 10
                    implicitWidth: 24
                    implicitHeight: 24
                    visible: searchInput.text.length > 0
                    onClicked: {
                        searchInput.text = ""
                        if (searchController) {
                            searchController.clearSearch()
                        }
                        searchInput.forceActiveFocus()
                    }
                    ToolTip.text: qsTr("Clear search")
                    ToolTip.visible: hovered
                }
            }
        }

        // Results summary bar
        Rectangle {
            id: summaryBar
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? 32 : 0
            visible: searchController && searchController.totalCount > 0
            color: "#f0f4f8"
            border.color: "#e0e0e0"
            border.width: 1

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 12

                Label {
                    text: searchController
                        ? qsTr("%1 results").arg(searchController.totalCount)
                        : ""
                    font.pixelSize: 11
                    font.bold: true
                    color: "#444444"
                }

                Item { Layout.fillWidth: true }

                // Category count badges
                Label {
                    visible: searchController && searchController.booksCount > 0
                    text: qsTr("Books: %1").arg(searchController ? searchController.booksCount : 0)
                    font.pixelSize: 10
                    color: "#1565c0"
                }
                Label {
                    visible: searchController && searchController.annotationsCount > 0
                    text: qsTr("Annotations: %1").arg(searchController ? searchController.annotationsCount : 0)
                    font.pixelSize: 10
                    color: "#2e7d32"
                }
                Label {
                    visible: searchController && searchController.vocabularyCount > 0
                    text: qsTr("Vocabulary: %1").arg(searchController ? searchController.vocabularyCount : 0)
                    font.pixelSize: 10
                    color: "#e65100"
                }
                Label {
                    visible: searchController && searchController.notesCount > 0
                    text: qsTr("Notes: %1").arg(searchController ? searchController.notesCount : 0)
                    font.pixelSize: 10
                    color: "#6a1b9a"
                }
            }
        }

        // Search results list grouped by category
        ListView {
            id: resultsListView
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 1

            model: searchController ? searchController.resultsModel : null

            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            // Section headers for category grouping
            section.property: "category"
            section.delegate: Rectangle {
                width: resultsListView.width
                height: 28
                color: "#f5f5f5"
                border.color: "#e0e0e0"
                border.width: 1

                Label {
                    anchors.left: parent.left
                    anchors.leftMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    text: section
                    font.pixelSize: 11
                    font.bold: true
                    color: {
                        if (section === "Books") return "#1565c0"
                        if (section === "Annotations") return "#2e7d32"
                        if (section === "Vocabulary") return "#e65100"
                        if (section === "Notes") return "#6a1b9a"
                        return "#444444"
                    }
                }
            }

            delegate: Rectangle {
                id: resultDelegate
                width: resultsListView.width
                height: resultContent.height + 16
                color: resultMouseArea.containsMouse ? "#f5f8ff" : "transparent"
                border.color: resultMouseArea.containsMouse ? "#d0d8e8" : "transparent"
                border.width: 1

                ColumnLayout {
                    id: resultContent
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 8
                    spacing: 4

                    // Title row with category indicator
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6

                        // Category color indicator
                        Rectangle {
                            width: 4
                            height: 14
                            radius: 2
                            color: {
                                if (model.category === "Books") return "#1565c0"
                                if (model.category === "Annotations") return "#2e7d32"
                                if (model.category === "Vocabulary") return "#e65100"
                                if (model.category === "Notes") return "#6a1b9a"
                                return "#999999"
                            }
                        }

                        // Title
                        Label {
                            text: model.title || ""
                            font.pixelSize: 12
                            font.bold: true
                            color: "#222222"
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                    }

                    // Snippet
                    Label {
                        Layout.fillWidth: true
                        text: model.snippet || ""
                        font.pixelSize: 11
                        color: "#555555"
                        wrapMode: Text.WordWrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                    }
                }

                MouseArea {
                    id: resultMouseArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor

                    onClicked: {
                        if (searchController) {
                            searchController.navigateToResult(
                                model.entityId,
                                model.category,
                                model.bookId,
                                model.positionData
                            )
                        }
                    }
                }
            }

            // Empty state - no results
            Label {
                anchors.centerIn: parent
                text: {
                    if (searchController && searchController.currentQuery !== "" && searchController.totalCount === 0) {
                        return qsTr("No results found for \"%1\".\nTry different keywords or search operators.").arg(searchController.currentQuery)
                    }
                    return qsTr("Search across your library.\nUse Ctrl+F for quick access.")
                }
                font.pixelSize: 13
                color: "#999999"
                horizontalAlignment: Text.AlignHCenter
                visible: resultsListView.count === 0
            }
        }

        // Search tips footer
        Rectangle {
            id: tipsFooter
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? 36 : 0
            visible: searchInput.activeFocus && searchInput.text.length === 0
            color: "#f9f9f9"
            border.color: "#e0e0e0"
            border.width: 1

            Label {
                anchors.centerIn: parent
                text: qsTr("Tips: Use \"quotes\" for exact phrases, OR for alternatives, -word to exclude")
                font.pixelSize: 10
                color: "#888888"
            }
        }
    }
}
