"""_helpers.py — funciones auxiliares compartidas entre servicios.

Centraliza utilidades duplicadas (fmt_bytes, label_user) para evitar
que cada servicio defina su propia copia.
"""


def fmt_bytes(n) -> str:
    """Formatea un número de bytes en una cadena legible (B, KB, MB, GB, TB, PB)."""
    if n is None or n == 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


def label_user(
    email: str | None,
    first: str | None,
    last: str | None,
    overleaf_id: str | None = None,
) -> str:
    """Devuelve la etiqueta más informativa disponible para un usuario."""
    if email:
        return email
    name = " ".join(p for p in (first, last) if p).strip()
    return name or overleaf_id or "—"
