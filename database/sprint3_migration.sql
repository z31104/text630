USE smart_member_system;

-- =====================================================
-- Sprint 3 資料庫升級檔
-- 注意：ALTER TABLE 與 CREATE INDEX 原則上只執行一次
-- =====================================================


-- 1. 檢查 members 是否已有 line_user_id
SHOW COLUMNS FROM members LIKE 'line_user_id';


-- 2. 若上一步沒有查到 line_user_id，
-- 請解除下方註解並單獨執行一次
/*
ALTER TABLE members
ADD COLUMN line_user_id VARCHAR(100) NULL
AFTER member_level;
*/


-- 3. 檢查是否已有重複 LINE ID
SELECT
    line_user_id,
    COUNT(*) AS duplicate_count
FROM members
WHERE line_user_id IS NOT NULL
  AND line_user_id <> ''
GROUP BY line_user_id
HAVING COUNT(*) > 1;


-- 4. 若沒有重複 LINE ID，
-- 且 members 尚未有 line_user_id 唯一索引，
-- 請解除下方註解並單獨執行一次
/*
ALTER TABLE members
ADD UNIQUE KEY uk_members_line_user_id (line_user_id);
*/


-- 5. 檢查 recognition_logs 目前有哪些索引
SHOW INDEX FROM recognition_logs;


-- 6. 若沒有 idx_recognition_visit_time，
-- 請解除下方註解並單獨執行一次
/*
CREATE INDEX idx_recognition_visit_time
ON recognition_logs (visit_time);
*/


-- =====================================================
-- Sprint 3 抽獎功能升級
-- =====================================================

-- 1. 建立抽獎獎品設定表
CREATE TABLE IF NOT EXISTS lottery_prizes (
    prize_id INT AUTO_INCREMENT PRIMARY KEY,
    prize_code VARCHAR(50) NOT NULL UNIQUE,
    prize_name VARCHAR(100) NOT NULL,
    prize_type VARCHAR(30) NOT NULL,
    prize_value DECIMAL(10,2) DEFAULT 0,
    probability_weight INT NOT NULL DEFAULT 1,
    stock_quantity INT NULL,
    prize_status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
);


-- 2. 檢查舊 lottery_records 欄位
SHOW COLUMNS FROM lottery_records;


-- 3. 若舊表缺少 prize_id，才單獨執行一次
/*
ALTER TABLE lottery_records
ADD COLUMN prize_id INT NULL
AFTER member_id;
*/


-- 4. 若舊表缺少 is_final，才單獨執行一次
/*
ALTER TABLE lottery_records
ADD COLUMN is_final BOOLEAN NOT NULL DEFAULT TRUE
AFTER result;
*/


-- 5. 若舊表缺少 redeemed，才單獨執行一次
/*
ALTER TABLE lottery_records
ADD COLUMN redeemed BOOLEAN NOT NULL DEFAULT FALSE
AFTER is_final;
*/


-- 6. 若舊表缺少 redeemed_at，才單獨執行一次
/*
ALTER TABLE lottery_records
ADD COLUMN redeemed_at DATETIME NULL
AFTER redeemed;
*/


-- 7. 檢查 lottery_records 索引
SHOW INDEX FROM lottery_records;


-- 8. 若沒有會員抽獎紀錄索引，才單獨執行一次
/*
CREATE INDEX idx_lottery_records_member_time
ON lottery_records (
    member_id,
    created_at
);
*/


-- 9. 建立六筆抽獎獎品
INSERT IGNORE INTO lottery_prizes (
    prize_code,
    prize_name,
    prize_type,
    prize_value,
    probability_weight,
    stock_quantity,
    prize_status
)
VALUES
    ('cash_50', '$50', 'coupon', 50, 1, NULL, 'active'),
    ('discount_90', '9折', 'discount', 0.90, 1, NULL, 'active'),
    ('cash_200', '$200', 'coupon', 200, 1, NULL, 'active'),
    ('gift', '小禮品', 'gift', 0, 1, NULL, 'active'),
    ('free_shipping', '免運', 'free_shipping', 0, 1, NULL, 'active'),
    ('retry', '再抽一次', 'retry', 0, 1, NULL, 'active');

