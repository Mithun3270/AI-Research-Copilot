import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from backend.config import settings

logger = logging.getLogger("EmailService")

class EmailService:
    @staticmethod
    def _send_smtp_email(to_email: str, subject: str, html_content: str, text_content: str) -> bool:
        """Sends an email via SMTP or falls back to development logging."""
        if not settings.SMTP_HOST or not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
            logger.info("=" * 65)
            logger.info(f" [DEV EMAIL SERVICE] Email to: {to_email}")
            logger.info(f" [DEV EMAIL SERVICE] Subject: {subject}")
            logger.info(f" [DEV EMAIL SERVICE] Content Preview:\n{text_content}")
            logger.info("=" * 65)
            return True

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = settings.EMAIL_FROM
            msg["To"] = to_email

            part1 = MIMEText(text_content, "plain")
            part2 = MIMEText(html_content, "html")
            msg.attach(part1)
            msg.attach(part2)

            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
                server.starttls()
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.sendmail(settings.EMAIL_FROM, to_email, msg.as_string())

            logger.info(f"Email successfully dispatched to {to_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}", exc_info=True)
            return False

    @classmethod
    def send_verification_email(cls, to_email: str, full_name: str, token: str) -> bool:
        """Constructs and sends the email verification link."""
        verification_link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
        subject = "Verify Your Account - AI Research Copilot"

        text_content = f"""Hello {full_name},

Thank you for registering on AI Research Copilot!
Please verify your email address by opening the following link in your browser:

{verification_link}

This verification link will expire in {settings.VERIFICATION_TOKEN_EXPIRE_HOURS} hours.

If you did not create this account, please disregard this message.

Warm regards,
AI Research Copilot Team
"""

        html_content = f"""
        <html>
          <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #24292e; background-color: #f6f8fa; padding: 24px;">
            <div style="max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 8px; border: 1px solid #e1e4e8; padding: 32px;">
              <h2 style="color: #0366d6; margin-top: 0;">AI Research Copilot</h2>
              <p>Hello <strong>{full_name}</strong>,</p>
              <p>Welcome to <strong>AI Research Copilot</strong> — your intelligent research-paper assistant.</p>
              <p>Please click the button below to verify your email address and activate your account:</p>
              <div style="text-align: center; margin: 30px 0;">
                <a href="{verification_link}" style="background-color: #2ea44f; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Verify Email Address</a>
              </div>
              <p style="font-size: 13px; color: #586069;">Or copy and paste this link into your browser:</p>
              <p style="font-size: 12px; word-break: break-all; color: #0366d6;"><a href="{verification_link}">{verification_link}</a></p>
              <hr style="border: none; border-top: 1px solid #eaecef; margin: 24px 0;" />
              <p style="font-size: 12px; color: #6a737d;">This link will expire in {settings.VERIFICATION_TOKEN_EXPIRE_HOURS} hours. If you did not create an account, you can safely ignore this email.</p>
            </div>
          </body>
        </html>
        """
        return cls._send_smtp_email(to_email, subject, html_content, text_content)

    @classmethod
    def send_password_reset_email(cls, to_email: str, full_name: str, token: str) -> bool:
        """Constructs and sends the password reset link."""
        reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        subject = "Reset Your Password - AI Research Copilot"

        text_content = f"""Hello {full_name},

We received a request to reset your password for AI Research Copilot.
You can reset your password using the link below:

{reset_link}

This link is valid for {settings.RESET_TOKEN_EXPIRE_HOURS} hour only.

If you did not request a password reset, you can safely ignore this email.

Warm regards,
AI Research Copilot Team
"""

        html_content = f"""
        <html>
          <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #24292e; background-color: #f6f8fa; padding: 24px;">
            <div style="max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 8px; border: 1px solid #e1e4e8; padding: 32px;">
              <h2 style="color: #d73a49; margin-top: 0;">Password Reset Request</h2>
              <p>Hello <strong>{full_name}</strong>,</p>
              <p>We received a request to reset your password for AI Research Copilot.</p>
              <div style="text-align: center; margin: 30px 0;">
                <a href="{reset_link}" style="background-color: #d73a49; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Reset Password</a>
              </div>
              <p style="font-size: 13px; color: #586069;">Or copy and paste this link into your browser:</p>
              <p style="font-size: 12px; word-break: break-all; color: #0366d6;"><a href="{reset_link}">{reset_link}</a></p>
              <hr style="border: none; border-top: 1px solid #eaecef; margin: 24px 0;" />
              <p style="font-size: 12px; color: #6a737d;">This link expires in {settings.RESET_TOKEN_EXPIRE_HOURS} hour. If you did not make this request, your account remains secure and no action is required.</p>
            </div>
          </body>
        </html>
        """
        return cls._send_smtp_email(to_email, subject, html_content, text_content)

email_service = EmailService()
