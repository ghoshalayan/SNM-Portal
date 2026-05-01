import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from typing import Optional

from sqlalchemy.orm import Session
from app.models.company import Company


class EmailService:
    @staticmethod
    def get_smtp_config(db: Session, company_id: int) -> Optional[dict]:
        company = db.query(Company).filter(
            Company.companyId == company_id,
            Company.isActive == True,
        ).first()

        if not company or not company.SMTP or not company.MailFrom:
            return None

        return {
            "smtp_host": company.SMTP,
            "smtp_port": int(company.PortNo) if company.PortNo else 587,
            "mail_from": company.MailFrom,
            "mail_password": company.MailPassword,
        }

    @staticmethod
    def send_email(
        smtp_config: dict,
        to_email: str,
        subject: str,
        html_body: str,
        attachment: Optional[bytes] = None,
        attachment_filename: Optional[str] = None,
    ) -> bool:
        msg = MIMEMultipart()
        msg["From"] = smtp_config["mail_from"]
        msg["To"] = to_email
        msg["Subject"] = subject

        msg.attach(MIMEText(html_body, "html"))

        if attachment and attachment_filename:
            part = MIMEApplication(attachment, Name=attachment_filename)
            part["Content-Disposition"] = f'attachment; filename="{attachment_filename}"'
            msg.attach(part)

        with smtplib.SMTP(smtp_config["smtp_host"], smtp_config["smtp_port"]) as server:
            server.starttls()
            if smtp_config.get("mail_password"):
                server.login(smtp_config["mail_from"], smtp_config["mail_password"])
            server.send_message(msg)

        return True

    @staticmethod
    def fill_template(template: str, placeholders: dict) -> str:
        result = template
        for key, value in placeholders.items():
            result = result.replace(f"{{{{{key}}}}}", str(value or ""))
        return result


email_service = EmailService()
