import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Dialogs
import QtWebEngine 1.10
import Qt.labs.settings 1.1

ApplicationWindow {
    id: mainWindow

    visible: true
    width: 1280
    height: 800
    minimumWidth: 800
    minimumHeight: 600
    title: appController && appController.isBookOpen
        ? appController.bookTitle + " — AI Ebook Reader"
        : "AI Ebook Reader"

    // Panel state
    property bool navPanelVisible: true
    property real navPanelWidth: 260
    property bool sidePanelVisible: false
    property real sidePanelWidth: 300
    readonly property real minPanelWidth: 200

    Settings {
        category: "Layout"
        property alias navPanelVisible: mainWindow.navPanelVisible
        property alias navPanelWidth: mainWindow.navPanelWidth
        property alias sidePanelVisible: mainWindow.sidePanelVisible
        property alias sidePanelWidth: mainWindow.sidePanelWidth
        property alias windowWidth: mainWindow.width
        property alias windowHeight: mainWindow.height
    }

    // =========================================================================
    // Toolbar
    // =========================================================================
    header: ToolBar {
        height: 40
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 8
            anchors.rightMargin: 8
            spacing: 4

            ToolButton { text: "☰"; onClicked: mainWindow.navPanelVisible = !mainWindow.navPanelVisible }
            ToolButton { text: "📂"; onClicked: openFileDialog.open(); ToolTip.text: "Open (Ctrl+O)"; ToolTip.visible: hovered }

            Item { Layout.fillWidth: true }

            // Zoom
            ToolButton { text: "−"; font.pixelSize: 16; onClicked: appController.zoomOut() }
            Label {
                text: appController ? appController.zoomPercent + "%" : "100%"
                font.pixelSize: 12; color: "#555"
                Layout.preferredWidth: 44
                horizontalAlignment: Text.AlignHCenter
                MouseArea { anchors.fill: parent; onClicked: appController.zoomReset() }
            }
            ToolButton { text: "+"; font.pixelSize: 16; onClicked: appController.zoomIn() }

            Item { Layout.fillWidth: true }

            // Page nav
            ToolButton { text: "◀"; onClicked: appController.previousPage(); enabled: appController && appController.currentPage > 0 }
            Label {
                text: appController && appController.isBookOpen
                    ? (appController.currentPage + 1) + " / " + appController.pageCount : ""
                font.pixelSize: 12; color: "#555"
                Layout.preferredWidth: 70
                horizontalAlignment: Text.AlignHCenter
            }
            ToolButton { text: "▶"; onClicked: appController.nextPage(); enabled: appController && appController.currentPage < appController.pageCount - 1 }

            Item { Layout.fillWidth: true }

            ToolButton { text: "≡"; onClicked: mainWindow.sidePanelVisible = !mainWindow.sidePanelVisible }
        }
    }

    // =========================================================================
    // Status Bar
    // =========================================================================
    footer: ToolBar {
        height: 26
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 12
            anchors.rightMargin: 12
            Label {
                text: appController && appController.isBookOpen ? appController.bookTitle : "Ready"
                font.pixelSize: 11; color: "#666"; elide: Text.ElideRight; Layout.fillWidth: true
            }
            Label {
                visible: appController && appController.isBookOpen
                text: appController ? "Page " + (appController.currentPage + 1) + " / " + appController.pageCount : ""
                font.pixelSize: 11; color: "#555"
            }
            Rectangle {
                visible: appController && appController.isBookOpen
                width: 80; height: 6; radius: 3; color: "#ddd"
                Rectangle {
                    width: appController && appController.pageCount > 0
                        ? parent.width * (appController.currentPage + 1) / appController.pageCount : 0
                    height: parent.height; radius: 3; color: "#1a73e8"
                }
            }
        }
    }

    // =========================================================================
    // File Dialog
    // =========================================================================
    FileDialog {
        id: openFileDialog
        title: "Open Ebook"
        nameFilters: ["Ebook files (*.pdf *.epub *.azw3)", "PDF (*.pdf)", "All files (*)"]
        onAccepted: {
            var filePath = selectedFile.toString()
            if (Qt.platform.os === "windows") filePath = filePath.replace("file:///", "")
            else filePath = filePath.replace("file://", "")
            appController.openBook(filePath)
        }
    }

    // =========================================================================
    // Shortcuts
    // =========================================================================
    Shortcut { sequence: "Ctrl+O"; onActivated: openFileDialog.open() }
    Shortcut { sequence: "Ctrl+L"; onActivated: mainWindow.navPanelVisible = !mainWindow.navPanelVisible }
    Shortcut { sequence: "Ctrl+R"; onActivated: mainWindow.sidePanelVisible = !mainWindow.sidePanelVisible }
    Shortcut { sequence: "Left"; onActivated: if (appController) appController.previousPage() }
    Shortcut { sequence: "Right"; onActivated: if (appController) appController.nextPage() }
    Shortcut { sequence: "Ctrl++"; onActivated: if (appController) appController.zoomIn() }
    Shortcut { sequence: "Ctrl+-"; onActivated: if (appController) appController.zoomOut() }
    Shortcut { sequence: "Ctrl+0"; onActivated: if (appController) appController.zoomReset() }

    // =========================================================================
    // Main Content
    // =========================================================================
    SplitView {
        anchors.fill: parent
        orientation: Qt.Horizontal

        // =====================================================================
        // LEFT PANEL - TOC
        // =====================================================================
        Rectangle {
            id: navPanel
            SplitView.preferredWidth: mainWindow.navPanelVisible ? mainWindow.navPanelWidth : 0
            SplitView.minimumWidth: mainWindow.navPanelVisible ? mainWindow.minPanelWidth : 0
            SplitView.maximumWidth: mainWindow.navPanelVisible ? 500 : 0
            visible: mainWindow.navPanelVisible
            color: "#f8f9fa"

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                TabBar {
                    id: navTabBar
                    Layout.fillWidth: true
                    TabButton { text: "TOC"; font.pixelSize: 11 }
                    TabButton { text: "Library"; font.pixelSize: 11 }
                }

                // TOC list
                ListView {
                    id: tocListView
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    visible: navTabBar.currentIndex === 0
                    model: ListModel { id: tocModel }
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                    delegate: ItemDelegate {
                        width: tocListView.width
                        height: 32
                        leftPadding: 12 + (model.level - 1) * 16

                        background: Rectangle {
                            color: model.page === (appController ? appController.currentPage : -1)
                                ? "#e3f2fd" : "transparent"
                        }

                        contentItem: Label {
                            text: model.title
                            font.pixelSize: model.level === 1 ? 12 : 11
                            font.bold: model.level === 1
                            color: model.page === (appController ? appController.currentPage : -1) ? "#1565c0" : "#333"
                            elide: Text.ElideRight
                            verticalAlignment: Text.AlignVCenter
                        }

                        onClicked: if (appController) appController.goToPage(model.page)
                    }

                    Label {
                        anchors.centerIn: parent
                        text: "No table of contents"
                        color: "#999"; font.pixelSize: 12
                        visible: tocModel.count === 0
                    }
                }

                Label {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    text: "Library"; color: "#999"; font.pixelSize: 12
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    visible: navTabBar.currentIndex === 1
                }
            }
        }

        // =====================================================================
        // CENTER - WebEngine PDF Reader
        // =====================================================================
        Rectangle {
            id: readerArea
            SplitView.fillWidth: true
            SplitView.minimumWidth: 400
            color: "#4a4a4a"

            // Empty state
            Label {
                anchors.centerIn: parent
                text: "Open a book to start reading\n\nCtrl+O or click 📂"
                font.pixelSize: 16; color: "#aaa"
                horizontalAlignment: Text.AlignHCenter
                visible: !appController || !appController.isBookOpen
            }

            // WebEngineView renders PDF with selectable text
            WebEngineView {
                id: pdfWebView
                anchors.fill: parent
                visible: appController && appController.isBookOpen
                backgroundColor: "#4a4a4a"

                settings.javascriptEnabled: true

                // Intercept JS console.log for action dispatch
                onJavaScriptConsoleMessage: function(level, message, lineNumber, sourceID) {
                    if (message.startsWith("ACTION:")) {
                        var parts = message.split(":")
                        var action = parts[1]
                        var text = parts.slice(2).join(":")
                        console.log("Action detected:", action, "text:", text)
                        if (action === "dictionary" && appController) {
                            appController.lookupDictionary(text)
                        } else if (action === "translate" && appController) {
                            appController.lookupDictionary(text)
                        }
                    } else if (message.startsWith("PAGE_VISIBLE:")) {
                        var pageNum = parseInt(message.split(":")[1])
                        if (appController && !isNaN(pageNum)) {
                            appController.goToPage(pageNum)
                        }
                    } else if (message === "NAV:next") {
                        if (appController) appController.nextPage()
                    } else if (message === "NAV:prev") {
                        if (appController) appController.previousPage()
                    } else if (message.startsWith("SAVE_HIGHLIGHT:")) {
                        var hlParts = message.substring("SAVE_HIGHLIGHT:".length).split(":")
                        var hlColor = hlParts[0]
                        var hlText = hlParts.slice(1).join(":")
                        if (appController) appController.saveHighlight(hlColor, hlText)
                    }
                }
            }

            // Dictionary popup — draggable & resizable
            Rectangle {
                id: dictPopup
                visible: false
                x: parent.width - width - 16
                y: 16
                width: 420
                height: 500
                radius: 8
                color: "#ffffff"
                border.color: "#b0b0b0"
                border.width: 1
                z: 100
                clip: true

                property real minW: 280
                property real minH: 200

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    // Title bar — draggable
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 30
                        color: "#f0f1f3"
                        radius: 8

                        Rectangle {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            height: 8
                            color: parent.color
                        }

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 10
                            anchors.rightMargin: 4
                            spacing: 4

                            Label {
                                id: dictHeaderLabel
                                text: "Dictionary"
                                font.pixelSize: 12
                                font.bold: true
                                color: "#333"
                                Layout.fillWidth: true
                            }

                            Button {
                                id: dictLangToggle
                                text: "EN-VI"
                                flat: true
                                font.pixelSize: 10
                                implicitHeight: 22
                                implicitWidth: 40
                                property bool isVietnamese: true
                                onClicked: {
                                    isVietnamese = !isVietnamese
                                    text = isVietnamese ? "EN-VI" : "EN-EN"
                                    if (dictWebView.dictUrls) {
                                        dictWebView.url = isVietnamese
                                            ? dictWebView.dictUrls.en_vi
                                            : dictWebView.dictUrls.en_en
                                    }
                                }
                            }

                            Button {
                                text: "✕"
                                flat: true
                                font.pixelSize: 12
                                implicitWidth: 22
                                implicitHeight: 22
                                onClicked: dictPopup.visible = false
                            }
                        }

                        // Drag area (over whole title bar)
                        MouseArea {
                            anchors.fill: parent
                            anchors.rightMargin: 70  // Don't cover buttons
                            cursorShape: Qt.SizeAllCursor
                            property point pressPos: Qt.point(0, 0)

                            onPressed: function(mouse) {
                                pressPos = Qt.point(mouse.x, mouse.y)
                            }
                            onPositionChanged: function(mouse) {
                                var dx = mouse.x - pressPos.x
                                var dy = mouse.y - pressPos.y
                                dictPopup.x = Math.max(0, Math.min(dictPopup.x + dx, dictPopup.parent.width - 80))
                                dictPopup.y = Math.max(0, Math.min(dictPopup.y + dy, dictPopup.parent.height - 40))
                            }
                        }
                    }

                    // WebView content
                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        WebEngineView {
                            id: dictWebView
                            anchors.fill: parent
                            anchors.bottomMargin: 14  // Leave room for resize grip
                            property var dictUrls: null
                            settings.javascriptEnabled: true
                        }

                        // Resize grip at bottom-right (below webview)
                        Rectangle {
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            width: 14
                            height: 14
                            color: "#e0e0e0"
                            radius: 2

                            Text {
                                anchors.centerIn: parent
                                text: "◢"
                                font.pixelSize: 10
                                color: "#888"
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.SizeFDiagCursor
                                property point pressPos: Qt.point(0, 0)
                                property real origW: 0
                                property real origH: 0

                                onPressed: function(mouse) {
                                    pressPos = mapToItem(dictPopup.parent, mouse.x, mouse.y)
                                    origW = dictPopup.width
                                    origH = dictPopup.height
                                }
                                onPositionChanged: function(mouse) {
                                    var curr = mapToItem(dictPopup.parent, mouse.x, mouse.y)
                                    var dx = curr.x - pressPos.x
                                    var dy = curr.y - pressPos.y
                                    dictPopup.width = Math.max(dictPopup.minW, origW + dx)
                                    dictPopup.height = Math.max(dictPopup.minH, origH + dy)
                                }
                            }
                        }
                    }
                }
            }
        }

        // =====================================================================
        // RIGHT PANEL
        // =====================================================================
        Rectangle {
            id: sidePanel
            SplitView.preferredWidth: mainWindow.sidePanelVisible ? mainWindow.sidePanelWidth : 0
            SplitView.minimumWidth: mainWindow.sidePanelVisible ? mainWindow.minPanelWidth : 0
            SplitView.maximumWidth: mainWindow.sidePanelVisible ? 500 : 0
            visible: mainWindow.sidePanelVisible
            color: "#f8f9fa"

            ColumnLayout {
                anchors.fill: parent
                spacing: 0
                TabBar {
                    id: sideTabBar
                    Layout.fillWidth: true
                    TabButton { text: "Dictionary"; font.pixelSize: 11 }
                    TabButton { text: "Vocab"; font.pixelSize: 11 }
                    TabButton { text: "Notes"; font.pixelSize: 11 }
                }
                Label {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    text: ["Dictionary", "Vocabulary", "Notes"][sideTabBar.currentIndex]
                    color: "#999"; font.pixelSize: 12
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }
    }

    // =========================================================================
    // Wire controller signals to UI
    // =========================================================================
    Connections {
        target: appController

        function onTocChanged() {
            tocModel.clear()
            try {
                var toc = JSON.parse(appController.tocJson)
                for (var i = 0; i < toc.length; i++) {
                    tocModel.append({ title: toc[i].title, page: toc[i].page, level: toc[i].level })
                }
                if (toc.length > 0) navTabBar.currentIndex = 0
            } catch(e) { console.warn("TOC parse error:", e) }
        }

        function onPageHtmlChanged() {
            if (appController.pageHtml !== "") {
                pdfWebView.loadHtml(appController.pageHtml, "about:blank")
            }
        }

        function onDictionaryResultReady(jsonStr) {
            console.log("[DICT QML] Received result:", jsonStr)
            try {
                var data = JSON.parse(jsonStr)

                if (data.mode === "webview" && data.urls) {
                    dictHeaderLabel.text = data.word || "Dictionary"
                    dictWebView.dictUrls = data.urls
                    dictWebView.url = data.urls.en_vi
                    dictLangToggle.isVietnamese = true
                    dictLangToggle.text = "EN-VI"
                    dictPopup.visible = true
                    console.log("[DICT QML] Loading URL:", data.urls.en_vi)
                    return
                }

                if (data.error) {
                    dictHeaderLabel.text = data.word || ""
                    dictPopup.visible = true
                }
            } catch(err) {
                console.warn("[DICT QML] Parse error:", err)
            }
        }

        function onErrorOccurred(msg) {
            console.warn("Error:", msg)
        }
    }
}
