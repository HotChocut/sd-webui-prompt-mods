(function () {
    function root() { return typeof gradioApp === "function" ? gradioApp() : document; }
    function touch(input) {
        if (!input) return;
        if (typeof updateInput === "function") updateInput(input);
        else {
            input.dispatchEvent(new Event("input", {bubbles: true}));
            input.dispatchEvent(new Event("change", {bubbles: true}));
        }
    }
    function setChecked(id, checked) {
        const r = root(), visible = document.getElementById(id + "-visible-checkbox"), wrap = r.getElementById(id + "-checkbox"), hidden = wrap && wrap.querySelector("input");
        if (!visible || !hidden) return false;
        checked = !!checked;
        if (visible.checked !== checked) visible.click();
        visible.checked = hidden.checked = checked;
        touch(hidden);
        return true;
    }
    function apply() {
        document.querySelectorAll(".prompt-mods-default-enabled").forEach(function (node) {
            let tries = 0;
            const timer = setInterval(function () {
                if (setChecked(node.dataset.accordionId, node.dataset.enabled === "true") || ++tries > 60) clearInterval(timer);
            }, 100);
        });
    }
    if (typeof onUiLoaded === "function") onUiLoaded(apply);
    else document.addEventListener("DOMContentLoaded", apply);
})();
