"""
Migration: Add audit log + verification columns to web_matrix_space_settings
Run: source /srv/ch-webserver/chwebsiteprj/bin/activate && python3 alter_matrix_space_settings_audit_verify.py
"""
from app.db import get_engine
from sqlalchemy import text

def run():
    engine = get_engine()
    cols = [
        "ALTER TABLE web_matrix_space_settings ADD COLUMN IF NOT EXISTS audit_log_enabled TINYINT NOT NULL DEFAULT 0",
        "ALTER TABLE web_matrix_space_settings ADD COLUMN IF NOT EXISTS audit_log_room_id VARCHAR(255) NULL",
        "ALTER TABLE web_matrix_space_settings ADD COLUMN IF NOT EXISTS audit_event_config TEXT NULL",
        "ALTER TABLE web_matrix_space_settings ADD COLUMN IF NOT EXISTS verification_type VARCHAR(20) NOT NULL DEFAULT 'none'",
        "ALTER TABLE web_matrix_space_settings ADD COLUMN IF NOT EXISTS verification_room_id VARCHAR(255) NULL",
        "ALTER TABLE web_matrix_space_settings ADD COLUMN IF NOT EXISTS verification_account_age_days INT NOT NULL DEFAULT 7",
        "ALTER TABLE web_matrix_space_settings ADD COLUMN IF NOT EXISTS verification_verified_message TEXT NULL",
        "ALTER TABLE web_matrix_space_settings ADD COLUMN IF NOT EXISTS verification_failed_message TEXT NULL",
    ]
    with engine.connect() as conn:
        for sql in cols:
            print(f"Running: {sql[:80]}...")
            conn.execute(text(sql))
        conn.commit()
    print("Done.")

if __name__ == '__main__':
    run()
