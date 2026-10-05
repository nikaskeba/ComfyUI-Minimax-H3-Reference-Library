// One search query shared by the library type tabs and other open library windows.
const key = "skeba-library-search";
const bindings = new Map();
function update(value) {
    for (const [input, render] of bindings) {
        input.value = value;
        render();
    }
}
export function bindLibrarySearch(input, render) {
    input.value = localStorage.getItem(key) || "";
    bindings.set(input, render);
    input.addEventListener("input", () => {
        localStorage.setItem(key, input.value);
        update(input.value);
    });
}
window.addEventListener("storage", event => {
    if (event.key === key || event.key === null) update(localStorage.getItem(key) || "");
});
window.addEventListener("pageshow", () => update(localStorage.getItem(key) || ""));

// The collection is a shared filter; tabs only change the reference source.
const collectionKey = "skeba-library-collection";
const collectionBindings = new Map();
export function restoreLibraryCollection(input) {
    const value = localStorage.getItem(collectionKey) || "";
    if (value && ![...input.options].some(option => option.value === value)) {
        input.add(new Option(value, value));
    }
    input.value = value;
}
function updateCollections() {
    for (const [input, render] of collectionBindings) {
        restoreLibraryCollection(input);
        render();
    }
}
export function bindLibraryCollection(input, render) {
    collectionBindings.set(input, render);
    restoreLibraryCollection(input);
    input.addEventListener("change", () => {
        localStorage.setItem(collectionKey, input.value);
        updateCollections();
    });
}
window.addEventListener("storage", event => {
    if (event.key === collectionKey || event.key === null) updateCollections();
});
window.addEventListener("pageshow", updateCollections);
