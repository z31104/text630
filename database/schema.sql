CREATE DATABASE IF NOT EXISTS smart_member_system;
USE smart_member_system;

CREATE TABLE IF NOT EXISTS members (
    member_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    phone VARCHAR(20),
    email VARCHAR(100),
    vip BOOLEAN DEFAULT FALSE,
    line_id VARCHAR(100),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS face_images (
    face_id INT AUTO_INCREMENT PRIMARY KEY,
    member_id INT NOT NULL,
    image_path VARCHAR(255) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (member_id) REFERENCES members(member_id)
);

CREATE TABLE IF NOT EXISTS recognition_logs (
    log_id INT AUTO_INCREMENT PRIMARY KEY,
    member_id INT NULL,
    name VARCHAR(50),
    vip BOOLEAN DEFAULT FALSE,
    line_id VARCHAR(100),
    confidence FLOAT DEFAULT 0,
    recognized_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    camera_location VARCHAR(100),
    FOREIGN KEY (member_id) REFERENCES members(member_id)
);

CREATE TABLE IF NOT EXISTS vip_notifications (
    notification_id INT AUTO_INCREMENT PRIMARY KEY,
    member_id INT NOT NULL,
    log_id INT,
    line_id VARCHAR(100),
    message TEXT,
    status VARCHAR(20) DEFAULT 'pending',
    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (member_id) REFERENCES members(member_id),
    FOREIGN KEY (log_id) REFERENCES recognition_logs(log_id)
);