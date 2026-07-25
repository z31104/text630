(function () {
    "use strict";

    const app = document.getElementById("cameraApp");
    if (!app) {
        return;
    }

    const statusUrl = app.dataset.statusUrl;
    const streamUrl = app.dataset.streamUrl;
    const reloadUrl = app.dataset.reloadUrl;
    const stream = document.getElementById("cameraStream");
    const streamState = document.getElementById("cameraStreamState");
    const statusBadge = document.getElementById("cameraStatusBadge");
    const statusText = document.getElementById("cameraStatusText");
    const statusMessage = document.getElementById("cameraStatusMessage");
    const feedback = document.getElementById("cameraFeedback");
    const retryButton = document.getElementById("retryCameraButton");
    const reloadButton = document.getElementById("reloadFacesButton");

    let statusRequestRunning = false;
    let reloadRequestRunning = false;
    let statusTimer = null;

    function setFeedback(message, type) {
        if (!feedback) {
            return;
        }

        feedback.textContent = message;
        feedback.className = `camera-feedback ${type}`;
        feedback.hidden = false;
    }

    function setStreamState(title, message, hidden) {
        if (!streamState) {
            return;
        }

        const titleElement = streamState.querySelector("strong");
        const messageElement = streamState.querySelector("span");

        if (titleElement) {
            titleElement.textContent = title;
        }
        if (messageElement) {
            messageElement.textContent = message;
        }

        streamState.hidden = hidden;
    }

    function updateCameraStatus(data) {
        const connected = data && data.connected === true;
        const rawStatus = data && data.status ? String(data.status) : "Disconnected";
        const message = data && data.message ? String(data.message) : "未取得攝影機狀態說明。";

        if (statusText) {
            statusText.textContent = rawStatus;
        }
        if (statusMessage) {
            statusMessage.textContent = message;
        }
        if (statusBadge) {
            statusBadge.textContent = connected ? "攝影機已連線" : rawStatus === "Connecting" ? "連線確認中" : "攝影機離線";
            statusBadge.className = connected
                ? "camera-status-badge is-online"
                : rawStatus === "Connecting"
                    ? "camera-status-badge is-loading"
                    : "camera-status-badge is-offline";
        }

        if (!connected && rawStatus !== "Connecting") {
            setStreamState("攝影機離線", message, false);
        }
    }

    async function refreshCameraStatus() {
        if (statusRequestRunning || document.hidden) {
            return;
        }

        statusRequestRunning = true;

        try {
            const response = await fetch(statusUrl, { cache: "no-store" });
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.message || "狀態 API 回應失敗");
            }

            updateCameraStatus(data);
        } catch (error) {
            updateCameraStatus({
                connected: false,
                status: "Disconnected",
                message: "無法取得攝影機狀態，請確認服務是否正常。"
            });
        } finally {
            statusRequestRunning = false;
        }
    }

    function reconnectStream() {
        if (!stream || retryButton.disabled) {
            return;
        }

        retryButton.disabled = true;
        retryButton.textContent = "重新連線中…";
        setStreamState("攝影機載入中", "正在重新建立影像串流。", false);
        stream.src = `${streamUrl}?refresh=${Date.now()}`;

        window.setTimeout(function () {
            retryButton.disabled = false;
            retryButton.textContent = "重新連線串流";
        }, 1500);
    }

    async function reloadFaces() {
        if (reloadRequestRunning) {
            return;
        }

        reloadRequestRunning = true;
        reloadButton.disabled = true;
        reloadButton.setAttribute("aria-busy", "true");
        reloadButton.textContent = "重新載入中…";
        setFeedback("正在重新載入會員與 Visitor 人臉資料。", "is-loading");

        try {
            const response = await fetch(reloadUrl, {
                method: "POST",
                headers: { "Accept": "application/json" }
            });
            const data = await response.json();

            if (!response.ok || data.success !== true) {
                throw new Error(data.message || "人臉資料重新載入失敗");
            }

            const memberCount = Number.isFinite(Number(data.member_count))
                ? Number(data.member_count)
                : "—";
            const visitorCount = Number.isFinite(Number(data.visitor_count))
                ? Number(data.visitor_count)
                : "—";

            setFeedback(
                `載入成功：會員 ${memberCount} 筆、Visitor ${visitorCount} 筆。`,
                "is-success"
            );
        } catch (error) {
            setFeedback(error.message || "人臉資料重新載入失敗。", "is-error");
        } finally {
            reloadRequestRunning = false;
            reloadButton.disabled = false;
            reloadButton.removeAttribute("aria-busy");
            reloadButton.textContent = "重新載入人臉";
        }
    }

    if (stream) {
        stream.addEventListener("load", function () {
            setStreamState("", "", true);
        });

        stream.addEventListener("error", function () {
            setStreamState(
                "影像串流無法顯示",
                "請確認攝影機連線後再重新連線。",
                false
            );
        });
    }

    if (retryButton) {
        retryButton.addEventListener("click", reconnectStream);
    }

    if (reloadButton) {
        reloadButton.addEventListener("click", reloadFaces);
    }

    document.addEventListener("visibilitychange", function () {
        if (!document.hidden) {
            refreshCameraStatus();
        }
    });

    refreshCameraStatus();
    statusTimer = window.setInterval(refreshCameraStatus, 2000);

    window.addEventListener("beforeunload", function () {
        if (statusTimer) {
            window.clearInterval(statusTimer);
        }
    });
}());
