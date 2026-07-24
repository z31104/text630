let LIFF_ID = "";

const spinWheel = document.getElementById("spinWheel");
const spinButton = document.getElementById("spinButton");
const lotteryResult = document.getElementById("lotteryResult");
const registerForm = document.getElementById("registerForm");
const registerButton = document.getElementById("registerButton");
const registerResult = document.getElementById("registerResult");
const lineUserIdInput = document.getElementById("line_user_id");
const idTokenInput = document.getElementById("id_token");
const lineHint = document.getElementById("lineHint");
const faceImageInput = document.getElementById("face_image");
const facePreview = document.getElementById("facePreview");
const clearFaceImageButton = document.getElementById("clearFaceImage");
const lotteryPrizeCard = document.getElementById("lotteryPrizeCard");
const lotteryPrizeName = document.getElementById("lotteryPrizeName");
const lotteryPrizeDetail = document.getElementById("lotteryPrizeDetail");
const lotteryQrCode = document.getElementById("lotteryQrCode");
const lotteryQrWrap = lotteryQrCode ? lotteryQrCode.closest(".lottery-qr-wrap") : null;
const lotteryConfetti = document.getElementById("lotteryConfetti");

let registerSuccess = false;
let registeredMember = null;
let isSpinning = false;
let isDrawing = false;
let lotteryCompleted = false;
let currentRotation = 0;

const prizes = [
    { id: "WELCOME_50", name: "$50 折價券" },
    { id: "WELCOME_10_OFF", name: "9 折優惠" },
    { id: "WELCOME_200", name: "$200 折價券" },
    { id: "WELCOME_GIFT", name: "小禮品" },
    { id: "WELCOME_FREE_SHIP", name: "免運券" },
    { id: "WELCOME_RETRY", name: "再抽一次" }
];

// TODO: 以下 prize_code 暫時沿用前端 prizes 的 id，需與資料庫組確認正式值。
const prizeIndexMap = {
    WELCOME_50: 0,
    WELCOME_10_OFF: 1,
    WELCOME_200: 2,
    WELCOME_GIFT: 3,
    WELCOME_FREE_SHIP: 4,
    WELCOME_RETRY: 5
};

function getPrizeIndex(prize) {
    if (!prize || !prize.prize_code) {
        throw new Error("後端未提供獎品代碼 prize_code");
    }

    const index = prizeIndexMap[prize.prize_code];

    if (typeof index !== "number") {
        throw new Error(`找不到獎品對應位置：${prize.prize_name || prize.prize_code}`);
    }

    return index;
}

function setLineHint(message, type = "") {
    if (!lineHint) {
        return;
    }

    lineHint.textContent = message;
    lineHint.className = type ? `form-hint ${type}` : "form-hint";
}

function showRegisterResult(message, type) {
    if (!registerResult) {
        return;
    }

    registerResult.textContent = message;
    registerResult.hidden = false;
    registerResult.className = `register-result ${type}`;
}

function setLineUserIdFromQuery() {
    const params = new URLSearchParams(window.location.search);
    const queryLineUserId = params.get("line_user_id") || params.get("userId");

    if (!queryLineUserId || !lineUserIdInput) {
        return false;
    }

    lineUserIdInput.value = queryLineUserId.trim();
    setLineHint("已帶入 LINE User ID，可以完成註冊。", "success");
    return true;
}

function initLiffProfile() {
    // 注意：line_user_id 有值不代表已經拿得到 LIFF ID Token，
    // 官方帳號的註冊連結本身就會帶 line_user_id 這個查詢參數，
    // 所以這裡即使已經帶入 line_user_id，還是要繼續往下走 LIFF 登入流程，
    // 否則後端 _verify_line_id_token() 會因為缺少 id_token 一律擋下註冊。
    const hasQueryLineUserId = setLineUserIdFromQuery();

    if (typeof liff === "undefined") {
        if (!hasQueryLineUserId) {
            setLineHint("目前不是從 LINE LIFF 開啟，請從 LINE 註冊連結進入。", "warning");
        }
        return;
    }

    fetch("/line/config")
        .then(function (res) {
            return res.json();
        })
        .then(function (config) {
            LIFF_ID = config.liff_id || "";

            if (!LIFF_ID) {
                setLineHint("LINE LIFF 尚未設定，請聯絡管理員設定 LIFF_ID。", "error");
                return Promise.reject(new Error("LIFF_ID 未設定"));
            }

            return liff.init({ liffId: LIFF_ID });
        })
        .then(function () {
            if (!liff.isLoggedIn()) {
                liff.login({ redirectUri: window.location.href });
                return null;
            }

            if (idTokenInput) {
                idTokenInput.value = liff.getIDToken() || "";
            }

            return liff.getProfile();
        })
        .then(function (profile) {
            if (!profile || !lineUserIdInput) {
                return;
            }

            lineUserIdInput.value = profile.userId;
            setLineHint("已取得 LINE User ID，可以完成註冊。", "success");
        })
        .catch(function (error) {
            console.error("LIFF 初始化失敗", error);
            if (LIFF_ID && (!lineUserIdInput || !lineUserIdInput.value.trim())) {
                setLineHint("無法取得 LINE User ID，請從 LINE 官方帳號的註冊連結重新開啟。", "error");
            }
        });
}

