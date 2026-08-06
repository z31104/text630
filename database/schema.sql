CREATE DATABASE IF NOT EXISTS smart_member_system
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE smart_member_system;
CREATE TABLE IF NOT EXISTS product_categories (
    category_id INT AUTO_INCREMENT PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL UNIQUE,
    description VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
    product_id INT AUTO_INCREMENT PRIMARY KEY,
    product_code VARCHAR(50) NOT NULL UNIQUE,
    product_name VARCHAR(150) NOT NULL,
    category_id INT,
    price DECIMAL(10, 2) NOT NULL DEFAULT 0,
    stock_quantity INT NOT NULL DEFAULT 0,
    description TEXT,
    image_url VARCHAR(255),
    product_status VARCHAR(20) DEFAULT '上架',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (category_id)
        REFERENCES product_categories(category_id)
        ON DELETE SET NULL
);
-- 正式會員
CREATE TABLE IF NOT EXISTS members (
    member_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    phone VARCHAR(20),
    birthday DATE NULL,
    vip BOOLEAN DEFAULT FALSE,
    member_level VARCHAR(20) DEFAULT 'normal',
    
    -- 第四週正式欄位
    last_visit_time DATETIME NULL,
    total_visit_time INT NOT NULL DEFAULT 0,
    total_visit_count INT NOT NULL DEFAULT 0,
    updated_by VARCHAR(100) NULL,

    line_user_id VARCHAR(100) UNIQUE,
    total_amount DECIMAL(12, 2) NOT NULL DEFAULT 0,
    favorite_product VARCHAR(100),
    face_image VARCHAR(255),
    registration_source VARCHAR(50) DEFAULT 'line',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS purchase_records (
    purchase_id INT AUTO_INCREMENT PRIMARY KEY,
    member_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL DEFAULT 1,
    unit_price DECIMAL(10, 2) NOT NULL DEFAULT 0,
    total_amount DECIMAL(10, 2) NOT NULL DEFAULT 0,
    purchase_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    store_location VARCHAR(100),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (member_id)
        REFERENCES members(member_id)
        ON DELETE CASCADE,

    FOREIGN KEY (product_id)
        REFERENCES products(product_id)
        ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS face_images (
    face_id INT AUTO_INCREMENT PRIMARY KEY,
    member_id INT NOT NULL,
    image_path VARCHAR(255) NOT NULL,
    encoding_data LONGTEXT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (member_id)
        REFERENCES members(member_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS visitors (
    visitor_id INT AUTO_INCREMENT PRIMARY KEY,
    visitor_code VARCHAR(50) NOT NULL UNIQUE,
    display_name VARCHAR(50) DEFAULT 'Visitor',
    visitor_visit_count INT NOT NULL DEFAULT 0,
    first_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_seen_at DATETIME NULL,
    converted_member_id INT NULL,
    best_face_image VARCHAR(255) NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

INDEX idx_visitors_converted_member_id (converted_member_id),

    FOREIGN KEY (converted_member_id)
        REFERENCES members(member_id)
        ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS visitor_faces (
    visitor_face_id INT AUTO_INCREMENT PRIMARY KEY,
    visitor_id INT NOT NULL,
    image_path VARCHAR(255) NULL,
    encoding_data LONGTEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (visitor_id)
        REFERENCES visitors(visitor_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS camera_locations (
    camera_id VARCHAR(50) PRIMARY KEY,
    camera_name VARCHAR(100) NOT NULL,
    camera_location VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS recognition_logs (
    log_id INT AUTO_INCREMENT PRIMARY KEY,
    subject_type VARCHAR(20) NOT NULL DEFAULT 'unknown',
    member_id INT NULL,
    visitor_id INT NULL,
    visitor_code VARCHAR(50) NULL,
    camera_id VARCHAR(50),
    name VARCHAR(50),
    vip BOOLEAN DEFAULT FALSE,
    line_user_id VARCHAR(100),

    confidence FLOAT DEFAULT 0,
    member_level VARCHAR(20) DEFAULT 'guest',
    recognition_status VARCHAR(30) DEFAULT 'guest',
    visit_status VARCHAR(30) DEFAULT 'arrived',

    recognized_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    visit_time DATETIME,
    last_seen_at DATETIME NULL,
    leave_time DATETIME NULL,

    -- 第四週正式停留時間欄位，統一以秒數儲存
    stay_seconds INT DEFAULT 0,

    notification_sent BOOLEAN NOT NULL DEFAULT FALSE,
    coupon_sent BOOLEAN NOT NULL DEFAULT FALSE,
    lottery_status VARCHAR(30) NOT NULL DEFAULT 'not_joined',

    camera_location VARCHAR(100),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_recognition_logs_member_active (
        subject_type,
        member_id,
        camera_id,
        visit_status,
        leave_time
    ),

    INDEX idx_recognition_logs_visitor_active (
        subject_type,
        visitor_id,
        camera_id,
        visit_status,
        leave_time
),

    INDEX idx_recognition_visit_time (
        visit_time
),


    FOREIGN KEY (member_id) 
    REFERENCES members(member_id)
     ON DELETE SET NULL,


    FOREIGN KEY (visitor_id)
    REFERENCES visitors(visitor_id)
    ON DELETE SET NULL
    );

CREATE TABLE IF NOT EXISTS vip_notifications (
    notification_id INT AUTO_INCREMENT PRIMARY KEY,
    member_id INT NOT NULL,
    log_id INT,
    line_user_id VARCHAR(100),
    message TEXT,
    status VARCHAR(20) DEFAULT 'pending',
    sent_at DATETIME DEFAULT NULL,


    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    notification_type VARCHAR(30) NOT NULL DEFAULT 'vip',
    retry_count INT NOT NULL DEFAULT 0,
    response_message TEXT NULL,
    
    UNIQUE KEY uq_vip_notifications_log_id (log_id),

    FOREIGN KEY (member_id)
    REFERENCES members(member_id)
    ON DELETE CASCADE,

    FOREIGN KEY (log_id)
    REFERENCES recognition_logs(log_id)
    ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS coupons (
    coupon_id INT AUTO_INCREMENT PRIMARY KEY,
    coupon_name VARCHAR(100) NOT NULL,
    description TEXT,
    discount_type VARCHAR(20),
    discount_value INT,
    start_at DATETIME,
    end_at DATETIME,
    status VARCHAR(20) DEFAULT 'active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS member_coupons (
    member_coupon_id INT AUTO_INCREMENT PRIMARY KEY,
    member_id INT NOT NULL,
    coupon_id INT NOT NULL,
    source VARCHAR(50),
    status VARCHAR(20) DEFAULT 'unused',

    receive_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    used_time DATETIME NULL,

    FOREIGN KEY (member_id) REFERENCES members(member_id) ON DELETE CASCADE,
    FOREIGN KEY (coupon_id) REFERENCES coupons(coupon_id) ON DELETE CASCADE
);

    INSERT IGNORE INTO coupons (
    coupon_id,
    coupon_name,
    description,
    discount_type,
    discount_value,
    start_at,
    end_at,
    status
)
VALUES
(
    1,
    '新會員 50 元優惠券',
    '新會員抽獎獲得，消費時可折抵 50 元',
    'amount',
    50,
    NOW(),
    DATE_ADD(NOW(), INTERVAL 30 DAY),
    'active'
),
(
    2,
    '新會員 9 折優惠券',
    '新會員抽獎獲得，消費時享 9 折優惠',
    'percentage',
    10,
    NOW(),
    DATE_ADD(NOW(), INTERVAL 30 DAY),
    'active'
),
(
    3,
    '新會員 200 元優惠券',
    '新會員抽獎獲得，消費時可折抵 200 元',
    'amount',
    200,
    NOW(),
    DATE_ADD(NOW(), INTERVAL 30 DAY),
    'active'
),
(
    4,
    '新會員免運優惠券',
    '新會員抽獎獲得，可享免運優惠',
    'free_shipping',
    0,
    NOW(),
    DATE_ADD(NOW(), INTERVAL 30 DAY),
    'active'
),
(
    5,
    '新會員 100 元註冊禮',
    '完成會員註冊後贈送，消費時可折抵 100 元',
    'amount',
    100,
    NULL,
    NULL,
    'active'
);

CREATE TABLE IF NOT EXISTS lottery_prizes (
    prize_id INT AUTO_INCREMENT PRIMARY KEY,

    prize_code VARCHAR(50) NOT NULL UNIQUE,
    prize_name VARCHAR(100) NOT NULL,
    prize_type VARCHAR(30) NOT NULL,

    prize_value DECIMAL(10,2) DEFAULT 0,
    probability_weight INT NOT NULL DEFAULT 1,

    stock_quantity INT NULL,
    prize_status VARCHAR(20) NOT NULL DEFAULT 'active',


    -- 抽到這個獎項時，要發哪一張優惠券
    -- 禮品、再抽一次可以是 NULL
    coupon_id INT NULL,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    
    CONSTRAINT fk_lottery_prizes_coupon
            FOREIGN KEY (coupon_id)
            REFERENCES coupons(coupon_id)
            ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS lottery_records (
    lottery_id INT AUTO_INCREMENT PRIMARY KEY,

    member_id INT NOT NULL,
    prize_id INT NOT NULL,
    coupon_id INT NULL,

    lottery_name VARCHAR(100) NOT NULL DEFAULT '新會員抽獎',
    prize VARCHAR(100) NULL,
    draw_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) NOT NULL DEFAULT '中獎',

    prize_name VARCHAR(100) NOT NULL,
    result VARCHAR(100),

    is_final BOOLEAN NOT NULL DEFAULT TRUE,
    -- retry 類獎項不會結束抽獎流程；前端依此決定是否可再次呼叫抽獎 API。
    can_retry BOOLEAN NOT NULL DEFAULT FALSE,
    redeemed BOOLEAN NOT NULL DEFAULT FALSE,
    redeemed_at DATETIME NULL,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_lottery_records_member_time (
        member_id,
        created_at
    ),

    FOREIGN KEY (member_id)
        REFERENCES members(member_id)
        ON DELETE CASCADE,

    FOREIGN KEY (prize_id)
        REFERENCES lottery_prizes(prize_id)
        ON DELETE RESTRICT,


CONSTRAINT fk_lottery_records_coupon
    FOREIGN KEY (coupon_id)
        REFERENCES coupons(coupon_id)
        ON DELETE SET NULL
);


CREATE TABLE IF NOT EXISTS member_prizes (
    member_prize_id BIGINT AUTO_INCREMENT PRIMARY KEY,

    member_id INT NOT NULL,
    prize_id INT NOT NULL,
    -- 連到實際發給會員的優惠券
    -- 再抽一次或沒有優惠券的獎品可以是 NULL
    member_coupon_id INT NULL,

    campaign_code VARCHAR(50) NOT NULL,
    prize_code VARCHAR(50) NOT NULL,

    redeem_token VARCHAR(128) NOT NULL UNIQUE,

    status VARCHAR(20) NOT NULL DEFAULT 'unused',

    issued_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NULL,
    redeemed_at DATETIME NULL,
    redeemed_by VARCHAR(100) NULL,

    UNIQUE KEY uq_member_campaign (
        member_id,
        campaign_code
    ),

    INDEX idx_member_prizes_status (
        status
    ),

    INDEX idx_member_prizes_expires_at (
        expires_at
    ),

    CONSTRAINT chk_member_prizes_status
    CHECK (
        status IN (
            'unused',
            'redeemed',
            'expired'
        )
    ),

    FOREIGN KEY (member_id)
        REFERENCES members(member_id)
        ON DELETE CASCADE,

    FOREIGN KEY (prize_id)
        REFERENCES lottery_prizes(prize_id)
        ON DELETE RESTRICT,
    
    CONSTRAINT fk_member_prizes_member_coupon
        FOREIGN KEY (member_coupon_id)
        REFERENCES member_coupons(member_coupon_id)
        ON DELETE SET NULL
);

INSERT IGNORE INTO lottery_prizes (
    prize_code,
    prize_name,
    prize_type,
    prize_value,
    probability_weight,
    stock_quantity,
    prize_status,
    coupon_id
)
VALUES
    (
        'WELCOME_50',
        '$50',
        'coupon',
        50,
        1,
        NULL,
        'active',
        1
    ),
    (
        'WELCOME_10_OFF',
        '9折',
        'discount',
        0.90,
        1,
        NULL,
        'active',
        2
    ),
    (
        'WELCOME_200',
        '$200',
        'coupon',
        200,
        1,
        NULL,
        'active',
        3
    ),
    (
        'WELCOME_GIFT',
        '小禮品',
        'gift',
        0,
        1,
        NULL,
        'active',
        NULL
    ),
    (
        'WELCOME_FREE_SHIP',
        '免運',
        'free_shipping',
        0,
        1,
        NULL,
        'active',
        4
    ),
    (
        'WELCOME_RETRY',
        '再抽一次',
        'retry',
        0,
        1,
        NULL,
        'active',
        NULL
    );

CREATE TABLE IF NOT EXISTS member_preferences (
    preference_id INT AUTO_INCREMENT PRIMARY KEY,
    member_id INT NOT NULL,
    category VARCHAR(50),
    preference_value VARCHAR(100),
    source VARCHAR(50),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (member_id) REFERENCES members(member_id) ON DELETE CASCADE
);

-- =====================================================
-- 商品分類預設資料
-- 四個分類：餐廳、家具、廚具、玩偶
-- =====================================================

INSERT INTO product_categories (
    category_name,
    description
)
VALUES
    ('餐廳', '餐桌用餐與餐廳區相關商品'),
    ('家具', '居家收納、桌椅與生活家具'),
    ('廚具', '料理、烹飪與廚房用品'),
    ('玩偶', '兒童與居家裝飾玩偶')
ON DUPLICATE KEY UPDATE
    description = VALUES(description);


-- =====================================================
-- 餐廳區商品：10 項
-- =====================================================

INSERT INTO products (
    product_code,
    product_name,
    category_id,
    price,
    stock_quantity,
    description,
    image_url,
    product_status
)
VALUES
(
    'REST001',
    '陶瓷餐盤四件組',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '餐廳'),
    499,
    50,
    '日常用白色陶瓷餐盤四件組',
    NULL,
    '上架'
),
(
    'REST002',
    '玻璃水杯六件組',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '餐廳'),
    399,
    60,
    '透明耐用玻璃水杯六件組',
    NULL,
    '上架'
),
(
    'REST003',
    '不鏽鋼餐具組',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '餐廳'),
    299,
    80,
    '包含刀、叉、湯匙的餐具組',
    NULL,
    '上架'
),
(
    'REST004',
    '棉麻桌巾',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '餐廳'),
    459,
    35,
    '簡約棉麻材質餐桌桌巾',
    NULL,
    '上架'
),
(
    'REST005',
    '防滑餐墊四入組',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '餐廳'),
    259,
    70,
    '防水防滑餐桌墊四入組',
    NULL,
    '上架'
),
(
    'REST006',
    '木製托盤',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '餐廳'),
    349,
    40,
    '適合端送餐點與飲品的木製托盤',
    NULL,
    '上架'
),
(
    'REST007',
    '陶瓷馬克杯',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '餐廳'),
    199,
    100,
    '簡約設計陶瓷馬克杯',
    NULL,
    '上架'
),
(
    'REST008',
    '雙層保溫杯',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '餐廳'),
    599,
    45,
    '不鏽鋼雙層真空保溫杯',
    NULL,
    '上架'
),
(
    'REST009',
    '餐巾紙收納盒',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '餐廳'),
    229,
    55,
    '木紋餐巾紙收納盒',
    NULL,
    '上架'
),
(
    'REST010',
    '玻璃調味罐三件組',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '餐廳'),
    329,
    65,
    '鹽、胡椒與香料玻璃調味罐',
    NULL,
    '上架'
)
ON DUPLICATE KEY UPDATE
    product_name = VALUES(product_name),
    category_id = VALUES(category_id),
    price = VALUES(price),
    stock_quantity = VALUES(stock_quantity),
    description = VALUES(description),
    image_url = VALUES(image_url),
    product_status = VALUES(product_status);


