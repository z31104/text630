const LIFF_ID = "2010668858-gsTCqv7v";

const spinWheelNew = document.getElementById("spinWheel");
const spinButtonNew = document.getElementById("spinButton");
const lotteryResultNew = document.getElementById("lotteryResult");
const registerFormNew = document.getElementById("registerForm");
const registerButtonNew = document.getElementById("registerButton");
const registerResultNew = document.getElementById("registerResult");
const lineUserIdInputNew = document.getElementById("line_user_id");
const lineHintNew = document.getElementById("lineHint");
const faceImageInputNew = document.getElementById("face_image");
const facePreviewNew = document.getElementById("facePreview");
const clearFaceImageButtonNew = document.getElementById("clearFaceImage");

let registerSuccessNew = false;

function showRegisterResultNew(message, type) {
    registerResultNew.textContent = message;
    registerResultNew.hidden = false;
    registerResultNew.className = "register-result " + type;
}
function setLineHintNew(message) {
    if (lineHintNew) {
        lineHintNew.textContent = message;
    }
}

function setLineUserIdFromQueryNew() {
    const params = new URLSearchParams(window.location.search);
    const queryLineUserId = params.get("line_user_id");

    if (queryLineUserId) {
        lineUserIdInputNew.value = queryLineUserId;
        setLineHintNew("已從連結帶入 LINE User ID，可以完成註冊。");
        return true;
    }

    return false;
}

function initLiffProfileNew() {
    const hasQueryLineUserId = setLineUserIdFromQueryNew();

    if (hasQueryLineUserId) {
        return;
    }

    if (typeof liff === "undefined") {
        if (!hasQueryLineUserId) {
            setLineHintNew("目前無法載入 LINE LIFF，請從 LINE 註冊連結開啟此頁。");
        }
        return;
    }

    liff.init({ liffId: LIFF_ID })
        .then(function () {
            if (!liff.isLoggedIn()) {
                liff.login({ redirectUri: window.location.href });
                return null;
            }

            return liff.getProfile();
        })
        .then(function (profile) {
            if (!profile) {
                return;
            }

            lineUserIdInputNew.value = profile.userId;
            setLineHintNew("已取得 LINE User ID，請填寫資料並完成註冊。");
        })
        .catch(function (err) {
            console.error("LIFF 初始化失敗", err);
            if (!lineUserIdInputNew.value.trim()) {
                setLineHintNew("無法取得 LINE 使用者資料，請重新從 LINE 註冊連結開啟。");
            }
        });
}

function resetRegisterButtonNew() {
    if (!registerSuccessNew) {
        registerButtonNew.disabled = false;
        registerButtonNew.textContent = "完成註冊";
    }
}

if (registerFormNew) {
    initLiffProfileNew();

    faceImageInputNew.addEventListener("change", function () {
        const file = faceImageInputNew.files[0];

        if (!file) {
            facePreviewNew.hidden = true;
            facePreviewNew.src = "";
            if (clearFaceImageButtonNew) {
                clearFaceImageButtonNew.hidden = true;
            }
            return;
        }

        facePreviewNew.src = URL.createObjectURL(file);
        facePreviewNew.hidden = false;
        if (clearFaceImageButtonNew) {
            clearFaceImageButtonNew.hidden = false;
        }
    });

    if (clearFaceImageButtonNew) {
        clearFaceImageButtonNew.addEventListener("click", function () {
            faceImageInputNew.value = "";
            facePreviewNew.hidden = true;
            facePreviewNew.src = "";
            clearFaceImageButtonNew.hidden = true;
        });
    }

    registerFormNew.addEventListener("submit", function (event) {
        event.preventDefault();

        if (registerSuccessNew) {
            return;
        }

        const name = document.getElementById("name").value.trim();
        const phone = document.getElementById("phone").value.trim();
        const lineUserId = lineUserIdInputNew.value.trim();
        const faceImageFile = faceImageInputNew.files[0];

        if (!name) {
            showRegisterResultNew("請輸入姓名。", "error");
            return;
        }

        if (!lineUserId) {
            showRegisterResultNew("尚未取得 LINE User ID，請從 LINE 註冊連結重新開啟。", "error");
            return;
        }

        if (!faceImageFile) {
            showRegisterResultNew("請上傳會員臉部照片。", "error");
            return;
        }

        const allowedTypes = ["image/jpeg", "image/png"];
        if (!allowedTypes.includes(faceImageFile.type)) {
            showRegisterResultNew("照片格式需為 JPG 或 PNG。", "error");
            return;
        }

        const maxSize = 8 * 1024 * 1024;
        if (faceImageFile.size > maxSize) {
            showRegisterResultNew("照片大小不可超過 8 MB。", "error");
            return;
        }

        registerButtonNew.disabled = true;
        registerButtonNew.textContent = "註冊中...";

        const formData = new FormData();
        formData.append("name", name);
        formData.append("phone", phone);
        formData.append("line_user_id", lineUserId);
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
                    showRegisterResultNew(result.data.message || "註冊失敗，請稍後再試。", "error");
                    return;
                }

                const member = result.data.member || {};
                registerSuccessNew = true;

                showRegisterResultNew(
                    `${result.data.message || "註冊成功"}${member.member_id ? "，會員編號：" + member.member_id : ""}`,
                    "success"
                );

                registerFormNew.querySelectorAll("input").forEach(function (input) {
                    input.disabled = true;
                });

                registerButtonNew.disabled = true;
                registerButtonNew.textContent = "已完成註冊";

                if (spinButtonNew && lotteryResultNew) {
                    spinButtonNew.disabled = false;
                    lotteryResultNew.textContent = "註冊完成，可以抽一次迎新獎勵。";
                }
            })
            .catch(function (err) {
                console.error("註冊送出失敗", err);
                showRegisterResultNew("網路或伺服器發生錯誤，請稍後再試。", "error");
            })
            .finally(resetRegisterButtonNew);
    });
}

const prizesNew = ["$50 折價券", "9 折優惠", "$200 折價券", "小禮品", "免運券", "再抽一次"];
let isSpinningNew = false;
let currentRotationNew = 0;

if (spinButtonNew && spinWheelNew && lotteryResultNew) {
    spinButtonNew.addEventListener("click", function () {
        if (isSpinningNew) {
            return;
        }

        isSpinningNew = true;
        spinButtonNew.disabled = true;
        lotteryResultNew.textContent = "抽獎中...";

        spinWheelNew.style.setProperty("--wheel-text-fix", "0deg");

        const prizeIndex = Math.floor(Math.random() * prizesNew.length);
        const segmentDegree = 360 / prizesNew.length;
        const prizeCenterDegree = prizeIndex * segmentDegree + segmentDegree / 2;
        const targetDegree = 360 - prizeCenterDegree;
        const extraSpins = 5 * 360;
        const finalRotation = currentRotationNew + extraSpins + targetDegree;

        spinWheelNew.style.transform = `rotate(${finalRotation}deg)`;
        currentRotationNew = finalRotation;

        setTimeout(function () {
            spinWheelNew.style.setProperty("--wheel-text-fix", `${finalRotation}deg`);
            lotteryResultNew.textContent = `抽獎結果：${prizesNew[prizeIndex]}`;
            spinButtonNew.disabled = false;
            isSpinningNew = false;
        }, 4200);
    });
}
