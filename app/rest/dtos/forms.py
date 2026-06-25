"""forms.py — DTOs de validación de formularios (WTForms sin CSRF propio).

La protección CSRF está gestionada globalmente por CSRFProtect en la app factory,
así que estos Form objects solo añaden validación de tipos y restricciones de valor.

Uso típico en controllers:
    form = SetQuotaForm(request.form)
    if not form.validate():
        flash("Datos inválidos.", "danger")
        return redirect(...)
    max_bytes = form.to_bytes()
"""
from wtforms import Form, StringField, IntegerField, SelectField, PasswordField, BooleanField
from wtforms.validators import DataRequired, Optional, Length, AnyOf, ValidationError


# ── Shared constants ──────────────────────────────────────────────────────────

_STORAGE_UNITS = [("B", "B"), ("KB", "KB"), ("MB", "MB"), ("GB", "GB")]
_ROLE_ACTIONS  = [("assign", "assign"), ("remove", "remove")]
_MULTIPLIERS   = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3}

# Claves de preferencia de notificación expuestas en /mi-cuenta/.
# Son las mismas que muestra el modal de /alertas/, EXCEPTO `notify_service_down`
# (eliminado a petición del usuario).
_NOTIF_LEVEL_FIELDS = (
    "notify_critical",
    "notify_danger",
    "notify_warning",
    "notify_info",
)
_NOTIF_TYPE_FIELDS = (
    "notify_sync_failed",
    "notify_quota_exceeded",
    "notify_quota_warning",
    "notify_project_limit_exceeded",
    "notify_project_limit_warning",
    "notify_repeated_errors",
    "notify_administrative_warning",
)
_NOTIF_ALL_FIELDS = _NOTIF_LEVEL_FIELDS + _NOTIF_TYPE_FIELDS
_NOTIF_MODE_VALUES = ("off", "immediate", "digest")
_DIGEST_FREQUENCY_VALUES = (
    "disabled", "12h", "daily", "3days", "5days", "weekly", "2weeks", "monthly"
)


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginForm(Form):
    """Login form — accepts username or email + password.

    El campo se sigue llamando `username` por compatibilidad con el HTML y
    los tests existentes, pero el valor puede ser un username o un email.
    """
    username = StringField("Usuario o email", validators=[DataRequired(), Length(max=255)])
    password = PasswordField("Contraseña",    validators=[DataRequired()])


# ── Users ─────────────────────────────────────────────────────────────────────

class SetQuotaForm(Form):
    """Formulario para establecer la cuota de almacenamiento de un usuario.

    quota_value vacío o "0" → sin límite (None).
    """
    quota_value = StringField("Cuota",   validators=[Optional()])
    quota_unit  = SelectField(
        "Unidad",
        choices=_STORAGE_UNITS,
        default="MB",
        validators=[AnyOf([u for u, _ in _STORAGE_UNITS])],
    )

    def validate_quota_value(self, field):
        raw = (field.data or "").strip()
        if not raw:
            return
        try:
            v = float(raw)
            if v < 0:
                raise ValidationError("El valor de cuota no puede ser negativo.")
        except (ValueError, TypeError):
            raise ValidationError("El valor de cuota debe ser un número.")

    def to_bytes(self) -> int | None:
        """Convierte valor+unidad validados a bytes. Devuelve None si es ilimitado."""
        raw = (self.quota_value.data or "").strip()
        if not raw or raw == "0":
            return None
        try:
            v = float(raw)
            if v < 0:
                return None
        except (ValueError, TypeError):
            return None
        return int(v * _MULTIPLIERS.get(self.quota_unit.data, _MULTIPLIERS["MB"]))


# ── Roles ─────────────────────────────────────────────────────────────────────

