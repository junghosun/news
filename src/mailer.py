"""Send the digest as an HTML email over SMTP (STARTTLS)."""

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_email(smtp_host, smtp_port, username, password, sender, recipients, subject, html_body):
    smtp_host = str(smtp_host).strip()
    smtp_port = int(str(smtp_port).strip())
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    ctx = ssl.create_default_context()
    with smtplib.SMTP(smtp_host, smtp_port, timeout=60) as server:
        server.starttls(context=ctx)
        server.login(username, password)
        server.sendmail(sender, recipients, msg.as_string())
    print(f"Sent to {', '.join(recipients)}")