function resetRegisterButton() {
    if (!registerButton || registerSuccess) {
        return;
    }

    registerButton.disabled = false;
    registerButton.textContent = "完成註冊";
}

function getSelectedPreferences() {
    return Array.from(document.querySelectorAll('input[name="preference"]:checked'))
        .map(function (checkbox) {
            return checkbox.value;
        });
}

function resetFacePreview() {
    if (facePreview) {
        facePreview.hidden = true;
        facePreview.removeAttribute("src");
    }

    if (clearFaceImageButton) {
        clearFaceImageButton.hidden = true;
    }
}

function getRegisteredMemberId() {
    if (!registeredMember) {
        return null;
    }

    return (
        registeredMember.member_id ||
        registeredMember.id ||
        registeredMember.memberId ||
        null
    );
}

async function requestLotteryDraw(memberId) {
    if (!memberId) {
        throw new Error("找不到會員編號，請先完成會員註冊");
    }

    const response = await fetch("/api/lottery/draw", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            member_id: memberId
        })
    });

    let result;

    try {
        result = await response.json();
    } catch (error) {
        throw new Error("伺服器回傳格式錯誤");
    }

    if (!result || typeof result !== "object") {
        throw new Error("伺服器回傳格式錯誤");
    }

    if (!response.ok && result.already_completed !== true) {
        throw new Error(result.message || "抽獎失敗");
    }

    return result;
}

function buildPrizePayload(prize) {
    const memberId = getRegisteredMemberId();
    const prizeCode = prize.prize_code || prize.id || null;
    const prizeName = prize.prize_name || prize.name || null;

    return JSON.stringify({
        type: "welcome_lottery_prize",
        member_id: memberId,
        record_id: prize.record_id ?? null,
        prize_id: prizeCode,
        prize_code: prizeCode,
        prize_name: prizeName,
        line_user_id: lineUserIdInput ? lineUserIdInput.value.trim() || null : null,
        issued_at: new Date().toISOString()
    });
}

function escapeQrPayloadUnicode(payload) {
    return payload.replace(/[^\x00-\x7F]/g, function (character) {
        return `\\u${character.charCodeAt(0).toString(16).padStart(4, "0")}`;
    });
}

function renderPrizeQrCode(payload) {
    if (!lotteryQrCode) {
        return;
    }

    lotteryQrCode.innerHTML = "";

    if (typeof QRCode !== "undefined") {
        try {
            new QRCode(lotteryQrCode, {
                text: escapeQrPayloadUnicode(payload),
                width: 132,
                height: 132,
                colorDark: "#1f2937",
                colorLight: "#ffffff",
                correctLevel: QRCode.CorrectLevel.M
            });
            return;
        } catch (error) {
            console.warn("本機 QR Code 產生失敗，改用備援服務", error);
            lotteryQrCode.innerHTML = "";
        }
    }

    const fallbackImage = document.createElement("img");
    fallbackImage.src = `https://api.qrserver.com/v1/create-qr-code/?size=132x132&data=${encodeURIComponent(payload)}`;
    fallbackImage.alt = "中獎兌換 QR Code";
    lotteryQrCode.appendChild(fallbackImage);
}

function clearPrizeQrCode() {
    if (lotteryQrCode) {
        lotteryQrCode.innerHTML = "";
    }

    if (lotteryQrWrap) {
        lotteryQrWrap.hidden = true;
    }
}

function showPrizeResult(prize, qrCodeUrl = null) {
    const payload = qrCodeUrl || buildPrizePayload(prize);

    if (lotteryPrizeName) {
        lotteryPrizeName.textContent = prize.name;
    }

    if (lotteryPrizeDetail) {
        lotteryPrizeDetail.textContent = "兌換資料已包含獎項、會員資訊與產生時間。";
    }

    renderPrizeQrCode(payload);

    if (lotteryQrWrap) {
        lotteryQrWrap.hidden = false;
    }

    if (lotteryPrizeCard) {
        lotteryPrizeCard.hidden = false;
    }
}