class UpdateRoleForm(Form):
    """Formulario para actualizar descripción, cuota, límite de proyectos
    y "rol por defecto" de un rol."""
    description  = StringField("Descripción",     validators=[Optional(), Length(max=500)])
    quota_value  = StringField("Cuota",           validators=[Optional()])
    quota_unit   = SelectField(
        "Unidad",
        choices=_STORAGE_UNITS,
        default="MB",
        validators=[AnyOf([u for u, _ in _STORAGE_UNITS])],
    )
    max_projects = StringField("Máx. proyectos", validators=[Optional()])
    is_default   = BooleanField("Rol por defecto", validators=[Optional()])

    def validate_quota_value(self, field):
        raw = (field.data or "").strip()
        if not raw:
            return
        try:
            v = float(raw)
            if v < 0:
                raise ValidationError("El valor de cuota no puede ser negativo.")
        except (ValueError, TypeError):
            raise ValidationError("El valor de cuota debe ser un número.")

    def validate_max_projects(self, field):
        raw = (field.data or "").strip()
        if not raw:
            return
        try:
            int(raw)
        except (ValueError, TypeError):
            raise ValidationError("El número máximo de proyectos debe ser un entero.")

    def to_quota_bytes(self) -> int | None:
        raw = (self.quota_value.data or "").strip()
        if not raw:
            return None
        try:
            v = float(raw)
            return None if v <= 0 else int(v * _MULTIPLIERS.get(self.quota_unit.data, _MULTIPLIERS["MB"]))
        except (ValueError, TypeError):
            return None

    def to_max_projects(self) -> int | None:
        raw = (self.max_projects.data or "").strip()
        try:
            v = int(raw)
            return v if v > 0 else None
        except (ValueError, TypeError):
            return None


class CreateRoleForm(Form):
    """Formulario para crear un nuevo rol desde la pantalla de gestión.

    `quota_unlimited` y `projects_unlimited` desactivan los inputs numéricos
    y hacen que `to_quota_bytes()` / `to_max_projects()` devuelvan None.
    """
    name        = StringField("Nombre",      validators=[DataRequired(), Length(min=2, max=64)])
    description = StringField("Descripción", validators=[Optional(),     Length(max=500)])
    color       = SelectField(
        "Color",
        choices=[
            ("primary",   "Azul"),
            ("info",      "Cian"),
            ("success",   "Verde"),
            ("warning",   "Amarillo"),
            ("danger",    "Rojo"),
            ("secondary", "Gris"),
            ("dark",      "Oscuro"),
        ],
        default="secondary",
        validators=[AnyOf(["primary", "info", "success", "warning", "danger", "secondary", "dark"])],
    )

    quota_unlimited = BooleanField("Cuota ilimitada", validators=[Optional()])
    # OJO: nada de Optional() aquí — WTForms cortocircuitaría validate_quota_value
    # cuando el campo está vacío, y necesitamos ejecutarlo siempre para chequear
    # contra quota_unlimited.
    quota_value     = StringField("Cuota")
    quota_unit      = SelectField(
        "Unidad", choices=_STORAGE_UNITS, default="MB",
        validators=[AnyOf([u for u, _ in _STORAGE_UNITS])],
    )

    projects_unlimited = BooleanField("Proyectos ilimitados", validators=[Optional()])
    # Idem: sin Optional() para que validate_max_projects siempre corra.
    max_projects       = StringField("Máx. proyectos")

    is_default = BooleanField("Rol por defecto", validators=[Optional()])

    def validate_quota_value(self, field):
        if self.quota_unlimited.data:
            return  # se ignora
        raw = (field.data or "").strip()
        if not raw:
            raise ValidationError("Introduce la cuota o marca 'Ilimitada'.")
        try:
            v = float(raw)
            if v <= 0:
                raise ValidationError("La cuota debe ser mayor que 0.")
        except (ValueError, TypeError):
            raise ValidationError("La cuota debe ser un número.")

    def validate_max_projects(self, field):
        if self.projects_unlimited.data:
            return
        raw = (field.data or "").strip()
        if not raw:
            raise ValidationError("Introduce el límite de proyectos o marca 'Ilimitados'.")
        try:
            v = int(raw)
            if v < 1:
                raise ValidationError("El límite debe ser >= 1.")
        except (ValueError, TypeError):
            raise ValidationError("El límite debe ser un entero.")

    def to_quota_bytes(self) -> int | None:
        if self.quota_unlimited.data:
            return None
        try:
            v = float((self.quota_value.data or "").strip())
            return int(v * _MULTIPLIERS.get(self.quota_unit.data, _MULTIPLIERS["MB"]))
        except (ValueError, TypeError):
            return None

    def to_max_projects(self) -> int | None:
        if self.projects_unlimited.data:
            return None
        try:
            v = int((self.max_projects.data or "").strip())
            return v if v >= 1 else None
        except (ValueError, TypeError):
            return None


class ManageUserRoleForm(Form):
    """Formulario para asignar o quitar el rol de un usuario desde la vista de detalle de rol."""
    user_id = IntegerField("Usuario", validators=[DataRequired()])
    action  = SelectField(
        "Acción",
        choices=_ROLE_ACTIONS,
        default="assign",
        validators=[AnyOf([a for a, _ in _ROLE_ACTIONS])],
    )


