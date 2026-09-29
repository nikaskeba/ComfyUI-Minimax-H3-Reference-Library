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