function handleLotteryResult(result) {
    if (!result || !result.prize) {
        throw new Error(result && result.message ? result.message : "伺服器未回傳有效獎項");
    }

    const prize = result.prize;
    const prizeName = prize.prize_name || prize.name || prize.prize_code;
    const canRetry =
        result.can_retry === true ||
        result.is_final === false ||
        prize.prize_type === "retry";

    if (canRetry) {
        lotteryCompleted = false;
        clearPrizeQrCode();

        if (lotteryResult) {
            lotteryResult.textContent = `抽獎結果：${prizeName}。恭喜抽到再抽一次！`;
        }

        if (lotteryPrizeCard) {
            lotteryPrizeCard.hidden = true;
        }

        if (spinButton) {
            spinButton.disabled = false;
            spinButton.textContent = "再抽一次";
        }

        return;
    }

    const selectedPrize = {
        ...prize,
        record_id: result.record_id ?? prize.record_id ?? null,
        id: prize.id || prize.prize_code,
        name: prize.name || prize.prize_name
    };

    lotteryCompleted = true;

    if (lotteryResult) {
        lotteryResult.textContent = `抽獎結果：${selectedPrize.name}`;
    }

    showPrizeResult(
        selectedPrize,
        result.qr_code_url || prize.qr_code_url || null
    );
    launchLotteryConfetti();

    if (spinButton) {
        spinButton.disabled = true;
        spinButton.textContent = "已完成抽獎";
    }
}

function launchLotteryConfetti() {
    if (!lotteryConfetti) {
        return;
    }

    lotteryConfetti.innerHTML = "";
    lotteryConfetti.classList.add("is-active");

    for (let i = 0; i < 34; i += 1) {
        const piece = document.createElement("span");
        piece.style.setProperty("--confetti-left", `${Math.random() * 100}%`);
        piece.style.setProperty("--confetti-delay", `${Math.random() * 0.4}s`);
        piece.style.setProperty("--confetti-drift", `${Math.random() * 120 - 60}px`);
        piece.style.setProperty("--confetti-rotate", `${Math.random() * 420 + 120}deg`);
        piece.style.setProperty("--confetti-color", ["#facc15", "#2563eb", "#22c55e", "#ef4444", "#f97316"][i % 5]);
        lotteryConfetti.appendChild(piece);
    }

    window.setTimeout(function () {
        lotteryConfetti.classList.remove("is-active");
        lotteryConfetti.innerHTML = "";
    }, 2800);
}

if (registerForm) {
    initLiffProfile();

    if (faceImageInput) {
        faceImageInput.addEventListener("change", function () {
            const file = faceImageInput.files[0];

            if (!file) {
                resetFacePreview();
                return;
            }

            if (facePreview) {
                facePreview.src = URL.createObjectURL(file);
                facePreview.hidden = false;
            }

            if (clearFaceImageButton) {
                clearFaceImageButton.hidden = false;
            }
        });
    }

    if (clearFaceImageButton && faceImageInput) {
        clearFaceImageButton.addEventListener("click", function () {
            faceImageInput.value = "";
            resetFacePreview();
        });
    }

    registerForm.addEventListener("submit", function (event) {
        event.preventDefault();

        if (registerSuccess) {
            return;
        }

        const nameInput = document.getElementById("name");
        const phoneInput = document.getElementById("phone");
        const name = nameInput ? nameInput.value.trim() : "";
        const phone = phoneInput ? phoneInput.value.trim() : "";
        const birthday = document.getElementById("birthday").value;
        const lineUserId = lineUserIdInput ? lineUserIdInput.value.trim() : "";
        const faceImageFile = faceImageInput && faceImageInput.files ? faceImageInput.files[0] : null;

        if (!name) {
            showRegisterResult("請輸入姓名。", "error");
            return;
        }

        if (!lineUserId) {
            showRegisterResult("缺少 LINE User ID，請從 LINE 官方帳號的註冊連結重新開啟。", "error");
            return;
        }

        if (!faceImageFile) {
            showRegisterResult("請上傳臉部照片。", "error");
            return;
        }

        const allowedTypes = ["image/jpeg", "image/png"];
        if (!allowedTypes.includes(faceImageFile.type)) {
            showRegisterResult("照片格式僅支援 JPG 或 PNG。", "error");
            return;
        }

        const maxSize = 8 * 1024 * 1024;
        if (faceImageFile.size > maxSize) {
            showRegisterResult("照片大小不可超過 8 MB。", "error");
            return;
        }

        if (registerButton) {
            registerButton.disabled = true;
            registerButton.textContent = "註冊中...";
        }

        const formData = new FormData();
        formData.append("name", name);
        formData.append("phone", phone);
        formData.append("birthday", birthday);
        formData.append("line_user_id", lineUserId);
        formData.append("id_token", idTokenInput ? idTokenInput.value : "");
        formData.append("preferences", JSON.stringify(getSelectedPreferences()));
        formData.append("favorite_product", getSelectedPreferences()[0] || "");
        formData.append("registration_source", "line");
        formData.append("face_image", faceImageFile);

        fetch("/line/register", {
            method: "POST",
            body: formData
        })
            .then(function (response) {
                return response.json()
                    .catch(function () {
                        return { success: false, message: "伺服器回應格式錯誤。" };
                    })
                    .then(function (data) {
                        return { ok: response.ok, data: data };
                    });
            })
            .then(function (result) {
                if (!result.ok || !result.data.success) {
                    showRegisterResult(result.data.message || "註冊失敗，請稍後再試。", "error");
                    return;
                }

                registeredMember = result.data.member || {};
                registerSuccess = true;

                const memberId = getRegisteredMemberId();
                console.log("registeredMember:", registeredMember);
                console.log("memberId:", memberId);

                const memberIdMessage = memberId ? `，會員編號：${memberId}` : "";
                showRegisterResult(`${result.data.message || "註冊成功"}${memberIdMessage}`, "success");

                registerForm.querySelectorAll("input").forEach(function (input) {
                    input.disabled = true;
                });

                if (registerButton) {
                    registerButton.disabled = true;
                    registerButton.textContent = "已完成註冊";
                }

                if (spinButton && lotteryResult) {
                    if (memberId) {
                        spinButton.disabled = false;
                        lotteryResult.textContent = "註冊完成，可以抽一次迎新獎勵。";
                    } else {
                        spinButton.disabled = true;
                        lotteryResult.textContent = "註冊成功，但找不到會員編號，暫時無法抽獎。";
                    }
                }
            })
            .catch(function (error) {
                console.error("註冊 API 呼叫失敗", error);
                showRegisterResult("網路連線失敗，請稍後再試。", "error");
            })
            .finally(resetRegisterButton);
    });
}

