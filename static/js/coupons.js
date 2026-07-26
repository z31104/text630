let LIFF_ID_COUPONS = "";

const couponHeroTitle = document.getElementById("couponHeroTitle");
const couponHeroSubtitle = document.getElementById("couponHeroSubtitle");
const couponPanelTag = document.getElementById("couponPanelTag");
const couponSummaryTitle = document.getElementById("couponSummaryTitle");
const couponUnboundNotice = document.getElementById("couponUnboundNotice");
const couponUnboundMessage = document.getElementById("couponUnboundMessage");

const couponStatLabels = [
    document.getElementById("couponStatLabel1"),
    document.getElementById("couponStatLabel2"),
    document.getElementById("couponStatLabel3")
];
const couponStatValues = [
    document.getElementById("couponStatValue1"),
    document.getElementById("couponStatValue2"),
    document.getElementById("couponStatValue3")
];
const couponStatNotes = [
    document.getElementById("couponStatNote1"),
    document.getElementById("couponStatNote2"),
    document.getElementById("couponStatNote3")
];

function setStat(index, label, value, note) {
    if (couponStatLabels[index]) {
        couponStatLabels[index].textContent = label;
    }
    if (couponStatValues[index]) {
        couponStatValues[index].textContent = value;
    }
    if (couponStatNotes[index]) {
        couponStatNotes[index].textContent = note;
    }
}

function showMemberCoupons(data) {
    if (couponHeroTitle) {
        couponHeroTitle.textContent = "我的優惠券";
    }
    if (couponHeroSubtitle) {
        couponHeroSubtitle.textContent = "查看目前持有、可使用及即將到期的優惠券數量。";
    }
    if (couponPanelTag) {
        couponPanelTag.textContent = "MY COUPONS";
    }
    if (couponSummaryTitle) {
        couponSummaryTitle.textContent = "會員優惠券摘要";
    }

    setStat(0, "優惠券總數", data.total, "目前持有");
    setStat(1, "可使用", data.usable, "尚未使用");
    setStat(2, "即將過期", data.expiring_soon, "7 日內到期");

    if (couponUnboundNotice) {
        couponUnboundNotice.hidden = true;
    }
}

function showUnbound(message) {
    if (couponUnboundMessage && message) {
        couponUnboundMessage.textContent = message;
    }
}

function fetchMyCoupons(idToken) {
    fetch("/api/coupons/me", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ id_token: idToken })
    })
        .then(function (res) {
            return res.json();
        })
        .then(function (result) {
            if (!result || result.success !== true) {
                console.warn("查詢我的優惠券失敗", result && result.message);
                return;
            }

            if (result.bound) {
                showMemberCoupons(result);
            } else {
                showUnbound(result.message);
            }
        })
        .catch(function (error) {
            console.warn("查詢我的優惠券失敗", error);
        });
}

function initLiffCoupons() {
    if (typeof liff === "undefined") {
        return;
    }

    fetch("/line/config")
        .then(function (res) {
            return res.json();
        })
        .then(function (config) {
            LIFF_ID_COUPONS = config.liff_id_coupons || "";

            if (!LIFF_ID_COUPONS) {
                console.warn("LIFF_ID_COUPONS 尚未設定，跳過個人優惠券查詢");
                return Promise.reject(new Error("LIFF_ID_COUPONS 未設定"));
            }

            return liff.init({ liffId: LIFF_ID_COUPONS });
        })
        .then(function () {
            if (!liff.isLoggedIn()) {
                liff.login({ redirectUri: window.location.href });
                return;
            }

            const idToken = liff.getIDToken();

            if (!idToken) {
                console.warn("無法取得 LIFF ID Token");
                return;
            }

            fetchMyCoupons(idToken);
        })
        .catch(function (error) {
            console.warn("LIFF 初始化失敗，維持未登入畫面", error);
        });
}

initLiffCoupons();
