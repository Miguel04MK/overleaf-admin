"""
notification_service.py
-----------------------
Email notification system for admin alerts — batch/summary mode.

Instead of sending one email per alert, this module accumulates pending alerts
(those with email_notified_at IS NULL) and sends a single summary email per
admin with only the alerts matching that admin's notification preferences.

SMTP configuration via environment variables (all optional — app works without):

  SMTP_HOST       — SMTP server hostname (e.g. smtp.gmail.com)
  SMTP_PORT       — port (default 587)
  SMTP_USER       — username for SMTP auth (e.g. your Gmail address)
  SMTP_PASSWORD   — password or app-specific password
  SMTP_FROM       — From address (default: SMTP_USER or alertas@overleaf-admin.local)
  SMTP_USE_TLS    — "true" (default) to use STARTTLS
  APP_BASE_URL    — Base URL for links in emails (e.g. http://localhost:5000)

  SMTP_MOCK       — "true" (default in dev) to log emails to console instead of sending.
                     Set to "false" and configure SMTP_HOST/USER/PASSWORD to send real emails.

Gmail setup (app-specific password):
  1. Enable 2FA on your Google account
  2. Go to https://myaccount.google.com/apppasswords
  3. Create an app password for "Mail"
  4. Set SMTP_HOST=smtp.gmail.com, SMTP_PORT=587, SMTP_USE_TLS=true
  5. Set SMTP_USER=your-email@gmail.com, SMTP_PASSWORD=xxxx-xxxx-xxxx-xxxx
  6. Set SMTP_MOCK=false
"""
import logging
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

# ── Configuration from environment ────────────────────────────────────────────

def _get_smtp_config() -> dict:
    """Read SMTP config from environment each time (not cached at import).

    This allows tests with TESTING=True to override SMTP_MOCK without
    reloading the module.
    """
    from flask import current_app
    # In a testing context, always mock
    try:
        if current_app and current_app.config.get("TESTING"):
            mock = True
        else:
            mock = os.getenv("SMTP_MOCK", "true").lower() in ("1", "true", "yes")
    except RuntimeError:
        mock = os.getenv("SMTP_MOCK", "true").lower() in ("1", "true", "yes")

    host     = os.getenv("SMTP_HOST",     "").strip()
    user     = os.getenv("SMTP_USER",     "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    return {
        "mock":     mock,
        "host":     host,
        "port":     int(os.getenv("SMTP_PORT", "587")),
        "user":     user,
        "password": password,
        "from":     os.getenv("SMTP_FROM", "").strip() or user or "alertas@overleaf-admin.local",
        "tls":      os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes"),
        "base_url": os.getenv("APP_BASE_URL", "http://localhost:5000").rstrip("/"),
    }

# Keep module-level aliases for _build_summary_body (only needs base_url)
_APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:5000").rstrip("/")

# Mapping alert level -> AdminNotificationPref attribute
_LEVEL_TO_PREF: dict[str, str] = {
    "critical": "notify_critical",
    "danger":   "notify_danger",
    "warning":  "notify_warning",
    "info":     "notify_info",
}

# Mapping alert type -> AdminNotificationPref attribute
_TYPE_TO_PREF: dict[str, str] = {
    "sync_failed":             "notify_sync_failed",
    "quota_exceeded":          "notify_quota_exceeded",
    "quota_warning":           "notify_quota_warning",
    "project_limit_exceeded":  "notify_project_limit_exceeded",
    "project_limit_warning":   "notify_project_limit_warning",
    "repeated_errors":         "notify_repeated_errors",
    "administrative_warning":  "notify_administrative_warning",
}

# Defaults when an admin has no pref row
_DEFAULT_LEVELS = {"critical", "danger"}
_DEFAULT_TYPES  = {"sync_failed", "quota_exceeded", "repeated_errors"}

_LEVEL_LABELS = {
    "critical": "Critico",
    "danger":   "Peligro",
    "warning":  "Aviso",
    "info":     "Informacion",
}

_TYPE_LABELS = {
    "quota_warning":          "Cuota cercana",
    "quota_exceeded":         "Cuota excedida",
    "project_limit_warning":  "Proyectos cercano al limite",
    "project_limit_exceeded": "Limite de proyectos superado",
    "sync_failed":            "Fallo de sincronizacion",
    "repeated_errors":        "Errores repetidos",
    "administrative_warning": "Aviso administrativo",
}


# ── Public API ────────────────────────────────────────────────────────────────