-- =====================================================
-- 家具區商品：10 項
-- =====================================================

INSERT INTO products (
    product_code,
    product_name,
    category_id,
    price,
    stock_quantity,
    description,
    image_url,
    product_status
)
VALUES
(
    'FURN001',
    '實木餐桌',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '家具'),
    4990,
    15,
    '四人使用實木餐桌',
    NULL,
    '上架'
),
(
    'FURN002',
    '簡約餐椅',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '家具'),
    1290,
    40,
    '簡約木質靠背餐椅',
    NULL,
    '上架'
),
(
    'FURN003',
    '三人布沙發',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '家具'),
    8990,
    10,
    '舒適三人座布面沙發',
    NULL,
    '上架'
),
(
    'FURN004',
    '雙層茶几',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '家具'),
    2390,
    20,
    '附下層收納空間的客廳茶几',
    NULL,
    '上架'
),
(
    'FURN005',
    '五層收納櫃',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '家具'),
    1790,
    30,
    '五層開放式收納櫃',
    NULL,
    '上架'
),
(
    'FURN006',
    '床頭櫃',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '家具'),
    990,
    35,
    '附抽屜的小型床頭櫃',
    NULL,
    '上架'
),
(
    'FURN007',
    '電腦書桌',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '家具'),
    2990,
    18,
    '適合居家辦公的電腦書桌',
    NULL,
    '上架'
),
(
    'FURN008',
    '人體工學辦公椅',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '家具'),
    3990,
    22,
    '可調整高度與椅背的辦公椅',
    NULL,
    '上架'
),
(
    'FURN009',
    '三層鞋櫃',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '家具'),
    1590,
    28,
    '玄關用三層鞋櫃',
    NULL,
    '上架'
),
(
    'FURN010',
    '落地衣帽架',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '家具'),
    799,
    45,
    '可懸掛衣物與帽子的落地架',
    NULL,
    '上架'
)
ON DUPLICATE KEY UPDATE
    product_name = VALUES(product_name),
    category_id = VALUES(category_id),
    price = VALUES(price),
    stock_quantity = VALUES(stock_quantity),
    description = VALUES(description),
    image_url = VALUES(image_url),
    product_status = VALUES(product_status);


