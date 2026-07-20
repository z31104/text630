USE smart_member_system;

SET @sql = (
    SELECT IF(
        COUNT(*) = 0,
        'ALTER TABLE members ADD COLUMN last_visit_time DATETIME NULL AFTER visit_count',
        'SELECT "members.last_visit_time 已存在"'
    )
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'members'
      AND COLUMN_NAME = 'last_visit_time'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


SET @sql = (
    SELECT IF(
        COUNT(*) = 0,
        'ALTER TABLE members ADD COLUMN total_visit_time INT NOT NULL DEFAULT 0 AFTER last_visit_time',
        'SELECT "members.total_visit_time 已存在"'
    )
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'members'
      AND COLUMN_NAME = 'total_visit_time'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


SET @sql = (
    SELECT IF(
        COUNT(*) = 0,
        'ALTER TABLE members ADD COLUMN total_visit_count INT NOT NULL DEFAULT 0 AFTER total_visit_time',
        'SELECT "members.total_visit_count 已存在"'
    )
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'members'
      AND COLUMN_NAME = 'total_visit_count'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


SET @sql = (
    SELECT IF(
        COUNT(*) = 0,
        'ALTER TABLE members ADD COLUMN updated_by VARCHAR(100) NULL AFTER total_visit_count',
        'SELECT "members.updated_by 已存在"'
    )
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'members'
      AND COLUMN_NAME = 'updated_by'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
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

-- 若 lottery_records 已有 prize_id，
-- 但還沒有 prize_id 外鍵，才解除註解單獨執行一次
/*
ALTER TABLE lottery_records
ADD CONSTRAINT fk_lottery_records_prize
FOREIGN KEY (prize_id)
REFERENCES lottery_prizes(prize_id)
ON DELETE RESTRICT;
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

UPDATE members
SET total_visit_count = COALESCE(visit_count, 0)
WHERE total_visit_count = 0;