def should_notify(pref, alert_type: str, alert_level: str) -> bool:
    """Compat hacia atrás: True si el admin recibe la alerta en cualquier modo
    (inmediato o resumen). Las llamadas existentes que querían "¿debo enviar
    ya un email?" deben usar should_notify_now() en su lugar."""
    if pref is None:
        return alert_level in _DEFAULT_LEVELS or alert_type in _DEFAULT_TYPES

    level_attr = _LEVEL_TO_PREF.get(alert_level)
    type_attr  = _TYPE_TO_PREF.get(alert_type)
    level_ok   = bool(getattr(pref, level_attr, False)) if level_attr else False
    type_ok    = bool(getattr(pref, type_attr,  False)) if type_attr  else False
    return level_ok or type_ok


def should_notify_now(pref, alert_type: str, alert_level: str) -> bool:
    """True si el admin debe recibir un email INMEDIATO para esta alerta.

    Comprueba la pestaña "Inmediato" (notify_X = True para nivel o tipo).
    Cuando pref es None, asume "immediate" para los defaults conservadores.
    """
    if pref is None:
        return alert_level in _DEFAULT_LEVELS or alert_type in _DEFAULT_TYPES

    level_attr = _LEVEL_TO_PREF.get(alert_level)
    type_attr  = _TYPE_TO_PREF.get(alert_type)

    if hasattr(pref, "is_immediate"):
        level_ok = pref.is_immediate(level_attr) if level_attr else False
        type_ok  = pref.is_immediate(type_attr)  if type_attr  else False
    else:
        level_ok = bool(getattr(pref, level_attr, False)) if level_attr else False
        type_ok  = bool(getattr(pref, type_attr,  False)) if type_attr  else False

    return level_ok or type_ok


def should_include_in_digest(pref, alert_type: str, alert_level: str) -> bool:
    """True si la alerta debe entrar en el resumen periódico del admin.

    Comprueba la pestaña "Periódico" (notify_X_digest_only = True para nivel o tipo).
    Un tipo puede estar en AMBAS pestañas simultáneamente.
    """
    if pref is None:
        return False

    level_attr = _LEVEL_TO_PREF.get(alert_level)
    type_attr  = _TYPE_TO_PREF.get(alert_type)

    if hasattr(pref, "is_in_digest"):
        level_ok = pref.is_in_digest(level_attr) if level_attr else False
        type_ok  = pref.is_in_digest(type_attr)  if type_attr  else False
    else:
        level_ok = bool(getattr(pref, level_attr + "_digest_only", False)) if level_attr else False
        type_ok  = bool(getattr(pref, type_attr  + "_digest_only", False)) if type_attr  else False

    return level_ok or type_ok


def diagnose_smtp() -> dict:
    """
    Return a diagnostic dict about SMTP configuration.
    Useful for the test-email endpoint and logging.
    """
    cfg = _get_smtp_config()
    issues = []
    if cfg["mock"]:
        issues.append("SMTP_MOCK=true: los emails se imprimen en consola, no se envian.")
    if not cfg["host"] and not cfg["mock"]:
        issues.append("SMTP_HOST vacio: no se puede conectar a ningun servidor SMTP.")
    if not cfg["user"] and not cfg["mock"]:
        issues.append("SMTP_USER vacio: la mayoria de servidores SMTP requieren autenticacion.")
    if not cfg["password"] and not cfg["mock"]:
        issues.append("SMTP_PASSWORD vacio: la autenticacion SMTP fallara.")

    return {
        "mock":     cfg["mock"],
        "host":     cfg["host"] or "(vacio)",
        "port":     cfg["port"],
        "user":     cfg["user"] or "(vacio)",
        "password": "****" if cfg["password"] else "(vacio)",
        "from":     cfg["from"],
        "tls":      cfg["tls"],
        "base_url": cfg["base_url"],
        "issues":   issues,
        "ready":    cfg["mock"] or (bool(cfg["host"]) and bool(cfg["user"]) and bool(cfg["password"])),
    }


def get_pending_alerts() -> list:
    """Return all alerts that have NOT been email-notified yet."""
    from app.model.entities.system_alert import SystemAlert
    alerts = (
        SystemAlert.query
        .filter(SystemAlert.email_notified_at.is_(None))
        .filter_by(is_resolved=False)
        .order_by(SystemAlert.created_at.desc())
        .all()
    )
    logger.info("[EMAIL] Alertas pendientes de notificacion: %d", len(alerts))
    return alerts


def send_test_email(to_email: str) -> tuple[bool, str]:
    """
    Send a simple diagnostic email to verify SMTP configuration.
    Returns (success, message).
    """
    diag = diagnose_smtp()
    logger.info("[EMAIL TEST] Diagnostico SMTP: mock=%s, host=%s, user=%s, ready=%s",
                diag["mock"], diag["host"], diag["user"], diag["ready"])

    subject = "[Overleaf Admin] Correo de prueba"
    body = (
        "Este es un correo de prueba del sistema de alertas de Overleaf Admin.\n\n"
        f"Servidor SMTP: {diag['host']}:{diag['port']}\n"
        f"TLS: {'si' if diag['tls'] else 'no'}\n"
        f"Usuario: {diag['user']}\n"
        f"Modo mock: {'si' if diag['mock'] else 'no'}\n\n"
        "Si recibes este correo, la configuracion SMTP funciona correctamente.\n"
        f"\nEnviado desde: {_APP_BASE_URL}"
    )

    return _smtp_send(to_email, subject, body)


