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