let LIFF_ID_COUPONS = "";
let currentIdToken = "";
let currentAccessToken = "";

const couponHeroTitle = document.getElementById("couponHeroTitle");
const couponHeroSubtitle = document.getElementById("couponHeroSubtitle");
const couponPanelTag = document.getElementById("couponPanelTag");
const couponSummaryTitle = document.getElementById("couponSummaryTitle");
const couponUnboundNotice = document.getElementById("couponUnboundNotice");
const couponUnboundMessage = document.getElementById("couponUnboundMessage");
const couponListPanel = document.getElementById("couponListPanel");
const couponList = document.getElementById("couponList");
const couponListEmpty = document.getElementById("couponListEmpty");
const prizeListPanel = document.getElementById("prizeListPanel");
const prizeList = document.getElementById("prizeList");
const prizeListEmpty = document.getElementById("prizeListEmpty");

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

    if (
        coupon.can_redeem_directly === true
        && coupon.member_coupon_id
    ) {
        const redeemButton = document.createElement("button");
        redeemButton.type = "button";
        redeemButton.className = "member-coupon-redeem-link";
        redeemButton.textContent = "門市確認兌換";
        redeemButton.addEventListener("click", function () {
            const confirmed = window.confirm(
                "確定要兌換這張 100 元折價券嗎？兌換後將立即失效，無法復原。"
            );
            if (!confirmed) {
                return;
            }

            redeemButton.disabled = true;
            redeemButton.textContent = "兌換中...";
            fetch(`/api/coupons/${coupon.member_coupon_id}/redeem`, {
                method: "POST",
                cache: "no-store",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    id_token: currentIdToken,
                    access_token: currentAccessToken
                })
            })
                .then(function (response) {
                    return response.json().then(function (result) {
                        return {status: response.status, result: result};
                    });
                })
                .then(function (response) {
                    if (response.status === 401) {
                        restartCouponsLogin();
                        return;
                    }
                    if (!response.result || response.result.success !== true) {
                        window.alert(
                            (response.result && response.result.message)
                            || "兌換失敗，請稍後再試。"
                        );
                        redeemButton.disabled = false;
                        redeemButton.textContent = "門市確認兌換";
                        return;
                    }
                    window.alert("100 元折價券兌換成功。");
                    fetchMyCoupons(currentIdToken, currentAccessToken);
                })
                .catch(function () {
                    window.alert("兌換失敗，請稍後再試。");
                    redeemButton.disabled = false;
                    redeemButton.textContent = "門市確認兌換";
                });
        });
        redemption.appendChild(redeemButton);
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

function buildPrizeCard(prize) {
    const card = document.createElement("article");
    card.className = "member-coupon-card";
    const header = document.createElement("div");
    header.className = "member-coupon-card-header";
    const titleGroup = document.createElement("div");
    const code = document.createElement("p");
    code.className = "member-coupon-code";
    code.textContent = prize.prize_code || `獎品 #${prize.member_prize_id}`;
    const title = document.createElement("h3");
    title.textContent = prize.prize_name || "未命名獎品";
    titleGroup.append(code, title);
    const status = document.createElement("span");
    const isAvailable = prize.status === "unused";
    status.className = `member-coupon-status is-${isAvailable ? "available" : "used"}`;
    status.textContent = isAvailable ? "可兌換" : (prize.status === "redeemed" ? "已兌換" : "已失效");
    header.append(titleGroup, status);
    card.appendChild(header);

    const meta = document.createElement("dl");
    meta.className = "member-coupon-meta";
    appendCouponMeta(meta, "取得時間", prize.issued_at);
    appendCouponMeta(meta, "到期時間", prize.expires_at || "無期限");
    card.appendChild(meta);

    if (isAvailable && prize.redeem_url) {
        const redemption = document.createElement("div");
        redemption.className = "member-coupon-redemption";
        const label = document.createElement("strong");
        label.textContent = "請至門市出示兌換碼";
        const link = document.createElement("a");
        link.className = "member-coupon-redeem-link";
        link.href = prize.redeem_url;
        link.target = "_blank";
        link.rel = "noopener";
        link.textContent = "查看兌換入口";
        redemption.append(label, link);
        card.appendChild(redemption);
    }
    return card;
}

function renderPrizeList(prizes) {
    if (!prizeListPanel || !prizeList || !prizeListEmpty) {
        return;
    }
    const rows = Array.isArray(prizes) ? prizes : [];
    prizeList.replaceChildren();
    prizeListPanel.hidden = false;
    prizeListEmpty.hidden = rows.length > 0;
    rows.forEach(function (prize) {
        prizeList.appendChild(buildPrizeCard(prize || {}));
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
    renderPrizeList(data.prizes);

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
    if (prizeListPanel) {
        prizeListPanel.hidden = true;
    }
}

async function restartCouponsLogin() {
    try {
        if (typeof liff !== "undefined" && liff.isLoggedIn()) {
            liff.logout();
        }
    } catch (error) {
        console.warn("清除舊 LINE 登入狀態失敗", error);
    }

    if (LIFF_ID_COUPONS) {
        window.location.replace(
            `https://liff.line.me/${LIFF_ID_COUPONS}?reauth=${Date.now()}`
        );
    }
}

function fetchMyCoupons(idToken, accessToken) {
    currentIdToken = idToken || "";
    currentAccessToken = accessToken || "";
    return fetch("/api/coupons/me", {
        method: "POST",
        cache: "no-store",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            id_token: idToken || "",
            access_token: accessToken || ""
        })
    })
        .then(function (res) {
            return res.json().then(function (result) {
                return {
                    ok: res.ok,
                    status: res.status,
                    result: result
                };
            });
        })
        .then(function (response) {
            const result = response.result;

            if (response.status === 401) {
                restartCouponsLogin();
                return;
            }

            if (!result || result.success !== true) {
                console.warn("查詢我的優惠券失敗", result && result.message);
                showUnbound(
                    (result && result.message)
                    || "優惠券載入失敗，請稍後再試。"
                );
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

    fetch("/line/config", { cache: "no-store" })
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
                // 不自訂 redirectUri，讓 LIFF 回到 Developers Console
                // 已登記的 Endpoint URL，避免網域不符時登入後落到 404。
                liff.login();
                return;
            }

            const idToken = liff.getIDToken();
            const accessToken = liff.getAccessToken();

            if (!idToken && !accessToken) {
                console.warn("無法取得 LIFF 登入憑證");
                restartCouponsLogin();
                return;
            }

            fetchMyCoupons(idToken, accessToken);
        })
        .catch(function (error) {
            console.warn("LIFF 初始化失敗，維持未登入畫面", error);
        });
}

initLiffCoupons();
