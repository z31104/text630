const LIFF_ID = "2010668858-gsTCqv7v";

const spinWheel = document.getElementById("spinWheel");
const spinButton = document.getElementById("spinButton");
const lotteryResult = document.getElementById("lotteryResult");

const registerForm = document.getElementById("registerForm");
const registerButton = document.getElementById("registerButton");
const registerResult = document.getElementById("registerResult");
const lineUserIdInput = document.getElementById("line_user_id");
const lineHint = document.getElementById("lineHint");

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

registerForm.addEventListener("submit", function (event) {
    event.preventDefault();

    const name = document.getElementById("name").value.trim();
    const phone = document.getElementById("phone").value.trim();
    const lineUserId = lineUserIdInput.value.trim();
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

    registerButton.disabled = true;
    registerButton.textContent = "註冊中...";

    fetch("/line/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            name: name,
            phone: phone,
            line_user_id: lineUserId,
            birthday: birthday,
            preferences: preferences
        })
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
            showRegisterResult(
                `${result.data.message}！會員編號：${member.member_id}，姓名：${member.name}`,
                "success"
            );

            registerForm.querySelectorAll("input").forEach(function (input) {
                input.disabled = true;
            });

            spinButton.disabled = false;
            lotteryResult.textContent = "註冊完成！可以開始抽獎囉";
        })
        .catch(function () {
            showRegisterResult("網路異常，註冊失敗，請稍後再試", "error");
        })
        .finally(function () {
            registerButton.disabled = false;
            registerButton.textContent = "完成註冊";
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