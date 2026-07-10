CREATE DATABASE IF NOT EXISTS smart_member_system
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE smart_member_system;

CREATE TABLE IF NOT EXISTS members (
    member_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    phone VARCHAR(20),
    vip BOOLEAN DEFAULT FALSE,
    member_level VARCHAR(20) DEFAULT '一般會員',
    visit_count INT DEFAULT 0,
    line_user_id VARCHAR(100),
    total_amount INT DEFAULT 0,
    favorite_product VARCHAR(100),
    face_image VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS face_images (
    face_id INT AUTO_INCREMENT PRIMARY KEY,
    member_id INT NOT NULL,
    image_path VARCHAR(255) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (member_id) REFERENCES members(member_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS recognition_logs (
    log_id INT AUTO_INCREMENT PRIMARY KEY,

    member_id INT NULL,
    camera_id VARCHAR(50),

    name VARCHAR(50),
    vip BOOLEAN DEFAULT FALSE,
    line_user_id VARCHAR(100),

    confidence FLOAT DEFAULT 0,
    member_level VARCHAR(20),
    recognition_status VARCHAR(30),
    visit_status VARCHAR(30),

    recognized_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    visit_time DATETIME,
    leave_time DATETIME,
    stay_minutes INT DEFAULT 0,

    camera_location VARCHAR(100),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (member_id) REFERENCES members(member_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS vip_notifications (
    notification_id INT AUTO_INCREMENT PRIMARY KEY,
    member_id INT NOT NULL,
    log_id INT,
    line_user_id VARCHAR(100),
    message TEXT,
    status VARCHAR(20) DEFAULT 'pending',
    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (member_id) REFERENCES members(member_id),
    FOREIGN KEY (log_id) REFERENCES recognition_logs(log_id)
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