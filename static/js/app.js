document.addEventListener("DOMContentLoaded", function () {
    animateProgressBars();
    animateChartBars();
    autoDismissFlashes();
    setupDropzones();
    setupConfirmButtons();
    setupSubmitLoadingState();
    initToolbars();
});

// Animate every .progress-fill from 0 to its real width, so bars visibly fill in.
function animateProgressBars() {
    document.querySelectorAll(".progress-fill").forEach(function (el) {
        var target = el.style.width;
        el.style.width = "0%";
        requestAnimationFrame(function () {
            setTimeout(function () {
                el.style.width = target;
            }, 60);
        });
    });
}

// Flash messages fade out on their own after a few seconds.
function autoDismissFlashes() {
    document.querySelectorAll(".flash").forEach(function (el) {
        setTimeout(function () {
            el.classList.add("dismissing");
            setTimeout(function () { el.remove(); }, 320);
        }, 4000);
    });
}

// Turn any file input wrapped in [data-dropzone] into a drag-and-drop zone
// with an image preview, without changing how the form actually submits.
function setupDropzones() {
    document.querySelectorAll("[data-dropzone]").forEach(function (zone) {
        var input = zone.querySelector("input[type=file]");
        if (!input) return;

        zone.addEventListener("click", function () { input.click(); });

        ["dragenter", "dragover"].forEach(function (evt) {
            zone.addEventListener(evt, function (e) {
                e.preventDefault();
                zone.classList.add("dragover");
            });
        });
        ["dragleave", "drop"].forEach(function (evt) {
            zone.addEventListener(evt, function (e) {
                e.preventDefault();
                zone.classList.remove("dragover");
            });
        });
        zone.addEventListener("drop", function (e) {
            if (e.dataTransfer.files.length) {
                input.files = e.dataTransfer.files;
                showPreview(zone, input.files);
            }
        });
        input.addEventListener("change", function () {
            if (input.files.length) showPreview(zone, input.files);
        });
    });
}

function showPreview(zone, fileList) {
    var previewEl = zone.querySelector(".preview");
    if (!previewEl) {
        previewEl = document.createElement("div");
        previewEl.className = "preview";
        zone.appendChild(previewEl);
    }
    previewEl.innerHTML = "";

    Array.prototype.forEach.call(fileList, function (file) {
        if (file.type && file.type.startsWith("image/")) {
            var img = document.createElement("img");
            img.src = URL.createObjectURL(file);
            previewEl.appendChild(img);
        }
    });
    var nameEl = document.createElement("div");
    nameEl.className = "file-name";
    var names = Array.prototype.map.call(fileList, function (f) { return f.name; }).join(", ");
    nameEl.textContent = "Selected: " + names;
    previewEl.appendChild(nameEl);
}

// Replace the plain browser confirm() with a small styled modal.
// Any element with data-confirm="message" submits its closest form
// only after the user clicks "Confirm" in the modal.
function setupConfirmButtons() {
    var overlay = document.getElementById("confirm-modal");
    if (!overlay) return;
    var messageEl = overlay.querySelector(".modal-message");
    var confirmBtn = overlay.querySelector(".modal-confirm");
    var cancelBtn = overlay.querySelector(".modal-cancel");
    var pendingForm = null;

    document.querySelectorAll("[data-confirm]").forEach(function (btn) {
        btn.addEventListener("click", function (e) {
            e.preventDefault();
            pendingForm = btn.closest("form");
            messageEl.textContent = btn.getAttribute("data-confirm");
            overlay.classList.add("open");
        });
    });

    cancelBtn.addEventListener("click", function () {
        overlay.classList.remove("open");
        pendingForm = null;
    });
    overlay.addEventListener("click", function (e) {
        if (e.target === overlay) { overlay.classList.remove("open"); pendingForm = null; }
    });
    confirmBtn.addEventListener("click", function () {
        overlay.classList.remove("open");
        if (pendingForm) pendingForm.submit();
    });
}

// Give the clicked submit button a brief "loading" look so it's clear
// something is happening during the page's full reload.
function setupSubmitLoadingState() {
    document.querySelectorAll("form").forEach(function (form) {
        form.addEventListener("submit", function () {
            var btn = form.querySelector("button[type=submit], button:not([type])");
            if (btn) btn.classList.add("is-loading");
        });
    });
}

// Animate the simple CSS bar chart from 0 up to its real height.
function animateChartBars() {
    document.querySelectorAll(".chart-bar").forEach(function (el) {
        var target = el.style.height;
        el.style.height = "0%";
        requestAnimationFrame(function () {
            setTimeout(function () { el.style.height = target; }, 60);
        });
    });
}

// Client-side search: <input data-filter-table="tableId"> hides table rows
// whose data-search attribute (or full row text) doesn't match the query.
// Client-side sort: <select data-sort-table="tableId"> with option values
// like "progress:desc" or "name:asc", matching a data-* attribute on each row.
function initToolbars() {
    document.querySelectorAll("[data-filter-table]").forEach(function (input) {
        var table = document.getElementById(input.getAttribute("data-filter-table"));
        if (!table) return;
        input.addEventListener("input", function () {
            var q = input.value.toLowerCase();
            table.querySelectorAll("tbody tr").forEach(function (row) {
                var text = (row.getAttribute("data-search") || row.textContent).toLowerCase();
                row.style.display = text.indexOf(q) === -1 ? "none" : "";
            });
        });
    });

    document.querySelectorAll("[data-sort-table]").forEach(function (select) {
        var table = document.getElementById(select.getAttribute("data-sort-table"));
        if (!table) return;
        select.addEventListener("change", function () {
            var parts = select.value.split(":");
            var field = parts[0], dir = parts[1];
            var tbody = table.querySelector("tbody");
            var rows = Array.prototype.slice.call(tbody.querySelectorAll("tr"));
            rows.sort(function (a, b) {
                var av = a.dataset[field] || "";
                var bv = b.dataset[field] || "";
                var an = parseFloat(av), bn = parseFloat(bv);
                var cmp = (!isNaN(an) && !isNaN(bn)) ? (an - bn) : av.localeCompare(bv);
                return dir === "desc" ? -cmp : cmp;
            });
            rows.forEach(function (r) { tbody.appendChild(r); });
        });
    });
}
