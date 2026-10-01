"""Application-level database and configuration errors."""


class ConfigurationError(RuntimeError):
    """Raised when an environment configuration value is invalid."""


class RepositoryError(RuntimeError):
    """Base exception for persistence failures."""


class EntityNotFoundError(RepositoryError):
    """Raised when a requested entity does not exist."""


class EntityConflictError(RepositoryError):
    """Raised when a unique or concurrency constraint is violated."""


class ApplicationValidationError(ValueError):
    """Raised when input violates a backend-independent business rule."""


class DatabaseConnectionError(RepositoryError):
    """Raised when a configured database cannot be reached."""
