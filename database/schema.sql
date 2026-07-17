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
CREATE TABLE IF NOT EXISTS members (
    member_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    phone VARCHAR(20),
    birthday DATE NULL,
    vip BOOLEAN DEFAULT FALSE,
    member_level VARCHAR(20) DEFAULT 'normal',
    visit_count INT DEFAULT 0,
    line_user_id VARCHAR(100),
    total_amount INT DEFAULT 0,
    favorite_product VARCHAR(100),
    face_image VARCHAR(255),
    registration_source VARCHAR(20) DEFAULT 'line',
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
    visit_count INT DEFAULT 0,
    first_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_seen_at DATETIME NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
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
    stay_seconds INT DEFAULT 0,
    stay_minutes DECIMAL(10,2) DEFAULT 0,
    camera_location VARCHAR(100),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

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
    issued_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    used_at DATETIME,
    FOREIGN KEY (member_id) REFERENCES members(member_id) ON DELETE CASCADE,
    FOREIGN KEY (coupon_id) REFERENCES coupons(coupon_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS lottery_records (
    lottery_id INT AUTO_INCREMENT PRIMARY KEY,
    member_id INT NULL,
    coupon_id INT NULL,
    prize_name VARCHAR(100),
    result VARCHAR(100),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (member_id) REFERENCES members(member_id) ON DELETE SET NULL,
    FOREIGN KEY (coupon_id) REFERENCES coupons(coupon_id) ON DELETE SET NULL
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
INSERT IGNORE INTO product_categories (
    category_name,
    description
)
VALUES
('沙發', '客廳沙發與扶手椅'),
('桌椅', '餐桌、書桌與各類座椅'),
('收納', '收納櫃、層架與收納盒'),
('燈具', '桌燈、立燈與吊燈'),
('寢具', '床架、床墊與寢具用品');


INSERT IGNORE INTO products (
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
    'SOFA001',
    'KIVIK 三人座沙發',
    1,
    24990,
    10,
    '舒適寬敞的三人座沙發',
    '/static/images/kivik_sofa.jpg',
    '上架'
),
(
    'SOFA002',
    'EKTORP 雙人座沙發',
    1,
    18990,
    8,
    '經典造型雙人座沙發，椅套可拆洗',
    '/static/images/ektorp_sofa.jpg',
    '上架'
),
(
    'TABLE001',
    'LACK 邊桌',
    2,
    399,
    50,
    '簡約輕巧的客廳邊桌',
    '/static/images/lack_table.jpg',
    '上架'
),
(
    'CHAIR001',
    'POÄNG 扶手椅',
    2,
    3999,
    20,
    '符合人體工學的彎曲木製扶手椅',
    '/static/images/poang_chair.jpg',
    '上架'
),
(
    'STORAGE001',
    'KALLAX 層架組',
    3,
    2999,
    25,
    '適合客廳與臥室的收納層架',
    '/static/images/kallax.jpg',
    '上架'
),
(
    'STORAGE002',
    'BILLY 書櫃',
    3,
    2499,
    18,
    '經典簡約多層書櫃，適合居家收納',
    '/static/images/billy_bookcase.jpg',
    '上架'
),
(
    'LIGHT001',
    'TERTIAL 工作燈',
    4,
    699,
    30,
    '可調整方向的工作桌燈',
    '/static/images/tertial.jpg',
    '上架'
),
(
    'LIGHT002',
    'HEKTAR 立燈',
    4,
    1999,
    15,
    '工業風可調整式立燈',
    '/static/images/hektar_floor_lamp.jpg',
    '上架'
),
(
    'BED001',
    'MALM 雙人床架',
    5,
    8999,
    12,
    '簡約設計雙人床架',
    '/static/images/malm_bed.jpg',
    '上架'
),
(
    'BED002',
    'HEMNES 單人床框',
    5,
    12990,
    6,
    '附收納抽屜的多功能單人床框',
    '/static/images/hemnes_bed.jpg',
    '上架'
);