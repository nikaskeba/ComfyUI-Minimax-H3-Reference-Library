"""Lazy, type-agnostic branch selector for ComfyUI workflows."""

MAX_LANES = 16


class SkebaUniversalBypass:
    """Select original or processed values without evaluating the other branch."""

    @classmethod
    def INPUT_TYPES(cls):
        optional = {}
        for lane in range(1, MAX_LANES + 1):
            optional[f"original_{lane}"] = ("*", {"lazy": True})
            optional[f"processed_{lane}"] = ("*", {"lazy": True})

        return {
            "required": {
                "bypass": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "label_on": "BYPASS",
                        "label_off": "PROCESS",
                    },
                ),
            },
            "optional": optional,
            "hidden": {
                "prompt": "PROMPT",
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("*",) * MAX_LANES
    RETURN_NAMES = tuple(f"output_{lane}" for lane in range(1, MAX_LANES + 1))
    FUNCTION = "route"
    CATEGORY = "Skeba AI Nodes - Utilities"
    DESCRIPTION = (
        "Lazily selects up to 16 original or processed values. PROCESS evaluates "
        "only processed inputs; BYPASS evaluates only original inputs."
    )

    @staticmethod
    def _connected_output_lanes(prompt, unique_id):
        if not isinstance(prompt, dict) or unique_id is None:
            return set()

        node_id = str(unique_id)
        connected = set()
        for node in prompt.values():
            inputs = node.get("inputs", {}) if isinstance(node, dict) else {}
            for value in inputs.values():
                if (
                    isinstance(value, (list, tuple))
                    and len(value) == 2
                    and str(value[0]) == node_id
                    and isinstance(value[1], int)
                    and 0 <= value[1] < MAX_LANES
                ):
                    connected.add(value[1] + 1)
        return connected

    @classmethod
    def _active_lanes(cls, prompt, unique_id, values):
        lanes = cls._connected_output_lanes(prompt, unique_id)
        # PROMPT is always supplied by ComfyUI. The fallback makes the class
        # convenient to exercise directly without treating unused, dangling
        # inputs as active during a real graph execution.
        if not isinstance(prompt, dict):
            for lane in range(1, MAX_LANES + 1):
                if f"original_{lane}" in values or f"processed_{lane}" in values:
                    lanes.add(lane)
        return sorted(lanes)

    @classmethod
    def _validate_selected_inputs(cls, bypass, prompt, unique_id, values):
        branch = "original" if bypass else "processed"
        mode = "BYPASS" if bypass else "PROCESS"
        lanes = cls._active_lanes(prompt, unique_id, values)
        for lane in lanes:
            selected = f"{branch}_{lane}"
            if selected not in values:
                raise ValueError(
                    f"Universal Node Bypass lane {lane}: connect {selected} "
                    f"while the node is in {mode} mode."
                )
        return lanes, branch

    def check_lazy_status(self, bypass, prompt=None, unique_id=None, **kwargs):
        lanes, branch = self._validate_selected_inputs(
            bypass, prompt, unique_id, kwargs
        )
        return [
            f"{branch}_{lane}"
            for lane in lanes
            if kwargs[f"{branch}_{lane}"] is None
        ]

    def route(self, bypass, prompt=None, unique_id=None, **kwargs):
        lanes, branch = self._validate_selected_inputs(
            bypass, prompt, unique_id, kwargs
        )
        active = set(lanes)
        return tuple(
            kwargs.get(f"{branch}_{lane}") if lane in active else None
            for lane in range(1, MAX_LANES + 1)
        )
