import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Any


class EmailService:
    def __init__(self, config: Dict[str, Any]):
        # Load SMTP configuration from config.json
        smtp_config = config.get("smtp", {})

        # SMTP server configuration from config.json
        self.smtp_host = smtp_config.get("host", "localhost")
        self.smtp_port = int(smtp_config.get("port", 25))
        self.smtp_user = smtp_config.get("user", "")
        self.smtp_password = smtp_config.get("password", "")
        self.use_tls = smtp_config.get("use_tls", False)
        self.use_ssl = smtp_config.get("use_ssl", False)
        self.default_from = smtp_config.get("from", "noreply@cyverse.org")

    def send_email(
        self,
        to: str | List[str],
        subject: str,
        text_body: str | None = None,
        html_body: str | None = None,
        from_email: str | None = None,
        bcc: str | List[str] | None = None,
    ) -> bool:
        """
        Send an email using SMTP.
        
        Args:
            to: Recipient email address(es)
            subject: Email subject
            text_body: Plain text body (optional)
            html_body: HTML body (optional)
            from_email: Sender email (optional, uses default if not provided)
            bcc: BCC email address(es) (optional)
            
        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        try:
            # Prepare message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = from_email or self.default_from
            
            # Handle recipients
            if isinstance(to, str):
                msg["To"] = to
                to_list = [to]
            else:
                msg["To"] = ", ".join(to)
                to_list = to
                
            # Handle BCC
            bcc_list = []
            if bcc:
                if isinstance(bcc, str):
                    bcc_list = [bcc]
                else:
                    bcc_list = bcc
            
            # Add text body
            if text_body:
                text_part = MIMEText(text_body, "plain")
                msg.attach(text_part)
            
            # Add HTML body
            if html_body:
                html_part = MIMEText(html_body, "html")
                msg.attach(html_part)
            
            # If neither text nor HTML body provided, raise an error
            if not text_body and not html_body:
                raise ValueError("Either text_body or html_body must be provided")
            
            # Send email
            all_recipients = to_list + bcc_list
            
            if self.use_ssl:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port)
                if self.use_tls:
                    server.starttls()
            
            if self.smtp_user and self.smtp_password:
                server.login(self.smtp_user, self.smtp_password)
            
            server.sendmail(from_email or self.default_from, all_recipients, msg.as_string())
            server.quit()
            
            return True
            
        except Exception as e:
            print(f"Failed to send email: {e}")
            return False