let LIFF_ID_COUPONS = "";

const couponHeroTitle = document.getElementById("couponHeroTitle");
const couponHeroSubtitle = document.getElementById("couponHeroSubtitle");
const couponPanelTag = document.getElementById("couponPanelTag");
const couponSummaryTitle = document.getElementById("couponSummaryTitle");
const couponUnboundNotice = document.getElementById("couponUnboundNotice");
const couponUnboundMessage = document.getElementById("couponUnboundMessage");
const couponListPanel = document.getElementById("couponListPanel");
const couponList = document.getElementById("couponList");
const couponListEmpty = document.getElementById("couponListEmpty");

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

function appendCouponMeta(metaList, label, value) {
    const item = document.createElement("div");
    const term = document.createElement("dt");
    const detail = document.createElement("dd");

    term.textContent = label;
    detail.textContent = value || "-";
    item.append(term, detail);
    metaList.appendChild(item);
}

function buildCouponCard(coupon) {
    const statusClasses = [
        "available",
        "used",
        "expired",
        "upcoming",
        "unavailable"
    ];
    const status = statusClasses.includes(coupon.status)
        ? coupon.status
        : "unavailable";

    const card = document.createElement("article");
    card.className = "member-coupon-card";

    const header = document.createElement("div");
    header.className = "member-coupon-card-header";

    const titleGroup = document.createElement("div");
    const code = document.createElement("p");
    const title = document.createElement("h3");
    code.className = "member-coupon-code";
    code.textContent = coupon.member_coupon_id
        ? `優惠券 #${coupon.member_coupon_id}`
        : "會員優惠券";
    title.textContent = coupon.coupon_name || "未命名優惠券";
    titleGroup.append(code, title);

    const statusBadge = document.createElement("span");
    statusBadge.className = `member-coupon-status is-${status}`;
    statusBadge.textContent = coupon.status_label || "不可使用";
    header.append(titleGroup, statusBadge);

    const description = document.createElement("p");
    description.className = "member-coupon-description";
    description.textContent = (
        coupon.description
        || coupon.discount_text
        || "依活動內容使用"
    );

    card.append(header, description);

    if (coupon.discount_text) {
        const discount = document.createElement("p");
        discount.className = "member-coupon-discount";
        discount.textContent = coupon.discount_text;
        card.appendChild(discount);
    }

    const metaList = document.createElement("dl");
    metaList.className = "member-coupon-meta";
    appendCouponMeta(
        metaList,
        "取得時間",
        coupon.receive_time
    );
    appendCouponMeta(
        metaList,
        "到期時間",
        coupon.end_at || "無期限"
    );
    card.appendChild(metaList);

    const redemption = document.createElement("div");
    redemption.className = "member-coupon-redemption";

    const redemptionText = document.createElement("div");
    const redemptionLabel = document.createElement("span");
    const redemptionValue = document.createElement("strong");
    redemptionLabel.textContent = "兌換資訊";
    redemptionValue.textContent = coupon.redemption_info || "-";
    redemptionText.append(redemptionLabel, redemptionValue);
    redemption.appendChild(redemptionText);

    const hasSafeRedemptionUrl = (
        coupon.can_open_redemption === true
        && typeof coupon.redeem_url === "string"
        && coupon.redeem_url.startsWith("/redeem/")
    );

    if (hasSafeRedemptionUrl) {
        const redemptionLink = document.createElement("a");
        redemptionLink.className = "member-coupon-redeem-link";
        redemptionLink.href = coupon.redeem_url;
        redemptionLink.target = "_blank";
        redemptionLink.rel = "noopener";
        redemptionLink.textContent = "查看兌換入口";
        redemption.appendChild(redemptionLink);
    }

    card.appendChild(redemption);
    return card;
}

function renderCouponList(coupons) {
    if (!couponListPanel || !couponList || !couponListEmpty) {
        return;
    }

    const rows = Array.isArray(coupons) ? coupons : [];
    couponList.replaceChildren();
    couponListPanel.hidden = false;

    if (rows.length === 0) {
        couponListEmpty.hidden = false;
        return;
    }

    couponListEmpty.hidden = true;
    rows.forEach(function (coupon) {
        couponList.appendChild(buildCouponCard(coupon || {}));
    });
}

function showMemberCoupons(data) {
    if (couponHeroTitle) {
        couponHeroTitle.textContent = "我的優惠券";
    }
    if (couponHeroSubtitle) {
        couponHeroSubtitle.textContent = "查看目前持有的優惠券數量、有效期限與兌換狀態。";
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
    renderCouponList(data.coupons);

    if (couponUnboundNotice) {
        couponUnboundNotice.hidden = true;
    }
}

function showUnbound(message) {
    if (couponUnboundMessage && message) {
        couponUnboundMessage.textContent = message;
    }
    if (couponListPanel) {
        couponListPanel.hidden = true;
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