def send_summary_emails(actor: str = "system") -> dict:
    """
    Send a batch summary email to each active admin with their pending alerts.

    Each admin receives only the alerts matching their notification preferences.
    Alerts are marked with email_notified_at after successful processing.

    Returns a dict with counts: {sent, skipped, errors, alerts_notified, details}.
    """
    from app.config.extensions import db
    from app.model.entities.admin_user import AdminUser
    from app.model.entities.system_alert import SystemAlert
    from app.model.services.admin.admin_service import log_action

    # Step 1: Get pending alerts
    pending = get_pending_alerts()
    if not pending:
        logger.info("[EMAIL BATCH] No hay alertas pendientes de notificacion.")
        return {"sent": 0, "skipped": 0, "errors": 0,
                "alerts_notified": 0, "details": ["No hay alertas pendientes."]}

    # Step 2: Get active admins
    admins = AdminUser.query.filter_by(is_active=True).all()
    logger.info("[EMAIL BATCH] Admins activos encontrados: %d", len(admins))

    results = {"sent": 0, "skipped": 0, "errors": 0,
               "alerts_notified": 0, "details": []}
    notified_ids = set()

    # Step 3: For each admin, filter alerts by preferences and send
    for admin in admins:
        if not admin.email:
            logger.info("[EMAIL BATCH] Admin %s sin email, saltando.", admin.username)
            results["details"].append(f"{admin.username}: sin email configurado")
            results["skipped"] += 1
            continue

        pref = admin.notification_pref  # may be None
        logger.info("[EMAIL BATCH] Evaluando preferencias de %s (pref=%s)",
                    admin.username, "custom" if pref else "defaults")

        # Filter alerts for this admin's preferences
        admin_alerts = []
        for alert in pending:
            matches = should_notify(pref, alert.type, alert.level)
            if matches:
                admin_alerts.append(alert)
                logger.debug("[EMAIL BATCH]   - Alerta #%d (%s/%s) -> SI para %s",
                            alert.id, alert.level, alert.type, admin.username)
            else:
                logger.debug("[EMAIL BATCH]   - Alerta #%d (%s/%s) -> NO para %s",
                            alert.id, alert.level, alert.type, admin.username)

        if not admin_alerts:
            logger.info("[EMAIL BATCH] %s: 0 alertas coinciden con sus preferencias, saltando.",
                       admin.username)
            results["details"].append(f"{admin.username}: 0 alertas segun sus preferencias")
            results["skipped"] += 1
            continue

        logger.info("[EMAIL BATCH] %s: %d alertas coinciden, preparando resumen...",
                   admin.username, len(admin_alerts))

        # Build and send summary email
        subject = _build_summary_subject(admin_alerts)
        body    = _build_summary_body(admin_alerts, admin.username)

        ok, msg = _smtp_send(admin.email, subject, body)
        if ok:
            results["sent"] += 1
            results["details"].append(f"{admin.username} ({admin.email}): {len(admin_alerts)} alertas enviadas")
            for a in admin_alerts:
                notified_ids.add(a.id)
        else:
            results["errors"] += 1
            results["details"].append(f"{admin.username}: ERROR - {msg}")

    # Step 4: Mark all notified alerts
    if notified_ids:
        now = datetime.now(timezone.utc)
        for alert in pending:
            if alert.id in notified_ids:
                alert.email_notified_at = now
        db.session.commit()
        results["alerts_notified"] = len(notified_ids)
        logger.info("[EMAIL BATCH] %d alertas marcadas como notificadas.", len(notified_ids))

    # Step 5: Audit log
    log_action(
        action="email_summary_sent",
        actor=actor,
        detail=(f"Resumen de alertas enviado: {results['sent']} emails, "
                f"{results['alerts_notified']} alertas notificadas, "
                f"{results['errors']} errores."),
        level="info",
    )

    return results


# ── Internal helpers ──────────────────────────────────────────────────────────