-- 10. 檢查 lottery_records 是否已有 prize_id 外鍵
SELECT
    CONSTRAINT_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'lottery_records'
  AND COLUMN_NAME = 'prize_id'
  AND REFERENCED_TABLE_NAME IS NOT NULL;


-- 若上面沒有查到 prize_id 外鍵，
-- 才解除下方註解並單獨執行一次
/*
ALTER TABLE lottery_records
ADD CONSTRAINT fk_lottery_records_prize
FOREIGN KEY (prize_id)
REFERENCES lottery_prizes(prize_id)
ON DELETE RESTRICT;
*/    

-- =====================================================
-- Sprint 3 AI 人臉辨識與散客追蹤升級
-- =====================================================

-- 11. 建立散客主表
CREATE TABLE IF NOT EXISTS visitors (
    visitor_id INT AUTO_INCREMENT PRIMARY KEY,
    visitor_code VARCHAR(50) NOT NULL UNIQUE,
    display_name VARCHAR(50) DEFAULT 'Visitor',
    first_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    visit_count INT NOT NULL DEFAULT 0,
    last_seen_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_visitors_visitor_code (visitor_code),
    KEY idx_visitors_last_seen_at (last_seen_at)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- 12. 建立散客人臉資料表
CREATE TABLE IF NOT EXISTS visitor_faces (
    visitor_face_id INT AUTO_INCREMENT PRIMARY KEY
    visitor_id INT NOT NULL,
    image_path VARCHAR(255) NULL,
    encoding_data LONGTEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_visitor_faces_visitor_id (visitor_id),
    CONSTRAINT fk_visitor_faces_visitor
        FOREIGN KEY (visitor_id)
        REFERENCES visitors(visitor_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- 13. 建立安全新增欄位的程序
DROP PROCEDURE IF EXISTS add_column_if_missing;

DELIMITER $$
CREATE PROCEDURE add_column_if_missing(
    IN p_table_name VARCHAR(64),
    IN p_column_name VARCHAR(64),
    IN p_column_definition TEXT
)
BEGIN
    DECLARE v_column_count INT DEFAULT 0;

    SELECT COUNT(*)
      INTO v_column_count
      FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = DATABASE()
       AND TABLE_NAME = p_table_name
       AND COLUMN_NAME = p_column_name;

    IF v_column_count = 0 THEN
        SET @sql_text = CONCAT(
            'ALTER TABLE `', p_table_name,
            '` ADD COLUMN `', p_column_name,
            '` ', p_column_definition
        );

        PREPARE stmt FROM @sql_text;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END$$
DELIMITER ;


-- 14. 正式會員人臉特徵欄位
CALL add_column_if_missing(
    'face_images',
    'encoding_data',
    'LONGTEXT NULL AFTER image_path'
);


-- 15. recognition_logs 第三週 AI 欄位
CALL add_column_if_missing(
    'recognition_logs',
    'subject_type',
    'VARCHAR(20) NOT NULL DEFAULT ''member'' AFTER log_id'
);

CALL add_column_if_missing(
    'recognition_logs',
    'visitor_id',
    'INT NULL AFTER member_id'
);

CALL add_column_if_missing(
    'recognition_logs',
    'visitor_code',
    'VARCHAR(50) NULL AFTER visitor_id'
);

CALL add_column_if_missing(
    'recognition_logs',
    'last_seen_at',
    'DATETIME NULL AFTER recognized_at'
);

CALL add_column_if_missing(
    'recognition_logs',
    'leave_time',
    'DATETIME NULL AFTER last_seen_at'
);

CALL add_column_if_missing(
    'recognition_logs',
    'stay_seconds',
    'INT NOT NULL DEFAULT 0 AFTER leave_time'
);

CALL add_column_if_missing(
    'recognition_logs',
    'stay_minutes',
    'DECIMAL(10,2) NOT NULL DEFAULT 0 AFTER stay_seconds'
);

DROP PROCEDURE IF EXISTS add_column_if_missing;


-- 16. 建立安全新增索引的程序
DROP PROCEDURE IF EXISTS add_index_if_missing;

DELIMITER $$
CREATE PROCEDURE add_index_if_missing(
    IN p_table_name VARCHAR(64),
    IN p_index_name VARCHAR(64),
    IN p_index_columns VARCHAR(255)
)
BEGIN
    DECLARE v_index_count INT DEFAULT 0;

    SELECT COUNT(*)
      INTO v_index_count
      FROM information_schema.STATISTICS
     WHERE TABLE_SCHEMA = DATABASE()
       AND TABLE_NAME = p_table_name
       AND INDEX_NAME = p_index_name;

    IF v_index_count = 0 THEN
        SET @sql_text = CONCAT(
            'ALTER TABLE `', p_table_name,
            '` ADD INDEX `', p_index_name,
            '` ', p_index_columns
        );

        PREPARE stmt FROM @sql_text;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END$$
DELIMITER ;

CALL add_index_if_missing(
    'recognition_logs',
    'idx_recognition_subject_type',
    '(subject_type)'
);

CALL add_index_if_missing(
    'recognition_logs',
    'idx_recognition_visitor_id',
    '(visitor_id)'
);

CALL add_index_if_missing(
    'recognition_logs',
    'idx_recognition_visitor_code',
    '(visitor_code)'
);

CALL add_index_if_missing(
    'recognition_logs',
    'idx_recognition_last_seen_at',
    '(last_seen_at)'
);

CALL add_index_if_missing(
    'recognition_logs',
    'idx_recognition_leave_time',
    '(leave_time)'
);

CALL add_index_if_missing(
    'recognition_logs',
    'idx_recognition_active_visitor',
    '(subject_type, visitor_id, leave_time)'
);

DROP PROCEDURE IF EXISTS add_index_if_missing;


-- 17. recognition_logs.visitor_id 外鍵
DROP PROCEDURE IF EXISTS add_visitor_fk_if_missing;

DELIMITER $$
CREATE PROCEDURE add_visitor_fk_if_missing()
BEGIN
    DECLARE v_fk_count INT DEFAULT 0;

    SELECT COUNT(*)
      INTO v_fk_count
      FROM information_schema.KEY_COLUMN_USAGE
     WHERE TABLE_SCHEMA = DATABASE()
       AND TABLE_NAME = 'recognition_logs'
       AND COLUMN_NAME = 'visitor_id'
       AND REFERENCED_TABLE_NAME = 'visitors'
       AND REFERENCED_COLUMN_NAME = 'visitor_id';

    IF v_fk_count = 0 THEN
        ALTER TABLE recognition_logs
        ADD CONSTRAINT fk_recognition_logs_visitor
            FOREIGN KEY (visitor_id)
            REFERENCES visitors(visitor_id)
            ON DELETE SET NULL
            ON UPDATE CASCADE;
    END IF;
END$$
DELIMITER ;

CALL add_visitor_fk_if_missing();
DROP PROCEDURE IF EXISTS add_visitor_fk_if_missing;


-- 18. 舊會員辨識紀錄補上 subject_type
UPDATE recognition_logs
SET subject_type = 'member'
WHERE subject_type IS NULL
   OR subject_type = '';


-- 19. 執行後檢查
SHOW COLUMNS FROM face_images LIKE 'encoding_data';
SHOW COLUMNS FROM recognition_logs;
SHOW INDEX FROM recognition_logs;

SELECT
    CONSTRAINT_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('visitor_faces', 'recognition_logs')
  AND REFERENCED_TABLE_NAME IS NOT NULL;

SELECT 'Sprint 3 AI migration completed.' AS migration_result;