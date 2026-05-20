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
from wtforms import Form, StringField, IntegerField, SelectField, PasswordField
from wtforms.validators import DataRequired, Optional, Length, AnyOf, ValidationError


# ── Shared constants ──────────────────────────────────────────────────────────

_STORAGE_UNITS = [("B", "B"), ("KB", "KB"), ("MB", "MB"), ("GB", "GB")]
_ROLE_ACTIONS  = [("assign", "assign"), ("remove", "remove")]
_MULTIPLIERS   = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3}


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginForm(Form):
    """Login form — username + password."""
    username = StringField("Usuario",    validators=[DataRequired(), Length(max=120)])
    password = PasswordField("Contraseña", validators=[DataRequired()])


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
    """Formulario para actualizar descripción, cuota y límite de proyectos de un rol."""
    description  = StringField("Descripción",     validators=[Optional(), Length(max=500)])
    quota_value  = StringField("Cuota",           validators=[Optional()])
    quota_unit   = SelectField(
        "Unidad",
        choices=_STORAGE_UNITS,
        default="MB",
        validators=[AnyOf([u for u, _ in _STORAGE_UNITS])],
    )
    max_projects = StringField("Máx. proyectos", validators=[Optional()])

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