-- =====================================================
-- 廚具區商品：10 項
-- =====================================================

INSERT INTO products (
    product_code,
    product_name,
    category_id,
    price,
    stock_quantity,
    description,
    image_url,
    product_status
)
VALUES
(
    'KITC001',
    '不沾平底鍋',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '廚具'),
    799,
    50,
    '二十八公分不沾平底鍋',
    NULL,
    '上架'
),
(
    'KITC002',
    '不鏽鋼湯鍋',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '廚具'),
    1090,
    35,
    '附玻璃鍋蓋的不鏽鋼湯鍋',
    NULL,
    '上架'
),
(
    'KITC003',
    '主廚刀',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '廚具'),
    699,
    55,
    '適合切肉與蔬菜的主廚刀',
    NULL,
    '上架'
),
(
    'KITC004',
    '竹製砧板',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '廚具'),
    399,
    60,
    '天然竹材製成的料理砧板',
    NULL,
    '上架'
),
(
    'KITC005',
    '矽膠鍋鏟',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '廚具'),
    199,
    100,
    '耐高溫矽膠料理鍋鏟',
    NULL,
    '上架'
),
(
    'KITC006',
    '料理夾',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '廚具'),
    169,
    90,
    '不鏽鋼防滑料理夾',
    NULL,
    '上架'
),
(
    'KITC007',
    '瀝水籃',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '廚具'),
    299,
    70,
    '蔬果與餐具皆可使用的瀝水籃',
    NULL,
    '上架'
),
(
    'KITC008',
    '玻璃保鮮盒三件組',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '廚具'),
    649,
    50,
    '耐熱玻璃保鮮盒三件組',
    NULL,
    '上架'
),
(
    'KITC009',
    '量杯量匙組',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '廚具'),
    249,
    75,
    '烘焙與料理用量杯量匙組',
    NULL,
    '上架'
),
(
    'KITC010',
    '旋轉調味料架',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '廚具'),
    899,
    25,
    '可旋轉式多格調味料收納架',
    NULL,
    '上架'
)
ON DUPLICATE KEY UPDATE
    product_name = VALUES(product_name),
    category_id = VALUES(category_id),
    price = VALUES(price),
    stock_quantity = VALUES(stock_quantity),
    description = VALUES(description),
    image_url = VALUES(image_url),
    product_status = VALUES(product_status);


