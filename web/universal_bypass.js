import { app } from "../../scripts/app.js";


const NODE_NAME = "SkebaUniversalBypass";
const DISPLAY_NAME = "Universal Node Bypass";
const MAX_LANES = 16;
const WILDCARD = "*";

const inputName = (branch, lane) => `${branch}_${lane}`;
const outputName = (lane) => `output_${lane}`;
const isUniversalBypass = (node) => (
    node?.comfyClass === NODE_NAME
    || node?.type === NODE_NAME
    || node?.title === DISPLAY_NAME
);

const findInput = (node, name) => node.inputs?.find((slot) => slot.name === name);
const findOutput = (node, name) => node.outputs?.find((slot) => slot.name === name);

const graphLink = (id) => {
    if (id == null) return null;
    return app.graph?.links?.[id] ?? null;
};

const concreteType = (type) => {
    if (!type || type === WILDCARD || type === "*") return null;
    return type;
};

const endpointType = (link, endpoint) => {
    if (!link) return null;
    const nodeId = endpoint === "origin" ? link.origin_id : link.target_id;
    const slotIndex = endpoint === "origin" ? link.origin_slot : link.target_slot;
    const node = app.graph?.getNodeById?.(nodeId);
    const slot = endpoint === "origin" ? node?.outputs?.[slotIndex] : node?.inputs?.[slotIndex];
    return concreteType(slot?.type);
};

const resolveLinkType = (link) => (
    concreteType(link?.type)
    ?? endpointType(link, "origin")
    ?? endpointType(link, "target")
);

const laneLinks = (node, lane) => {
    const links = [];
    for (const branch of ["original", "processed"]) {
        const id = findInput(node, inputName(branch, lane))?.link;
        const link = graphLink(id);
        if (link) links.push(link);
    }
    for (const id of findOutput(node, outputName(lane))?.links ?? []) {
        const link = graphLink(id);
        if (link) links.push(link);
    }
    return links;
};

const laneIsConnected = (node, lane) => laneLinks(node, lane).length > 0;

const showLimitMessage = (node) => {
    if (node._skebaBypassLimitShown) return;
    node._skebaBypassLimitShown = true;
    app.extensionManager?.toast?.add?.({
        severity: "info",
        summary: "Universal Node Bypass",
        detail: "Maximum of 16 connection lanes reached.",
        life: 4000,
    });
};

const addLane = (node, lane, type = WILDCARD) => {
    if (!findInput(node, inputName("original", lane))) {
        node.addInput(inputName("original", lane), type);
    }
    if (!findInput(node, inputName("processed", lane))) {
        node.addInput(inputName("processed", lane), type);
    }
    if (!findOutput(node, outputName(lane))) {
        node.addOutput(outputName(lane), type);
    }
};

const removeLane = (node, lane) => {
    const outputIndex = node.outputs?.findIndex((slot) => slot.name === outputName(lane)) ?? -1;
    if (outputIndex >= 0) node.removeOutput(outputIndex);

    for (const branch of ["processed", "original"]) {
        const index = node.inputs?.findIndex(
            (slot) => slot.name === inputName(branch, lane),
        ) ?? -1;
        if (index >= 0) node.removeInput(index);
    }
};

const setVisibleLaneCount = (node, count) => {
    const wanted = Math.max(1, Math.min(MAX_LANES, count));
    const types = node.properties?.skeba_bypass_lane_types ?? {};
    for (let lane = 1; lane <= wanted; lane += 1) {
        addLane(node, lane, types[lane] ?? WILDCARD);
    }
    for (let lane = MAX_LANES; lane > wanted; lane -= 1) {
        if (!laneIsConnected(node, lane)) removeLane(node, lane);
    }
    node.properties ??= {};
    node.properties.skeba_bypass_lane_count = wanted;
};

const synchronizeLaneType = (node, lane) => {
    const links = laneLinks(node, lane);
    const saved = node.properties?.skeba_bypass_lane_types?.[lane];
    const type = links.map(resolveLinkType).find(Boolean)
        ?? (links.length ? concreteType(saved) : null)
        ?? WILDCARD;

    for (const branch of ["original", "processed"]) {
        const input = findInput(node, inputName(branch, lane));
        if (input) input.type = type;
    }
    const output = findOutput(node, outputName(lane));
    if (output) output.type = type;
    for (const link of links) {
        if (!concreteType(link.type) && type !== WILDCARD) link.type = type;
    }

    node.properties ??= {};
    node.properties.skeba_bypass_lane_types ??= {};
    if (type === WILDCARD) {
        delete node.properties.skeba_bypass_lane_types[lane];
    } else {
        node.properties.skeba_bypass_lane_types[lane] = type;
    }
};

const refreshLanes = (node) => {
    if (node._skebaBypassRefreshing) return;
    node._skebaBypassRefreshing = true;
    try {
        let highestConnected = 0;
        for (let lane = 1; lane <= MAX_LANES; lane += 1) {
            if (laneIsConnected(node, lane)) highestConnected = lane;
        }

        const visible = Math.min(MAX_LANES, Math.max(1, highestConnected + 1));
        setVisibleLaneCount(node, visible);
        for (let lane = 1; lane <= visible; lane += 1) {
            synchronizeLaneType(node, lane);
        }

        if (highestConnected === MAX_LANES) showLimitMessage(node);
        else node._skebaBypassLimitShown = false;

        node.setSize(node.computeSize());
        node.setDirtyCanvas(true, true);
    } finally {
        node._skebaBypassRefreshing = false;
    }
};


app.registerExtension({
    name: "SkebaAI.UniversalNodeBypass",
    nodeCreated(node) {
        if (!isUniversalBypass(node)) return;
        node.properties ??= {};
        setTimeout(() => {
            setVisibleLaneCount(node, 1);
            refreshLanes(node);
        }, 0);
    },
    loadedGraphNode(node) {
        if (!isUniversalBypass(node)) return;
        setTimeout(() => refreshLanes(node), 0);
    },
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (
            nodeData.name !== NODE_NAME
            && nodeData.name !== DISPLAY_NAME
            && nodeData.display_name !== DISPLAY_NAME
            && nodeData.category !== "Skeba AI Nodes - Utilities"
        ) return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated?.apply(this, arguments);
            this.properties ??= {};
            setTimeout(() => {
                setVisibleLaneCount(this, 1);
                refreshLanes(this);
            }, 0);
            return result;
        };

        const onAdded = nodeType.prototype.onAdded;
        nodeType.prototype.onAdded = function () {
            const result = onAdded?.apply(this, arguments);
            setTimeout(() => {
                const savedCount = this.properties?.skeba_bypass_lane_count ?? 1;
                setVisibleLaneCount(this, savedCount);
                refreshLanes(this);
            }, 0);
            return result;
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (info) {
            const result = onConfigure?.apply(this, arguments);
            const savedCount = info?.properties?.skeba_bypass_lane_count ?? 1;
            setVisibleLaneCount(this, savedCount);
            setTimeout(() => refreshLanes(this), 0);
            return result;
        };

        const onConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function () {
            const result = onConnectionsChange?.apply(this, arguments);
            setTimeout(() => refreshLanes(this), 0);
            return result;
        };

        const onSerialize = nodeType.prototype.onSerialize;
        nodeType.prototype.onSerialize = function (info) {
            refreshLanes(this);
            const result = onSerialize?.apply(this, arguments);
            info.properties ??= {};
            info.properties.skeba_bypass_lane_count = this.properties.skeba_bypass_lane_count;
            info.properties.skeba_bypass_lane_types = {
                ...this.properties.skeba_bypass_lane_types,
            };
            return result;
        };
    },
});
