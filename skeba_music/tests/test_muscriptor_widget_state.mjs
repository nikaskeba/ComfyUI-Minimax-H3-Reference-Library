import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// Load the browser ES module as source so this test works without changing the pack's package type.
const source = readFileSync(new URL("../../web/muscriptor_widget_state.js", import.meta.url), "utf8");
const { FIELDS, restoredValues } = await import(`data:text/javascript,${encodeURIComponent(source)}`);
const instruments = ["drums", "clean_electric_guitar"];

const intact = ["large", "cuda", "auto", false, 1, 1, 1, true, false,
    "Skeba Music/muscriptor_grid", "Skip malformed", "", "drums", 0];
assert.deepEqual(restoredValues(intact, {}, instruments), intact);

const shifted = ["auto", false, 1, 1, 1, true, false,
    "Skeba Music/muscriptor_grid", "Skip malformed", "", "Skip malformed", "", "", ""];
assert.deepEqual(restoredValues(shifted, { instruments: "" }, instruments),
    ["medium", "auto", "auto", false, 1, 1, 1, true, false,
        "Skeba Music/muscriptor_grid", "Skip malformed", "", "", 0]);

assert.deepEqual(restoredValues([], Object.fromEntries(FIELDS.map((name, index) => [name, intact[index]])), instruments), intact);
console.log("MuScriptor widget restoration: 3 cases passed");
