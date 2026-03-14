"""
Migration: Create web_matrix_audit_log table
Run: source /srv/ch-webserver/chwebsiteprj/bin/activate && python3 create_matrix_audit_log_table.py
"""
from app.db import get_engine
from sqlalchemy import text

def run():
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS web_matrix_audit_log (
                id            INT AUTO_INCREMENT PRIMARY KEY,
                space_id      VARCHAR(255) NOT NULL,
                action        VARCHAR(50)  NOT NULL,
                category      VARCHAR(20)  NULL,
                actor_matrix_id      VARCHAR(255) NULL,
                actor_display_name   VARCHAR(200) NULL,
                target_matrix_id     VARCHAR(255) NULL,
                target_display_name  VARCHAR(200) NULL,
                target_type          VARCHAR(20)  NULL,
                room_id       VARCHAR(255) NULL,
                room_name     VARCHAR(255) NULL,
                reason        VARCHAR(500) NULL,
                details       TEXT NULL,
                created_at    BIGINT NOT NULL DEFAULT 0,
                INDEX idx_matrix_audit_space_time (space_id, created_at),
                INDEX idx_matrix_audit_action (space_id, action)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))
        conn.commit()
    print("Done - web_matrix_audit_log created.")

if __name__ == '__main__':
    run()
