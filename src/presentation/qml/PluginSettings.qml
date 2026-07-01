import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Dialogs 1.3

/**
 * PluginSettings.qml - Settings panel for managing installed plugins.
 *
 * Displays a list of installed plugins with their status (enabled/disabled),
 * version, description, hooks, and permissions. Supports enabling, disabling,
 * installing, and uninstalling plugins.
 *
 * Requirements: 11.1–11.6
 */
Item {
    id: root

    // Reference to the plugin controller (set via context property)
    property var pluginController: null

    // Connect to controller error signal
    Connections {
        target: pluginController
        function onErrorOccurred(message) {
            errorLabel.text = message
            errorLabel.visible = true
            errorTimer.restart()
        }
        function onPluginInstalled(pluginId) {
            statusLabel.text = qsTr("Plugin '%1' installed successfully").arg(pluginId)
            statusLabel.visible = true
            statusTimer.restart()
        }
        function onPluginUninstalled(pluginId) {
            statusLabel.text = qsTr("Plugin '%1' uninstalled").arg(pluginId)
            statusLabel.visible = true
            statusTimer.restart()
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Header
        Rectangle {
            Layout.fillWidth: true
            height: 52
            color: "#fafafa"
            border.color: "#e0e0e0"
            border.width: 1

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 16
                spacing: 12

                Label {
                    text: qsTr("Plugins")
                    font.pixelSize: 16
                    font.bold: true
                    color: "#333333"
                    Layout.fillWidth: true
                }

                // Plugin count badge
                Label {
                    text: pluginController ? pluginController.pluginCount.toString() + qsTr(" installed") : "0"
                    font.pixelSize: 11
                    color: "#666666"
                    padding: 4
                    background: Rectangle {
                        radius: 8
                        color: "#e8e8e8"
                    }
                }

                // Enabled count
                Label {
                    text: pluginController ? pluginController.enabledCount.toString() + qsTr(" active") : "0"
                    font.pixelSize: 11
                    color: "#2e7d32"
                    padding: 4
                    background: Rectangle {
                        radius: 8
                        color: "#e8f5e9"
                    }
                }

                // Install button
                Button {
                    id: installButton
                    text: qsTr("Install Plugin...")
                    font.pixelSize: 11
                    highlighted: true
                    onClicked: folderDialog.open()
                }

                // Refresh button
                Button {
                    text: "\u21BB"
                    flat: true
                    font.pixelSize: 14
                    implicitWidth: 32
                    implicitHeight: 32
                    onClicked: {
                        if (pluginController) {
                            pluginController.discoverPlugins()
                        }
                    }
                    ToolTip.text: qsTr("Refresh plugin list")
                    ToolTip.visible: hovered
                }
            }
        }

        // Status/Error messages
        Rectangle {
            id: statusBar
            Layout.fillWidth: true
            height: (errorLabel.visible || statusLabel.visible) ? 32 : 0
            color: errorLabel.visible ? "#fce4ec" : "#e8f5e9"
            border.color: errorLabel.visible ? "#ef9a9a" : "#a5d6a7"
            border.width: errorLabel.visible || statusLabel.visible ? 1 : 0
            clip: true

            Behavior on height { NumberAnimation { duration: 150 } }

            Label {
                id: errorLabel
                anchors.centerIn: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 16
                font.pixelSize: 11
                color: "#c62828"
                visible: false
            }

            Label {
                id: statusLabel
                anchors.centerIn: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 16
                font.pixelSize: 11
                color: "#2e7d32"
                visible: false
            }

            Timer {
                id: errorTimer
                interval: 5000
                onTriggered: errorLabel.visible = false
            }

            Timer {
                id: statusTimer
                interval: 3000
                onTriggered: statusLabel.visible = false
            }
        }

        // Plugin list
        ListView {
            id: pluginListView
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 1

            model: pluginController ? pluginController.pluginModel : null

            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            delegate: Rectangle {
                id: pluginDelegate
                width: pluginListView.width
                height: pluginContent.height + 20
                color: pluginMouseArea.containsMouse ? "#f5f8ff" : "transparent"
                border.color: pluginMouseArea.containsMouse ? "#d0d8e8" : "#f0f0f0"
                border.width: 1

                MouseArea {
                    id: pluginMouseArea
                    anchors.fill: parent
                    hoverEnabled: true
                    propagateComposedEvents: true
                    onClicked: function(mouse) {
                        detailDialog.pluginId = model.pluginId
                        detailDialog.pluginName = model.name
                        detailDialog.pluginVersion = model.version
                        detailDialog.pluginDescription = model.description
                        detailDialog.pluginHooks = model.hooks
                        detailDialog.pluginPermissions = model.permissions
                        detailDialog.pluginEnabled = model.enabled
                        detailDialog.pluginError = model.error
                        detailDialog.open()
                    }
                }

                ColumnLayout {
                    id: pluginContent
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 12
                    spacing: 6

                    // Header row: name + version + status + toggle
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        // Plugin name
                        Label {
                            text: model.name || ""
                            font.pixelSize: 13
                            font.bold: true
                            color: model.error ? "#c62828" : "#222222"
                        }

                        // Version badge
                        Label {
                            text: "v" + (model.version || "?")
                            font.pixelSize: 10
                            color: "#888888"
                            padding: 2
                            background: Rectangle {
                                radius: 4
                                color: "#f0f0f0"
                            }
                        }

                        Item { Layout.fillWidth: true }

                        // Status indicator
                        Rectangle {
                            width: statusText.width + 12
                            height: 20
                            radius: 10
                            color: {
                                if (model.error) return "#fce4ec"
                                if (model.enabled) return "#e8f5e9"
                                return "#f5f5f5"
                            }
                            border.color: {
                                if (model.error) return "#ef9a9a"
                                if (model.enabled) return "#a5d6a7"
                                return "#e0e0e0"
                            }
                            border.width: 1

                            Label {
                                id: statusText
                                anchors.centerIn: parent
                                text: {
                                    if (model.error) return qsTr("Error")
                                    if (model.enabled) return qsTr("Enabled")
                                    return qsTr("Disabled")
                                }
                                font.pixelSize: 10
                                font.bold: true
                                color: {
                                    if (model.error) return "#c62828"
                                    if (model.enabled) return "#2e7d32"
                                    return "#666666"
                                }
                            }
                        }

                        // Enable/disable toggle
                        Switch {
                            checked: model.enabled
                            enabled: !model.error
                            onToggled: {
                                if (pluginController) {
                                    pluginController.togglePlugin(model.pluginId)
                                }
                            }
                            ToolTip.text: model.enabled ? qsTr("Disable plugin") : qsTr("Enable plugin")
                            ToolTip.visible: hovered
                        }
                    }

                    // Description
                    Label {
                        Layout.fillWidth: true
                        text: model.description || qsTr("No description available")
                        font.pixelSize: 11
                        color: "#555555"
                        wrapMode: Text.WordWrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                    }

                    // Hooks row
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        visible: model.hooks !== ""

                        Label {
                            text: qsTr("Hooks:")
                            font.pixelSize: 10
                            color: "#888888"
                        }

                        Label {
                            text: model.hooks || ""
                            font.pixelSize: 10
                            color: "#1565c0"
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                    }

                    // Error message
                    Label {
                        Layout.fillWidth: true
                        text: model.error || ""
                        font.pixelSize: 10
                        color: "#c62828"
                        wrapMode: Text.WordWrap
                        visible: model.error !== ""
                    }
                }
            }

            // Empty state
            Label {
                anchors.centerIn: parent
                text: qsTr("No plugins installed.\nClick 'Install Plugin...' to add plugins.")
                font.pixelSize: 13
                color: "#999999"
                horizontalAlignment: Text.AlignHCenter
                visible: pluginListView.count === 0
            }
        }
    }

    // Plugin detail dialog
    Dialog {
        id: detailDialog
        anchors.centerIn: parent
        width: Math.min(root.width - 40, 450)
        title: qsTr("Plugin Details")
        modal: true
        standardButtons: Dialog.Close

        property string pluginId: ""
        property string pluginName: ""
        property string pluginVersion: ""
        property string pluginDescription: ""
        property string pluginHooks: ""
        property string pluginPermissions: ""
        property bool pluginEnabled: false
        property string pluginError: ""

        ColumnLayout {
            anchors.fill: parent
            spacing: 12

            // Name and version
            RowLayout {
                spacing: 8
                Label {
                    text: detailDialog.pluginName
                    font.pixelSize: 15
                    font.bold: true
                    color: "#222222"
                }
                Label {
                    text: "v" + detailDialog.pluginVersion
                    font.pixelSize: 12
                    color: "#666666"
                }
            }

            // Description
            Label {
                Layout.fillWidth: true
                text: detailDialog.pluginDescription || qsTr("No description available")
                font.pixelSize: 12
                color: "#444444"
                wrapMode: Text.WordWrap
            }

            // Separator
            Rectangle {
                Layout.fillWidth: true
                height: 1
                color: "#e0e0e0"
            }

            // Hooks
            ColumnLayout {
                spacing: 4
                Label {
                    text: qsTr("Registered Hooks:")
                    font.pixelSize: 11
                    font.bold: true
                    color: "#555555"
                }
                Label {
                    text: detailDialog.pluginHooks || qsTr("None")
                    font.pixelSize: 11
                    color: "#1565c0"
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }

            // Permissions
            ColumnLayout {
                spacing: 4
                Label {
                    text: qsTr("Permissions:")
                    font.pixelSize: 11
                    font.bold: true
                    color: "#555555"
                }
                Label {
                    text: detailDialog.pluginPermissions || qsTr("None required")
                    font.pixelSize: 11
                    color: "#e65100"
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }

            // Error (if any)
            ColumnLayout {
                spacing: 4
                visible: detailDialog.pluginError !== ""
                Label {
                    text: qsTr("Error:")
                    font.pixelSize: 11
                    font.bold: true
                    color: "#c62828"
                }
                Label {
                    text: detailDialog.pluginError
                    font.pixelSize: 11
                    color: "#c62828"
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }

            // Action buttons
            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Button {
                    text: detailDialog.pluginEnabled ? qsTr("Disable") : qsTr("Enable")
                    enabled: detailDialog.pluginError === ""
                    onClicked: {
                        if (pluginController) {
                            pluginController.togglePlugin(detailDialog.pluginId)
                            detailDialog.pluginEnabled = !detailDialog.pluginEnabled
                        }
                    }
                }

                Item { Layout.fillWidth: true }

                Button {
                    text: qsTr("Uninstall")
                    font.pixelSize: 11
                    onClicked: {
                        uninstallDialog.pluginId = detailDialog.pluginId
                        uninstallDialog.pluginName = detailDialog.pluginName
                        uninstallDialog.open()
                        detailDialog.close()
                    }

                    contentItem: Label {
                        text: parent.text
                        font.pixelSize: 11
                        color: "#c62828"
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }
        }
    }

    // Uninstall confirmation dialog
    Dialog {
        id: uninstallDialog
        anchors.centerIn: parent
        width: Math.min(root.width - 40, 340)
        title: qsTr("Uninstall Plugin")
        modal: true
        standardButtons: Dialog.Yes | Dialog.No

        property string pluginId: ""
        property string pluginName: ""

        Label {
            anchors.fill: parent
            text: qsTr("Are you sure you want to uninstall \"%1\"?\nThis will remove the plugin and all its files.").arg(uninstallDialog.pluginName)
            font.pixelSize: 12
            color: "#444444"
            wrapMode: Text.WordWrap
        }

        onAccepted: {
            if (pluginController) {
                pluginController.uninstallPlugin(uninstallDialog.pluginId)
            }
        }
    }

    // Folder dialog for plugin installation
    FileDialog {
        id: folderDialog
        title: qsTr("Select Plugin Directory")
        selectFolder: true
        onAccepted: {
            if (pluginController) {
                // Convert file URL to path string
                var path = fileUrl.toString()
                if (path.startsWith("file:///")) {
                    path = path.substring(8)  // Remove file:/// prefix
                }
                pluginController.installPlugin(path)
            }
        }
    }
}
