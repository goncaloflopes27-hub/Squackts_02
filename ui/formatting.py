"""Portuguese presentation formats, without changing stored domain values."""
from __future__ import annotations

from datetime import datetime


def display_date(value: object, *, time: bool = False, empty: str = "Sem prazo") -> str:
    text = str(value or "").strip()
    if not text:
        return empty
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    return parsed.strftime("%d/%m/%Y %H:%M" if time else "%d/%m/%Y")


def display_action(action: object) -> str:
    key = str(action)
    return {"create": "Criação", "update": "Atualização", "delete": "Remoção", "archive": "Arquivo",
            "cancel": "Cancelamento", "refund": "Reembolso", "restore": "Restauro", "backup": "Cópia",
            "transition": "Mudança de estado", "payment": "Pagamento", "paid": "Pagamento",
            "adjust": "Ajuste", "artwork": "Arte", "quality": "Qualidade", "ship": "Expedição"}.get(key, key.replace("_", " ").capitalize())
