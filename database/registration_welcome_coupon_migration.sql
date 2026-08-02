-- 新會員完成 LINE 註冊後固定贈送的 100 元折價券。
-- 可重複執行；若同名券已存在，不會再次新增。
INSERT INTO coupons (
    coupon_name,
    description,
    discount_type,
    discount_value,
    start_at,
    end_at,
    status
)
SELECT
    '新會員 100 元註冊禮',
    '完成會員註冊後贈送，消費時可折抵 100 元',
    'amount',
    100,
    NOW(),
    NULL,
    'active'
WHERE NOT EXISTS (
    SELECT 1
    FROM coupons
    WHERE coupon_name = '新會員 100 元註冊禮'
);