class AssignRoleForm(Form):
    """Formulario para asignar/cambiar/quitar el rol desde la vista de detalle de usuario."""
    role_id = IntegerField("Rol",    validators=[Optional()])
    reason  = StringField("Motivo", validators=[Optional(), Length(max=500)])
    action  = SelectField(
        "Acción",
        choices=_ROLE_ACTIONS,
        default="assign",
        validators=[AnyOf([a for a, _ in _ROLE_ACTIONS])],
    )


# ── Account ───────────────────────────────────────────────────────────────────

class ChangePasswordForm(Form):
    """Formulario para que el admin actual cambie su propia contraseña.

    La validación de coincidencia con la password actual se hace en el servicio
    (necesita el modelo); aquí sólo validamos campos obligatorios + longitud +
    coincidencia entre new_password y confirm_password.
    """
    current_password = PasswordField("Contraseña actual",   validators=[DataRequired()])
    new_password     = PasswordField("Nueva contraseña",    validators=[DataRequired(), Length(min=8, max=255)])
    confirm_password = PasswordField("Repetir contraseña",  validators=[DataRequired()])

    def validate_confirm_password(self, field):
        if field.data != (self.new_password.data or ""):
            raise ValidationError("Las contraseñas nuevas no coinciden.")


_DIGEST_HOUR_VALUES = tuple(range(24))


class NotifPrefsForm(Form):
    """Formulario inline de "Mi cuenta" — dos pestañas independientes.

    Pestaña "Inmediato": checkboxes con name="immediate_notify_X".
    Pestaña "Periódico": checkboxes con name="digest_notify_X" +
                         digest_frequency + digest_hour.

    Procesamos request.form directamente en to_dict() porque WTForms con
    checkboxes dinámicos es más engorroso que útil aquí.
    """
    digest_frequency = SelectField(
        "Frecuencia del resumen",
        choices=[(v, v) for v in _DIGEST_FREQUENCY_VALUES],
        default="disabled",
        validators=[AnyOf(_DIGEST_FREQUENCY_VALUES)],
    )
    digest_hour = SelectField(
        "Hora del resumen",
        choices=[(str(h), f"{h:02d}:00") for h in range(24)],
        default="8",
        validators=[Optional()],
    )

    def __init__(self, formdata=None, **kwargs):
        super().__init__(formdata=formdata, **kwargs)
        self._raw = formdata

    def to_dict(self) -> dict:
        """Construye el dict que espera update_from_dict() del modelo."""
        immediate: dict[str, bool] = {}
        digest:    dict[str, bool] = {}
        for fname in _NOTIF_ALL_FIELDS:
            immediate[fname] = bool((self._raw or {}).get(f"immediate_{fname}"))
            digest[fname]    = bool((self._raw or {}).get(f"digest_{fname}"))

        raw_hour = (self._raw or {}).get("digest_hour", "")
        try:
            digest_hour: int | None = int(raw_hour) if str(raw_hour).strip().isdigit() else None
        except (TypeError, ValueError):
            digest_hour = None

        return {
            "immediate":        immediate,
            "digest":           digest,
            "digest_frequency": self.digest_frequency.data or "disabled",
            "digest_hour":      digest_hour,
        }


# ── Admins (módulo /administradores/) ─────────────────────────────────────────

class CreateAdminForm(Form):
    """Formulario para dar de alta un administrador de la plataforma."""
    username         = StringField("Usuario", validators=[DataRequired(), Length(min=2, max=64)])
    email            = StringField("Email",   validators=[DataRequired(), Length(max=255)])
    password         = PasswordField("Contraseña",          validators=[DataRequired(), Length(min=8, max=255)])
    confirm_password = PasswordField("Repetir contraseña",  validators=[DataRequired()])
    is_active        = BooleanField("Activo", validators=[Optional()])

    def validate_email(self, field):
        v = (field.data or "").strip()
        if "@" not in v or "." not in v:
            raise ValidationError("Email con formato no válido.")

    def validate_confirm_password(self, field):
        if field.data != (self.password.data or ""):
            raise ValidationError("Las contraseñas no coinciden.")


class ResetAdminPasswordForm(Form):
    """Reset de contraseña de OTRO admin desde /administradores/."""
    new_password     = PasswordField("Nueva contraseña",   validators=[DataRequired(), Length(min=8, max=255)])
    confirm_password = PasswordField("Repetir contraseña", validators=[DataRequired()])

    def validate_confirm_password(self, field):
        if field.data != (self.new_password.data or ""):
            raise ValidationError("Las contraseñas no coinciden.")
