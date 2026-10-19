from __future__ import annotations

from dataclasses import dataclass

ORDERED_STATES = ("rascunho", "confirmada", "em_producao", "pronta_envio", "expedida", "concluida", "cancelada")
VALID_STATES = set(ORDERED_STATES)
INITIAL_CREATION_STATES = {"rascunho", "confirmada"}
FINAL_STATES = {"concluida", "cancelada"}
EDIT_BLOCKED_STATES = {"expedida", "concluida", "cancelada"}
COMMERCIAL_EDIT_STATES = {"rascunho", "confirmada"}
TRACKING_ALLOWED_STATES = {"pronta_envio", "expedida", "concluida"}
TRACKING_REQUIRED_STATES = {"expedida", "concluida"}
PAID_REQUIRED_STATES = {"expedida", "concluida"}
STOCK_DEDUCTION_STATES = {"confirmada", "em_producao", "pronta_envio", "expedida", "concluida"}

STATE_TRANSITIONS: dict[str, set[str]] = {
    "rascunho": {"confirmada", "cancelada"},
    "confirmada": {"em_producao", "pronta_envio", "cancelada"},
    "em_producao": {"pronta_envio", "cancelada"},
    "pronta_envio": {"expedida", "cancelada"},
    "expedida": {"concluida"},
    "concluida": set(),
    "cancelada": set(),
}


@dataclass(frozen=True, slots=True)
class OrderActions:
    """Capabilities computed by the domain for every presentation entry point."""

    state: str
    targets: tuple[str, ...]
    can_edit_commercial: bool
    can_update_tracking: bool


def ensure_state_transition(current_state: str, new_state: str, action: str) -> None:
    if current_state == new_state:
        return
    if new_state not in STATE_TRANSITIONS.get(current_state, set()):
        raise ValueError(f"Transição inválida ao {action}: {current_state} -> {new_state}")


def validate_tracking_for_state(state: str, tracking: str) -> str:
    normalized = tracking.strip()
    if normalized and state not in TRACKING_ALLOWED_STATES and state != "cancelada":
        raise ValueError("Tracking só pode ser definido a partir de pronta_envio")
    if state in TRACKING_REQUIRED_STATES and not normalized:
        raise ValueError("Tracking é obrigatório para encomendas expedidas/concluídas")
    return normalized


def ensure_tracking_update_allowed(state: str, tracking: str) -> str:
    if state not in TRACKING_ALLOWED_STATES:
        raise ValueError("Tracking só pode ser atualizado a partir de pronta_envio")
    normalized = tracking.strip()
    if not normalized:
        raise ValueError("Tracking não pode ser vazio")
    return normalized


def validate_paid_for_state(state: str, paid: int) -> None:
    if state in PAID_REQUIRED_STATES and paid != 1:
        raise ValueError(f"Estado '{state}' exige encomenda marcada como paga")
    if state == "rascunho" and paid == 1:
        raise ValueError("Rascunho não pode estar marcado como pago")


def initial_creation_states_ordered() -> list[str]:
    return [state for state in ORDERED_STATES if state in INITIAL_CREATION_STATES]
