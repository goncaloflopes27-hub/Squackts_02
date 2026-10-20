from __future__ import annotations


class DomainError(ValueError):
    """An expected operational failure that can be shown to the user."""


class ValidationError(DomainError):
    pass


class OperationNotAllowed(DomainError):
    pass


class InsufficientStock(DomainError):
    pass


class NotFoundError(DomainError):
    pass


class ConflictError(DomainError):
    pass
