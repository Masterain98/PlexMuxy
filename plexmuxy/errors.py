class PlexMuxyError(Exception):
    """Base exception for stable, user-facing PlexMuxy failures."""

    code = "PLEXMUXY_ERROR"

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code or self.code


class ConfigError(PlexMuxyError, ValueError):
    code = "CONFIG_ERROR"


class ScanError(PlexMuxyError):
    code = "SCAN_ERROR"


class MatchError(PlexMuxyError):
    code = "MATCH_ERROR"


class PlanError(PlexMuxyError):
    code = "PLAN_ERROR"


class StalePlanError(PlanError):
    code = "PLAN_STALE"


class MuxError(PlexMuxyError):
    code = "MUX_EXECUTION_FAILED"


class VerificationError(PlexMuxyError):
    code = "OUTPUT_VERIFICATION_FAILED"


class CleanupError(PlexMuxyError):
    code = "CLEANUP_ERROR"