-- =====================================================
-- 玩偶區商品：10 項
-- =====================================================

INSERT INTO products (
    product_code,
    product_name,
    category_id,
    price,
    stock_quantity,
    description,
    image_url,
    product_status
)
VALUES
(
    'DOLL001',
    '泰迪熊玩偶',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '玩偶'),
    499,
    50,
    '柔軟棕色泰迪熊玩偶',
    NULL,
    '上架'
),
(
    'DOLL002',
    '白兔玩偶',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '玩偶'),
    399,
    60,
    '長耳朵白兔絨毛玩偶',
    NULL,
    '上架'
),
(
    'DOLL003',
    '柴犬玩偶',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '玩偶'),
    459,
    55,
    '可愛柴犬造型絨毛玩偶',
    NULL,
    '上架'
),
(
    'DOLL004',
    '企鵝玩偶',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '玩偶'),
    429,
    45,
    '黑白企鵝造型玩偶',
    NULL,
    '上架'
),
(
    'DOLL005',
    '恐龍玩偶',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '玩偶'),
    549,
    40,
    '綠色恐龍造型玩偶',
    NULL,
    '上架'
),
(
    'DOLL006',
    '長頸鹿玩偶',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '玩偶'),
    599,
    30,
    '長頸鹿造型大型玩偶',
    NULL,
    '上架'
),
(
    'DOLL007',
    '小象玩偶',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '玩偶'),
    459,
    50,
    '灰色小象造型玩偶',
    NULL,
    '上架'
),
(
    'DOLL008',
    '貓咪抱枕玩偶',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '玩偶'),
    699,
    35,
    '可作為抱枕使用的貓咪玩偶',
    NULL,
    '上架'
),
(
    'DOLL009',
    '羊駝玩偶',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '玩偶'),
    529,
    42,
    '柔軟羊駝造型絨毛玩偶',
    NULL,
    '上架'
),
(
    'DOLL010',
    '狐狸玩偶',
    (SELECT category_id
     FROM product_categories
     WHERE category_name = '玩偶'),
    479,
    48,
    '橘色狐狸造型絨毛玩偶',
    NULL,
    '上架'
)
ON DUPLICATE KEY UPDATE
    product_name = VALUES(product_name),
    category_id = VALUES(category_id),
    price = VALUES(price),
    stock_quantity = VALUES(stock_quantity),
    description = VALUES(description),
    image_url = VALUES(image_url),
    product_status = VALUES(product_status);