if (spinButton && spinWheel && lotteryResult) {
    spinButton.addEventListener("click", async function () {
        if (isDrawing) {
            return;
        }

        if (lotteryCompleted) {
            return;
        }

        if (isSpinning || !registerSuccess) {
            return;
        }

        const memberId = getRegisteredMemberId();

        if (!memberId) {
            spinButton.disabled = true;
            lotteryResult.textContent = "找不到會員編號，請先完成會員註冊";
            return;
        }

        isDrawing = true;
        spinButton.disabled = true;
        spinButton.setAttribute("aria-busy", "true");
        spinButton.textContent = "抽獎中…";
        lotteryResult.textContent = "抽獎中...";

        try {
            const result = await requestLotteryDraw(memberId);

            if (result.already_completed === true) {
                lotteryCompleted = true;
                clearPrizeQrCode();

                if (lotteryPrizeCard) {
                    lotteryPrizeCard.hidden = true;
                }

                spinButton.disabled = true;
                spinButton.textContent = "已完成抽獎";
                lotteryResult.textContent = result.message || "已完成抽獎";
                return;
            }

            if (result.success !== true || !result.prize) {
                throw new Error(result.message || "抽獎失敗");
            }

            const prizeIndex = getPrizeIndex(result.prize);

            isSpinning = true;

            spinWheel.style.setProperty("--wheel-text-fix", "0deg");

            const segmentDegree = 360 / prizes.length;
            const prizeCenterDegree = prizeIndex * segmentDegree + segmentDegree / 2;
            const targetDegree = 360 - prizeCenterDegree;
            const extraSpins = 5 * 360;
            const finalRotation = currentRotation + extraSpins + targetDegree;

            spinWheel.style.transform = `rotate(${finalRotation}deg)`;
            currentRotation = finalRotation;

            await new Promise(function (resolve) {
                window.setTimeout(resolve, 4200);
            });

            spinWheel.style.setProperty("--wheel-text-fix", `${finalRotation}deg`);
            isSpinning = false;
            handleLotteryResult(result);
        } catch (error) {
            clearPrizeQrCode();

            if (lotteryPrizeCard) {
                lotteryPrizeCard.hidden = true;
            }

            lotteryResult.textContent = error.message || "抽獎失敗";
            isSpinning = false;

            if (!lotteryCompleted) {
                spinButton.disabled = false;
                spinButton.textContent = "重新抽獎";
            } else {
                spinButton.disabled = true;
                spinButton.textContent = "已完成抽獎";
            }
        } finally {
            isDrawing = false;
            spinButton.removeAttribute("aria-busy");
        }
    });
}