def _build_summary_subject(alerts: list) -> str:
    """Build a descriptive subject line grouping by severity."""
    by_level = {}
    for a in alerts:
        by_level.setdefault(a.level, 0)
        by_level[a.level] += 1

    parts = []
    for lvl in ("critical", "danger", "warning", "info"):
        n = by_level.get(lvl, 0)
        if n > 0:
            label = _LEVEL_LABELS.get(lvl, lvl)
            parts.append(f"{n} {label.lower()}")

    detail = " y ".join(parts) if len(parts) <= 2 else ", ".join(parts[:-1]) + f" y {parts[-1]}"
    return f"[Overleaf Admin] Resumen de alertas: {detail}"


def _build_summary_body(alerts: list, admin_name: str) -> str:
    """Build the plain-text body for a batch summary email."""
    total = len(alerts)

    # Count by level
    by_level = {}
    for a in alerts:
        by_level.setdefault(a.level, 0)
        by_level[a.level] += 1

    lines = [
        f"Hola {admin_name},",
        "",
        f"Tienes {total} alerta(s) nueva(s) en Overleaf Admin:",
        "",
        "--- Resumen por nivel ---",
    ]
    for lvl in ("critical", "danger", "warning", "info"):
        n = by_level.get(lvl, 0)
        if n > 0:
            label = _LEVEL_LABELS.get(lvl, lvl)
            lines.append(f"  {label}: {n}")

    lines.append("")
    lines.append("--- Detalle de alertas ---")
    lines.append("")

    for i, a in enumerate(alerts, 1):
        level_lbl = _LEVEL_LABELS.get(a.level, a.level)
        type_lbl  = _TYPE_LABELS.get(a.type, a.type)
        created   = a.created_at.strftime("%d/%m/%Y %H:%M") if a.created_at else "—"
        entity    = f"{a.entity_type} {a.entity_id or ''}".strip() if a.entity_type else "—"

        lines.append(f"  {i}. [{level_lbl.upper()}] {a.title}")
        lines.append(f"     Tipo:    {type_lbl}")
        lines.append(f"     Mensaje: {a.message}")
        lines.append(f"     Entidad: {entity}")
        lines.append(f"     Fecha:   {created}")
        lines.append("")

    lines.append("---")
    lines.append(f"Accede a la plataforma: {_APP_BASE_URL}/alertas/")
    lines.append("")
    lines.append("Este es un resumen automatico generado por Overleaf Admin.")
    lines.append("Puedes cambiar tus preferencias de notificacion desde la pantalla de alertas.")

    return "\n".join(lines)


def _smtp_send(to_email: str, subject: str, body: str) -> tuple[bool, str]:
    """
    Send a single email via SMTP or mock (log to console).
    Returns (success, message).
    """
    cfg = _get_smtp_config()

    if cfg["mock"]:
        logger.info(
            "[MOCK EMAIL] To: %s\n  Subject: %s\n  Body (%d chars):\n%s",
            to_email, subject, len(body),
            "\n".join("    | " + line for line in body.split("\n")[:20])
        )
        return True, f"[MOCK] Email simulado a {to_email}"

    # Real SMTP sending
    if not cfg["host"]:
        msg = "SMTP_HOST no configurado. No se puede enviar email."
        logger.error("[EMAIL] %s", msg)
        return False, msg

    if not cfg["user"]:
        logger.warning("[EMAIL] SMTP_USER vacio. La autenticacion puede fallar.")
    if not cfg["password"]:
        logger.warning("[EMAIL] SMTP_PASSWORD vacio. La autenticacion puede fallar.")

    try:
        logger.info("[EMAIL] Conectando a %s:%d (TLS=%s)...", cfg["host"], cfg["port"], cfg["tls"])

        msg = MIMEMultipart()
        msg["From"]    = cfg["from"]
        msg["To"]      = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as srv:
            srv.ehlo()
            if cfg["tls"]:
                srv.starttls()
                srv.ehlo()
            if cfg["user"]:
                logger.info("[EMAIL] Autenticando como %s...", cfg["user"])
                srv.login(cfg["user"], cfg["password"])
            srv.send_message(msg)

        logger.info("[EMAIL] Email enviado correctamente a %s", to_email)
        return True, f"Email enviado a {to_email}"

    except smtplib.SMTPAuthenticationError as exc:
        msg = f"Error de autenticacion SMTP: {exc}. Comprueba SMTP_USER y SMTP_PASSWORD."
        logger.error("[EMAIL] %s", msg)
        return False, msg
    except smtplib.SMTPConnectError as exc:
        msg = f"No se pudo conectar a {cfg['host']}:{cfg['port']}: {exc}"
        logger.error("[EMAIL] %s", msg)
        return False, msg
    except smtplib.SMTPException as exc:
        msg = f"Error SMTP: {exc}"
        logger.error("[EMAIL] %s", msg)
        return False, msg
    except Exception as exc:
        msg = f"Error inesperado al enviar email: {type(exc).__name__}: {exc}"
        logger.error("[EMAIL] %s", msg)
        return False, msg
