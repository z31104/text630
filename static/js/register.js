let LIFF_ID = "";

const spinWheel = document.getElementById("spinWheel");
const spinButton = document.getElementById("spinButton");
const lotteryResult = document.getElementById("lotteryResult");
const registerForm = document.getElementById("registerForm");
const registerButton = document.getElementById("registerButton");
const registerResult = document.getElementById("registerResult");
const lineUserIdInput = document.getElementById("line_user_id");
const lineHint = document.getElementById("lineHint");
const faceImageInput = document.getElementById("face_image");
const facePreview = document.getElementById("facePreview");
const clearFaceImageButton = document.getElementById("clearFaceImage");
const lotteryPrizeCard = document.getElementById("lotteryPrizeCard");
const lotteryPrizeName = document.getElementById("lotteryPrizeName");
const lotteryPrizeDetail = document.getElementById("lotteryPrizeDetail");
const lotteryQrCode = document.getElementById("lotteryQrCode");
const lotteryConfetti = document.getElementById("lotteryConfetti");

let registerSuccess = false;
let registeredMember = null;
let isSpinning = false;
let currentRotation = 0;

const prizes = [
    { id: "WELCOME_50", name: "$50 折價券" },
    { id: "WELCOME_10_OFF", name: "全品項 9 折" },
    { id: "WELCOME_100", name: "$100 折價券" },
    { id: "WELCOME_DESSERT", name: "甜點招待券" },
    { id: "WELCOME_DRINK", name: "飲品兌換券" },
    { id: "WELCOME_RETRY", name: "再抽一次" }
];

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
    if (setLineUserIdFromQuery()) {
        return;
    }

    if (typeof liff === "undefined") {
        setLineHint("目前不是從 LINE LIFF 開啟，請從 LINE 註冊連結進入。", "warning");
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

function buildPrizePayload(prize) {
    const memberId = getRegisteredMemberId();

    return JSON.stringify({
        type: "welcome_lottery_prize",
        prize_id: prize.id,
        prize_name: prize.name,
        member_id: memberId,
        line_user_id: lineUserIdInput ? lineUserIdInput.value.trim() || null : null,
        issued_at: new Date().toISOString()
    });
}

function renderPrizeQrCode(payload) {
    if (!lotteryQrCode) {
        return;
    }

    lotteryQrCode.innerHTML = "";

    if (typeof QRCode !== "undefined") {
        new QRCode(lotteryQrCode, {
            text: payload,
            width: 132,
            height: 132,
            colorDark: "#1f2937",
            colorLight: "#ffffff",
            correctLevel: QRCode.CorrectLevel.M
        });
        return;
    }

    const fallbackImage = document.createElement("img");
    fallbackImage.src = `https://api.qrserver.com/v1/create-qr-code/?size=132x132&data=${encodeURIComponent(payload)}`;
    fallbackImage.alt = "中獎兌換 QR Code";
    lotteryQrCode.appendChild(fallbackImage);
}

function showPrizeResult(prize) {
    const payload = buildPrizePayload(prize);

    if (lotteryPrizeName) {
        lotteryPrizeName.textContent = prize.name;
    }

    if (lotteryPrizeDetail) {
        lotteryPrizeDetail.textContent = "兌換資料已包含獎項、會員資訊與產生時間。";
    }

    renderPrizeQrCode(payload);

    if (lotteryPrizeCard) {
        lotteryPrizeCard.hidden = false;
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
                    spinButton.disabled = false;
                    lotteryResult.textContent = "註冊完成，可以抽一次迎新獎勵。";
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
    spinButton.addEventListener("click", function () {
        if (isSpinning || !registerSuccess) {
            return;
        }

        isSpinning = true;
        spinButton.disabled = true;
        lotteryResult.textContent = "抽獎中...";

        spinWheel.style.setProperty("--wheel-text-fix", "0deg");

        const prizeIndex = Math.floor(Math.random() * prizes.length);
        const segmentDegree = 360 / prizes.length;
        const prizeCenterDegree = prizeIndex * segmentDegree + segmentDegree / 2;
        const targetDegree = 360 - prizeCenterDegree;
        const extraSpins = 5 * 360;
        const finalRotation = currentRotation + extraSpins + targetDegree;

        spinWheel.style.transform = `rotate(${finalRotation}deg)`;
        currentRotation = finalRotation;

        window.setTimeout(function () {
            spinWheel.style.setProperty("--wheel-text-fix", `${finalRotation}deg`);
            lotteryResult.textContent = `抽獎結果：${prizes[prizeIndex].name}`;
            showPrizeResult(prizes[prizeIndex]);
            launchLotteryConfetti();
            spinButton.disabled = false;
            isSpinning = false;
        }, 4200);
    });
}
