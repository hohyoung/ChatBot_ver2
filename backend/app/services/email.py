from __future__ import annotations
import os
import smtplib
from email.mime.text import MIMEText
from app.services.logging import get_logger

log = get_logger("app.services.email")

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "no-reply@soosan.co.kr")


def send_email(to: str, subject: str, text: str) -> bool:
    # SMTP 미설정 시 실제 발송 대신 로그로 대체(개발 편의)
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASS:
        log.warning(
            "[DEV] SMTP 미설정. 가짜 발송: to=%s subject=%s body=%s", to, subject, text
        )
        return True
    try:
        msg = MIMEText(text, _charset="utf-8")
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = to
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_FROM, [to], msg.as_string())
        return True
    except Exception as e:
        log.exception("메일 발송 실패: %s", e)
        return False
