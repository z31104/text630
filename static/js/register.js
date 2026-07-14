const LIFF_ID = "2010668858-gsTCqv7v";

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

let registerSuccess = false;
const faceImageInput = document.getElementById("face_image");
const facePreview = document.getElementById("facePreview");

let registerSuccess = false;

function showRegisterResult(message, type) {
    registerResult.textContent = message;
    registerResult.hidden = false;
    registerResult.className = "register-result " + type;
}

if (typeof liff === "undefined") {
    console.error("LIFF SDK 沒有載入成功");
    lineHint.textContent = "無法載入 LINE 服務，請確認網路連線，或改由 LINE 官方帳號的註冊連結重新進入本頁面";
} else {
    liff.init({ liffId: LIFF_ID })
        .then(function () {
            if (!liff.isLoggedIn()) {
                liff.login();
                return;
            }
            return liff.getProfile().then(function (profile) {
                lineUserIdInput.value = profile.userId;
                lineHint.textContent = "已透過 LINE 自動帶入您的身分，請填寫以下資料完成註冊";
            });
        })
        .catch(function (err) {
            console.error("LIFF 初始化失敗：", err);
            lineHint.textContent = "無法取得 LINE 身分，請由 LINE 官方帳號的註冊連結重新進入本頁面";
        });
}

faceImageInput.addEventListener("change", function () {
    const file = faceImageInput.files[0];

    if (!file) {
        facePreview.hidden = true;
        facePreview.src = "";
        return;
    }

    facePreview.src = URL.createObjectURL(file);
    facePreview.hidden = false;
});

registerForm.addEventListener("submit", function (event) {
    event.preventDefault();

    if (registerSuccess) {
        return;
    }

    const name = document.getElementById("name").value.trim();
    const phone = document.getElementById("phone").value.trim();
    const lineUserId = lineUserIdInput.value.trim();
    const faceImageFile = faceImageInput.files[0];
    const birthday = document.getElementById("birthday").value;
    const preferences = Array.from(
        document.querySelectorAll('input[name="preference"]:checked')
    ).map(function (checkbox) {
        return checkbox.value;
    });

    if (!name) {
        showRegisterResult("請輸入姓名", "error");
        return;
    }

    if (!lineUserId) {
        showRegisterResult("找不到 LINE 使用者資訊，請由 LINE 官方帳號的註冊連結重新進入本頁面", "error");
        return;
    }

    if (!faceImageFile) {
        showRegisterResult("請上傳或拍攝會員人臉照片", "error");
        return;
    }

    const allowedTypes = ["image/jpeg", "image/png"];

    if (!allowedTypes.includes(faceImageFile.type)) {
        showRegisterResult("照片格式只支援 JPG 或 PNG", "error");
        return;
    }

    const maxSize = 8 * 1024 * 1024;

    if (faceImageFile.size > maxSize) {
        showRegisterResult("照片不可超過 8 MB", "error");
        return;
    }
    registerButton.disabled = true;
    registerButton.textContent = "註冊中...";

    const formData = new FormData();

    formData.append("name", name);
    formData.append("phone", phone);
    formData.append("line_user_id", lineUserId);
    formData.append("birthday", birthday);
    formData.append("preferences", JSON.stringify(preferences));
    formData.append("face_image", faceImageFile);

    fetch("/line/register", {
        method: "POST",
        body: formData
    })
        .then(function (response) {
            return response.json().then(function (data) {
                return { ok: response.ok, data: data };
            });
        })
        .then(function (result) {
            if (!result.ok) {
                showRegisterResult(result.data.error || "註冊失敗，請稍後再試", "error");
                return;
            }

            const member = result.data.member;
            registerSuccess = true;

            showRegisterResult(
                `${result.data.message}！會員編號：${member.member_id}，姓名：${member.name}`,
                "success"
            );

            registerForm.querySelectorAll("input").forEach(function (input) {
                input.disabled = true;
            });

            registerButton.disabled = true;
            registerButton.textContent = "已完成註冊";

            spinButton.disabled = false;
            lotteryResult.textContent = "註冊完成！可以開始抽獎囉";
        })
        .catch(function () {
            showRegisterResult("網路異常，註冊失敗，請稍後再試", "error");
        })
        .finally(function () {
            if (!registerSuccess) {
                registerButton.disabled = false;
                registerButton.textContent = "完成註冊";
            }
        });
});

const prizes = [
    "現折 50 元",
    "9 折券",
    "200元購物劵",
    "神秘小禮",
    "贈品三選一",
    "再接再厲"
];

let isSpinning = false;
let currentRotation = 0;

spinButton.addEventListener("click", function () {
    if (isSpinning) {
        return;
    }

    isSpinning = true;
    spinButton.disabled = true;
    lotteryResult.textContent = "抽獎中，請稍候...";

    spinWheel.style.setProperty("--wheel-text-fix", "0deg");

    const prizeIndex = Math.floor(Math.random() * prizes.length);
    const segmentDegree = 360 / prizes.length;

    const prizeCenterDegree = prizeIndex * segmentDegree + segmentDegree / 2;
    const targetDegree = 360 - prizeCenterDegree;

    const extraSpins = 5 * 360;
    const finalRotation = currentRotation + extraSpins + targetDegree;

    spinWheel.style.transform = `rotate(${finalRotation}deg)`;

    currentRotation = finalRotation;

    setTimeout(function () {
        spinWheel.style.setProperty("--wheel-text-fix", `${finalRotation}deg`);

        lotteryResult.textContent = `恭喜獲得：${prizes[prizeIndex]}`;
        spinButton.disabled = false;
        isSpinning = false;
    }, 4200);
});
