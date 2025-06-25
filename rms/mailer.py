# rms/mailer.py

from smtplib import SMTP, SMTP_SSL, SMTPException
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from flask import current_app, render_template, url_for
from datetime import datetime
from zoneinfo import ZoneInfo

PST = ZoneInfo("America/Los_Angeles")


def fmt_pst(d):
    """Format any date/datetime as YY/MM/DD in Pacific time."""
    if not d:
        return "-"
    if isinstance(d, datetime):
        d = d.astimezone(PST)
    return d.strftime("%y/%m/%d")


def smtp_send(to_addr: str, subject: str, text: str, attachments=None) -> bool:
    """
    Low-level SMTP send.  `attachments` is a list of
    (bytes, filename, mime_subtype) tuples.
    """
    cfg = current_app.config

    port   = cfg.get("MAIL_SMTP_PORT", cfg.get("SMTP_PORT", 587))
    server = cfg.get("MAIL_SMTP_SERVER", cfg.get("SMTP_SERVER"))
    user   = cfg.get("MAIL_SMTP_USER",   cfg.get("SMTP_USER", ""))
    pw     = cfg.get("MAIL_SMTP_PASS",   cfg.get("SMTP_PASS", ""))
    use_tls= cfg.get("MAIL_USE_TLS",     True)

    # build the message
    msg = MIMEMultipart("mixed")
    msg["From"]    = cfg["MAIL_FROM"]
    msg["To"]      = to_addr
    msg["Subject"] = subject

    # plain-text part
    msg.attach(MIMEText(text, "plain", _charset="utf-8"))

    # attachments (e.g. PDF)
    if attachments:
        for data, filename, subtype in attachments:
            part = MIMEApplication(data, _subtype=subtype)
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="{filename}"'
            )
            msg.attach(part)

    # connect & send
    use_ssl = (port == 465)
    SMTPClass = SMTP_SSL if use_ssl else SMTP

    try:
        with SMTPClass(server, port) as s:
            s.ehlo()
            if not use_ssl and use_tls:
                s.starttls()
                s.ehlo()
            if user:
                try:
                    s.login(user, pw)
                except SMTPException as e:
                    current_app.logger.warning(f"SMTP login failed, continuing without auth: {e}")
            s.send_message(msg)
        return True

    except SMTPException as e:
        current_app.logger.error(f"SMTP error sending to {to_addr}: {e}")
        return False


def send_return_notice(
    to_addr: str,
    r,
    event: str,
    total_credit: float = None,
    view_url: str = None,
    attachment_bytes: bytes = None,
    attachment_filename: str = None
) -> bool:
    """
    Send a Return notification email, using templates:
      - plain‐text: templates/emails/{event}_return.txt
      - html:       templates/emails/{event}_return.html  (optional)
    You can pass:
      • total_credit  (will be summed from r.items if omitted)
      • view_url      (a direct link; default is detail page)
      • attachment_bytes/attachment_filename for a PDF.
    """
    # pick up defaults
    if total_credit is None:
        total_credit = sum(float(it.credit_amount) for it in r.items)
    if view_url is None:
        view_url = url_for("returns.return_detail", id=r.id, _external=True)

    # build context
    ctx = {
        "r": r,
        "rep_name": r.rep_name,
        "fmt_pst": fmt_pst,
        "total_credit": total_credit,
        "view_url": view_url,
        "company_name": current_app.config.get("COMPANY_NAME", "ReturnApp")
    }

    # render text
    txt_tpl = f"emails/{event}.txt"
    text_body = render_template(txt_tpl, **ctx)

    # try html
    html_body = None
    html_tpl = f"emails/{event}.html"
    try:
        html_body = render_template(html_tpl, **ctx)
    except Exception:
        pass

    # assemble mixed/alternative
    msg = MIMEMultipart("mixed")
    msg["From"]    = current_app.config["MAIL_FROM"]
    msg["To"]      = to_addr
    msg["Subject"] = f"Return #{r.id} – {event.replace('_',' ').title()}"

    # alternative part
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(text_body, "plain", _charset="utf-8"))
    if html_body:
        alt.attach(MIMEText(html_body, "html",  _charset="utf-8"))
    msg.attach(alt)

    # optional PDF
    if attachment_bytes and attachment_filename:
        part = MIMEApplication(attachment_bytes, _subtype="pdf")
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{attachment_filename}"'
        )
        msg.attach(part)

    # send
    cfg = current_app.config
    port   = cfg.get("MAIL_SMTP_PORT", cfg.get("SMTP_PORT", 587))
    server = cfg.get("MAIL_SMTP_SERVER", cfg.get("SMTP_SERVER"))
    user   = cfg.get("MAIL_SMTP_USER",   cfg.get("SMTP_USER", ""))
    pw     = cfg.get("MAIL_SMTP_PASS",   cfg.get("SMTP_PASS", ""))
    use_tls= cfg.get("MAIL_USE_TLS",     True)

    use_ssl = (port == 465)
    SMTPClass = SMTP_SSL if use_ssl else SMTP

    try:
        with SMTPClass(server, port) as s:
            s.ehlo()
            if not use_ssl and use_tls:
                s.starttls(); s.ehlo()
            if user:
                try:
                    s.login(user, pw)
                except SMTPException as e:
                    current_app.logger.warning(f"SMTP login failed, continuing without auth: {e}")
            s.send_message(msg)
        return True
    except SMTPException as e:
        current_app.logger.error(f"SMTP error sending to {to_addr}: {e}")
        return False
