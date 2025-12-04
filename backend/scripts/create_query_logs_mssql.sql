-- MSSQL용 query_logs 테이블 생성 스크립트

-- 테이블이 이미 있으면 삭제 (선택)
-- DROP TABLE IF EXISTS query_logs;

-- query_logs 테이블 생성
CREATE TABLE query_logs (
    id INT IDENTITY(1,1) PRIMARY KEY,
    question NVARCHAR(MAX) NOT NULL,
    answer_id NVARCHAR(50) NULL,
    user_id INT NULL,
    created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),

    -- Foreign Key 제약조건 (users 테이블이 있는 경우)
    CONSTRAINT FK_query_logs_user_id
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE SET NULL  -- 사용자 삭제 시 user_id를 NULL로 설정
);

-- 인덱스 생성 (성능 향상)
CREATE INDEX idx_query_logs_created_at ON query_logs(created_at);
CREATE INDEX idx_query_logs_user_id ON query_logs(user_id);

-- 생성 확인
SELECT
    'query_logs table created successfully!' AS message,
    COUNT(*) AS initial_record_count
FROM query_logs;
