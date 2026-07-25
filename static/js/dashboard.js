(function () {
    "use strict";

    const filterForm = document.getElementById("dashboardFilters");
    const rows = Array.from(document.querySelectorAll("[data-dashboard-row]"));
    const subjectFilter = document.getElementById("dashboardSubjectFilter");
    const emptyState = document.getElementById("dashboardFilterEmpty");
    const resultCount = document.getElementById("dashboardResultCount");
    const refreshButton = document.getElementById("dashboardRefreshButton");
    const updatedAt = document.getElementById("dashboardUpdatedAt");

    function normalizedValue(element) {
        return element ? element.value.trim().toLowerCase() : "";
    }

    function matchingRows() {
        const selectedSubject = normalizedValue(subjectFilter);

        return rows.filter(function (row) {
            return !selectedSubject || row.dataset.identity === selectedSubject;
        });
    }

    function renderRows() {
        const matchedRows = matchingRows();

        rows.forEach(function (row) {
            row.hidden = true;
        });

        matchedRows.forEach(function (row) {
            row.hidden = false;
        });

        if (emptyState) {
            emptyState.hidden = matchedRows.length !== 0 || rows.length === 0;
        }

        if (resultCount) {
            resultCount.textContent = matchedRows.length
                ? `共 ${matchedRows.length} 筆`
                : "";
        }
    }

    if (updatedAt) {
        updatedAt.textContent = `頁面更新：${new Date().toLocaleString("zh-TW")}`;
    }

    if (filterForm) {
        filterForm.addEventListener("input", function () {
            renderRows();
        });
    }

    if (refreshButton) {
        refreshButton.addEventListener("click", function () {
            refreshButton.disabled = true;
            refreshButton.textContent = "重新整理中…";
            window.location.reload();
        });
    }

    renderRows();
}());
