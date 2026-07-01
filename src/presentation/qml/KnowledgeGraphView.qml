import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

/**
 * KnowledgeGraphView.qml - Knowledge Graph visualization with force-directed layout.
 *
 * Renders a visual graph showing Books, annotations, vocabulary, and tags
 * as connected nodes using a Canvas-based force-directed layout.
 * Supports node click navigation, graph filtering by tag/book, and
 * updates within 500ms of new data.
 *
 * Requirements: 9.1–9.5, 14.1
 */
Item {
    id: root

    // Reference to the knowledge graph controller (set via context property)
    property var graphController: null

    // Signals for navigation
    signal nodeNavigated(string nodeId, string entityType, string entityId)

    // Internal graph state
    property var nodes: []
    property var links: []
    property var nodePositions: ({})  // node_id -> {x, y, vx, vy}
    property bool simulationRunning: false
    property int simulationIterations: 0
    property int maxIterations: 150
    property real damping: 0.9
    property real repulsionStrength: 800
    property real attractionStrength: 0.005
    property real idealLinkLength: 120

    // Interaction state
    property string hoveredNodeId: ""
    property string selectedNodeId: ""
    property string draggedNodeId: ""
    property real dragOffsetX: 0
    property real dragOffsetY: 0

    // Node appearance configuration
    property var nodeColors: ({
        "book": "#1565c0",
        "annotation": "#2e7d32",
        "vocabulary": "#e65100",
        "note": "#6a1b9a"
    })
    property var nodeRadii: ({
        "book": 20,
        "annotation": 14,
        "vocabulary": 14,
        "note": 12
    })
    property var linkColors: ({
        "backlink": "#e53935",
        "same_book": "#90a4ae",
        "tag_shared": "#ffb300"
    })

    // Connect to controller signals
    Connections {
        target: graphController

        function onGraphChanged() {
            root.parseGraphData()
        }

        function onNodeClicked(nodeId, entityType, entityId) {
            root.nodeNavigated(nodeId, entityType, entityId)
        }
    }

    // Parse graph data from controller JSON properties
    function parseGraphData() {
        if (!graphController) return

        try {
            var nodesData = JSON.parse(graphController.nodesJson)
            var linksData = JSON.parse(graphController.linksJson)

            root.nodes = nodesData
            root.links = linksData

            initializePositions()
            startSimulation()
        } catch(e) {
            console.warn("KnowledgeGraphView: Failed to parse graph data:", e)
        }
    }

    // Initialize node positions randomly within the canvas area
    function initializePositions() {
        var positions = {}
        var centerX = graphCanvas.width / 2
        var centerY = graphCanvas.height / 2
        var spread = Math.min(graphCanvas.width, graphCanvas.height) * 0.35

        for (var i = 0; i < nodes.length; i++) {
            var node = nodes[i]
            // Check if we have an existing position to preserve
            if (nodePositions[node.id]) {
                positions[node.id] = nodePositions[node.id]
            } else {
                // Distribute in a circle with random offset
                var angle = (2 * Math.PI * i) / Math.max(nodes.length, 1)
                var radius = spread * (0.4 + Math.random() * 0.6)
                positions[node.id] = {
                    x: centerX + radius * Math.cos(angle),
                    y: centerY + radius * Math.sin(angle),
                    vx: 0,
                    vy: 0
                }
            }
        }

        nodePositions = positions
    }

    // Start the force-directed layout simulation
    function startSimulation() {
        simulationIterations = 0
        simulationRunning = true
        simulationTimer.start()
    }

    // One step of the force simulation
    function simulationStep() {
        if (!simulationRunning || nodes.length === 0) {
            simulationRunning = false
            simulationTimer.stop()
            graphCanvas.requestPaint()
            return
        }

        var positions = nodePositions
        var width = graphCanvas.width
        var height = graphCanvas.height

        // Calculate repulsive forces (nodes push each other away)
        for (var i = 0; i < nodes.length; i++) {
            var nodeA = nodes[i]
            var posA = positions[nodeA.id]
            if (!posA) continue

            for (var j = i + 1; j < nodes.length; j++) {
                var nodeB = nodes[j]
                var posB = positions[nodeB.id]
                if (!posB) continue

                var dx = posA.x - posB.x
                var dy = posA.y - posB.y
                var dist = Math.sqrt(dx * dx + dy * dy)
                if (dist < 1) dist = 1

                var force = repulsionStrength / (dist * dist)
                var fx = (dx / dist) * force
                var fy = (dy / dist) * force

                // Skip force application for dragged node
                if (draggedNodeId !== nodeA.id) {
                    posA.vx += fx
                    posA.vy += fy
                }
                if (draggedNodeId !== nodeB.id) {
                    posB.vx -= fx
                    posB.vy -= fy
                }
            }
        }

        // Calculate attractive forces along links (spring model)
        for (var k = 0; k < links.length; k++) {
            var link = links[k]
            var srcPos = positions[link.sourceNodeId]
            var tgtPos = positions[link.targetNodeId]
            if (!srcPos || !tgtPos) continue

            var ldx = tgtPos.x - srcPos.x
            var ldy = tgtPos.y - srcPos.y
            var ldist = Math.sqrt(ldx * ldx + ldy * ldy)
            if (ldist < 1) ldist = 1

            var displacement = ldist - idealLinkLength
            var lforce = attractionStrength * displacement
            var lfx = (ldx / ldist) * lforce
            var lfy = (ldy / ldist) * lforce

            if (draggedNodeId !== link.sourceNodeId) {
                srcPos.vx += lfx
                srcPos.vy += lfy
            }
            if (draggedNodeId !== link.targetNodeId) {
                tgtPos.vx -= lfx
                tgtPos.vy -= lfy
            }
        }

        // Center gravity (pull nodes toward center)
        var centerX = width / 2
        var centerY = height / 2
        var gravityStrength = 0.001

        for (var m = 0; m < nodes.length; m++) {
            var gNode = nodes[m]
            var gPos = positions[gNode.id]
            if (!gPos || draggedNodeId === gNode.id) continue

            gPos.vx += (centerX - gPos.x) * gravityStrength
            gPos.vy += (centerY - gPos.y) * gravityStrength
        }

        // Apply velocity with damping and boundary constraints
        var totalKineticEnergy = 0
        for (var n = 0; n < nodes.length; n++) {
            var uNode = nodes[n]
            var uPos = positions[uNode.id]
            if (!uPos || draggedNodeId === uNode.id) continue

            uPos.vx *= damping
            uPos.vy *= damping

            uPos.x += uPos.vx
            uPos.y += uPos.vy

            // Keep within bounds with padding
            var padding = 30
            uPos.x = Math.max(padding, Math.min(width - padding, uPos.x))
            uPos.y = Math.max(padding, Math.min(height - padding, uPos.y))

            totalKineticEnergy += uPos.vx * uPos.vx + uPos.vy * uPos.vy
        }

        nodePositions = positions
        simulationIterations++

        // Stop simulation when energy is low or max iterations reached
        if (totalKineticEnergy < 0.1 || simulationIterations >= maxIterations) {
            simulationRunning = false
            simulationTimer.stop()
        }

        graphCanvas.requestPaint()
    }

    // Simulation timer (60fps target)
    Timer {
        id: simulationTimer
        interval: 16
        repeat: true
        onTriggered: root.simulationStep()
    }

    // Find node at canvas coordinates
    function findNodeAt(mouseX, mouseY) {
        for (var i = nodes.length - 1; i >= 0; i--) {
            var node = nodes[i]
            var pos = nodePositions[node.id]
            if (!pos) continue

            var radius = nodeRadii[node.entityType] || 14
            var dx = mouseX - pos.x
            var dy = mouseY - pos.y
            if (dx * dx + dy * dy <= radius * radius) {
                return node
            }
        }
        return null
    }

    // Main layout
    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Toolbar with filters
        Rectangle {
            id: toolbar
            Layout.fillWidth: true
            Layout.preferredHeight: 48
            color: "#fafafa"
            border.color: "#e0e0e0"
            border.width: 1

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 12

                // Title
                Label {
                    text: qsTr("Knowledge Graph")
                    font.pixelSize: 14
                    font.bold: true
                    color: "#333333"
                }

                // Node/link count
                Label {
                    text: graphController
                        ? qsTr("%1 nodes, %2 links").arg(graphController.nodeCount).arg(graphController.linkCount)
                        : ""
                    font.pixelSize: 11
                    color: "#777777"
                }

                Item { Layout.fillWidth: true }

                // Tag filter
                ComboBox {
                    id: tagFilter
                    Layout.preferredWidth: 140
                    font.pixelSize: 11
                    model: [qsTr("All Tags")]
                    displayText: graphController && graphController.filterTag !== ""
                        ? graphController.filterTag
                        : qsTr("All Tags")

                    onActivated: function(index) {
                        if (graphController) {
                            if (index === 0) {
                                graphController.setFilterTag("")
                            }
                        }
                    }
                }

                // Tag input for manual filter
                TextField {
                    id: tagFilterInput
                    Layout.preferredWidth: 120
                    placeholderText: qsTr("Filter by tag...")
                    font.pixelSize: 11
                    selectByMouse: true

                    onAccepted: {
                        if (graphController) {
                            graphController.setFilterTag(text.trim())
                        }
                    }
                }

                // Book filter input
                TextField {
                    id: bookFilterInput
                    Layout.preferredWidth: 120
                    placeholderText: qsTr("Filter by book ID...")
                    font.pixelSize: 11
                    selectByMouse: true

                    onAccepted: {
                        if (graphController) {
                            graphController.setFilterBookId(text.trim())
                        }
                    }
                }

                // Clear filters button
                Button {
                    text: qsTr("Clear")
                    flat: true
                    font.pixelSize: 11
                    enabled: graphController && (graphController.filterTag !== "" || graphController.filterBookId !== "")
                    onClicked: {
                        tagFilterInput.text = ""
                        bookFilterInput.text = ""
                        if (graphController) {
                            graphController.clearFilters()
                        }
                    }
                    ToolTip.text: qsTr("Clear all filters")
                    ToolTip.visible: hovered
                }

                // Build graph button
                Button {
                    text: qsTr("Build")
                    flat: true
                    font.pixelSize: 11
                    onClicked: {
                        if (graphController) {
                            graphController.buildGraph()
                        }
                    }
                    ToolTip.text: qsTr("Build graph from existing data")
                    ToolTip.visible: hovered
                }

                // Refresh button
                Button {
                    text: qsTr("Refresh")
                    flat: true
                    font.pixelSize: 11
                    onClicked: {
                        if (graphController) {
                            graphController.refresh()
                        }
                    }
                }
            }
        }

        // Graph canvas area
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            Canvas {
                id: graphCanvas
                anchors.fill: parent

                onPaint: {
                    var ctx = getContext("2d")
                    ctx.clearRect(0, 0, width, height)

                    // Draw background
                    ctx.fillStyle = "#ffffff"
                    ctx.fillRect(0, 0, width, height)

                    // Draw links
                    for (var i = 0; i < links.length; i++) {
                        var link = links[i]
                        var srcPos = nodePositions[link.sourceNodeId]
                        var tgtPos = nodePositions[link.targetNodeId]
                        if (!srcPos || !tgtPos) continue

                        ctx.beginPath()
                        ctx.moveTo(srcPos.x, srcPos.y)
                        ctx.lineTo(tgtPos.x, tgtPos.y)
                        ctx.strokeStyle = linkColors[link.linkType] || "#cccccc"
                        ctx.lineWidth = (link.linkType === "backlink") ? 2 : 1
                        ctx.globalAlpha = (hoveredNodeId !== "" &&
                            hoveredNodeId !== link.sourceNodeId &&
                            hoveredNodeId !== link.targetNodeId) ? 0.2 : 0.7
                        ctx.stroke()
                        ctx.globalAlpha = 1.0
                    }

                    // Draw nodes
                    for (var j = 0; j < nodes.length; j++) {
                        var node = nodes[j]
                        var pos = nodePositions[node.id]
                        if (!pos) continue

                        var radius = nodeRadii[node.entityType] || 14
                        var color = nodeColors[node.entityType] || "#666666"
                        var isHovered = (hoveredNodeId === node.id)
                        var isSelected = (selectedNodeId === node.id)

                        // Dim non-hovered nodes when hovering
                        if (hoveredNodeId !== "" && !isHovered && !isConnectedToHovered(node.id)) {
                            ctx.globalAlpha = 0.3
                        }

                        // Node circle
                        ctx.beginPath()
                        ctx.arc(pos.x, pos.y, isHovered ? radius + 3 : radius, 0, 2 * Math.PI)
                        ctx.fillStyle = color
                        ctx.fill()

                        // Selection ring
                        if (isSelected) {
                            ctx.beginPath()
                            ctx.arc(pos.x, pos.y, radius + 5, 0, 2 * Math.PI)
                            ctx.strokeStyle = "#ff9800"
                            ctx.lineWidth = 2
                            ctx.stroke()
                        }

                        // Hover ring
                        if (isHovered) {
                            ctx.beginPath()
                            ctx.arc(pos.x, pos.y, radius + 3, 0, 2 * Math.PI)
                            ctx.strokeStyle = "#ffffff"
                            ctx.lineWidth = 2
                            ctx.stroke()
                        }

                        // Label
                        var label = node.label || ""
                        if (label.length > 15) label = label.substring(0, 15) + "..."
                        ctx.font = (isHovered ? "bold " : "") + "10px sans-serif"
                        ctx.textAlign = "center"
                        ctx.textBaseline = "top"
                        ctx.fillStyle = "#333333"
                        ctx.fillText(label, pos.x, pos.y + radius + 4)

                        ctx.globalAlpha = 1.0
                    }

                    // Loading indicator
                    if (graphController && graphController.isLoading) {
                        ctx.fillStyle = "rgba(255, 255, 255, 0.7)"
                        ctx.fillRect(0, 0, width, height)
                        ctx.font = "14px sans-serif"
                        ctx.textAlign = "center"
                        ctx.textBaseline = "middle"
                        ctx.fillStyle = "#333333"
                        ctx.fillText("Loading graph...", width / 2, height / 2)
                    }
                }
            }

            // Mouse interaction overlay
            MouseArea {
                id: graphMouseArea
                anchors.fill: parent
                hoverEnabled: true
                acceptedButtons: Qt.LeftButton | Qt.RightButton

                onPositionChanged: function(mouse) {
                    if (draggedNodeId !== "") {
                        // Drag node
                        var pos = nodePositions[draggedNodeId]
                        if (pos) {
                            pos.x = mouse.x - dragOffsetX
                            pos.y = mouse.y - dragOffsetY
                            pos.vx = 0
                            pos.vy = 0
                            nodePositions = nodePositions
                            graphCanvas.requestPaint()
                        }
                        return
                    }

                    // Hover detection
                    var foundNode = findNodeAt(mouse.x, mouse.y)
                    var newHoveredId = foundNode ? foundNode.id : ""
                    if (newHoveredId !== hoveredNodeId) {
                        hoveredNodeId = newHoveredId
                        cursorShape = hoveredNodeId !== "" ? Qt.PointingHandCursor : Qt.ArrowCursor
                        graphCanvas.requestPaint()
                    }
                }

                onPressed: function(mouse) {
                    if (mouse.button === Qt.LeftButton) {
                        var clickedNode = findNodeAt(mouse.x, mouse.y)
                        if (clickedNode) {
                            var pos = nodePositions[clickedNode.id]
                            if (pos) {
                                draggedNodeId = clickedNode.id
                                dragOffsetX = mouse.x - pos.x
                                dragOffsetY = mouse.y - pos.y
                            }
                        }
                    }
                }

                onReleased: function(mouse) {
                    if (mouse.button === Qt.LeftButton) {
                        if (draggedNodeId !== "") {
                            // If barely moved, treat as click
                            var pos = nodePositions[draggedNodeId]
                            if (pos) {
                                var movedDist = Math.abs(mouse.x - dragOffsetX - pos.x) +
                                                Math.abs(mouse.y - dragOffsetY - pos.y)
                                // Threshold for click vs drag (< 5px movement)
                                if (movedDist < 5 || draggedNodeId === hoveredNodeId) {
                                    handleNodeClick(draggedNodeId)
                                }
                            }
                            draggedNodeId = ""

                            // Resume simulation briefly after drag
                            if (!simulationRunning && nodes.length > 1) {
                                simulationIterations = maxIterations - 20
                                startSimulation()
                            }
                        }
                    }
                }

                onClicked: function(mouse) {
                    if (mouse.button === Qt.LeftButton && draggedNodeId === "") {
                        var clickedNode = findNodeAt(mouse.x, mouse.y)
                        if (clickedNode) {
                            handleNodeClick(clickedNode.id)
                        } else {
                            // Deselect when clicking empty space
                            selectedNodeId = ""
                            graphCanvas.requestPaint()
                        }
                    }
                }

                onDoubleClicked: function(mouse) {
                    var clickedNode = findNodeAt(mouse.x, mouse.y)
                    if (clickedNode && graphController) {
                        graphController.onNodeClicked(clickedNode.id)
                    }
                }
            }

            // Empty state
            Label {
                anchors.centerIn: parent
                text: qsTr("No knowledge graph data.\nClick \"Build\" to generate the graph\nfrom your books, annotations, and vocabulary.")
                font.pixelSize: 13
                color: "#999999"
                horizontalAlignment: Text.AlignHCenter
                visible: nodes.length === 0 && !(graphController && graphController.isLoading)
            }

            // Legend
            Rectangle {
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.margins: 12
                width: legendLayout.width + 24
                height: legendLayout.height + 16
                radius: 6
                color: "#f5f5f5"
                border.color: "#e0e0e0"
                border.width: 1
                opacity: 0.9
                visible: nodes.length > 0

                ColumnLayout {
                    id: legendLayout
                    anchors.centerIn: parent
                    spacing: 4

                    Label {
                        text: qsTr("Legend")
                        font.pixelSize: 10
                        font.bold: true
                        color: "#555555"
                    }

                    // Node type legend
                    Repeater {
                        model: [
                            { label: qsTr("Book"), color: "#1565c0" },
                            { label: qsTr("Annotation"), color: "#2e7d32" },
                            { label: qsTr("Vocabulary"), color: "#e65100" },
                            { label: qsTr("Note"), color: "#6a1b9a" }
                        ]

                        delegate: RowLayout {
                            spacing: 6
                            Rectangle {
                                width: 10
                                height: 10
                                radius: 5
                                color: modelData.color
                            }
                            Label {
                                text: modelData.label
                                font.pixelSize: 9
                                color: "#666666"
                            }
                        }
                    }

                    // Separator
                    Rectangle {
                        Layout.fillWidth: true
                        height: 1
                        color: "#e0e0e0"
                    }

                    // Link type legend
                    Repeater {
                        model: [
                            { label: qsTr("Backlink"), color: "#e53935" },
                            { label: qsTr("Same Book"), color: "#90a4ae" },
                            { label: qsTr("Shared Tag"), color: "#ffb300" }
                        ]

                        delegate: RowLayout {
                            spacing: 6
                            Rectangle {
                                width: 12
                                height: 2
                                color: modelData.color
                            }
                            Label {
                                text: modelData.label
                                font.pixelSize: 9
                                color: "#666666"
                            }
                        }
                    }
                }
            }
        }

        // Node detail bar (shown when a node is selected)
        Rectangle {
            id: nodeDetailBar
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? 44 : 0
            visible: selectedNodeId !== ""
            color: "#f0f4f8"
            border.color: "#d0d8e8"
            border.width: 1

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 12

                // Node type badge
                Rectangle {
                    width: 8
                    height: 8
                    radius: 4
                    color: {
                        var node = getSelectedNode()
                        return node ? (nodeColors[node.entityType] || "#666") : "#666"
                    }
                }

                Label {
                    text: {
                        var node = getSelectedNode()
                        if (!node) return ""
                        return node.label || ""
                    }
                    font.pixelSize: 12
                    font.bold: true
                    color: "#333333"
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }

                Label {
                    text: {
                        var node = getSelectedNode()
                        if (!node) return ""
                        return node.entityType || ""
                    }
                    font.pixelSize: 10
                    color: "#777777"
                }

                Button {
                    text: qsTr("Open")
                    flat: true
                    font.pixelSize: 11
                    onClicked: {
                        if (graphController && selectedNodeId !== "") {
                            graphController.onNodeClicked(selectedNodeId)
                        }
                    }
                    ToolTip.text: qsTr("Navigate to this entity")
                    ToolTip.visible: hovered
                }
            }
        }
    }

    // Helper: check if a node is connected to the hovered node
    function isConnectedToHovered(nodeId) {
        if (hoveredNodeId === "") return false
        for (var i = 0; i < links.length; i++) {
            var link = links[i]
            if ((link.sourceNodeId === hoveredNodeId && link.targetNodeId === nodeId) ||
                (link.targetNodeId === hoveredNodeId && link.sourceNodeId === nodeId)) {
                return true
            }
        }
        return false
    }

    // Helper: handle node selection on single click
    function handleNodeClick(nodeId) {
        selectedNodeId = nodeId
        graphCanvas.requestPaint()
    }

    // Helper: get the currently selected node data
    function getSelectedNode() {
        for (var i = 0; i < nodes.length; i++) {
            if (nodes[i].id === selectedNodeId) {
                return nodes[i]
            }
        }
        return null
    }

    // Initialize on component completion
    Component.onCompleted: {
        if (graphController) {
            parseGraphData()
        }
    }
}
