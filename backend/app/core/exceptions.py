from app.schemas.error import ErrorDetail


class AppError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        details: list[ErrorDetail] | None = None,
        retryable: bool = False,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or []
        self.retryable = retryable
        self.headers = headers or {}


class StorageUnavailableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="STORAGE_UNAVAILABLE",
            message="Sistem belum siap digunakan.",
            status_code=503,
            retryable=True,
        )


class DatabaseUnavailableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="DATABASE_UNAVAILABLE",
            message="Sistem belum siap digunakan.",
            status_code=503,
            retryable=True,
        )


class MigrationRequiredError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="MIGRATION_REQUIRED",
            message="Sistem belum siap digunakan.",
            status_code=503,
            retryable=True,
        )


class InvalidCredentialsError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="AUTH_INVALID_CREDENTIALS",
            message="Username atau password tidak benar.",
            status_code=401,
        )


class AuthRequiredError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="AUTH_REQUIRED",
            message="Silakan login untuk melanjutkan.",
            status_code=401,
        )


class SessionExpiredError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="AUTH_SESSION_EXPIRED",
            message="Sesi telah berakhir. Silakan login kembali.",
            status_code=401,
        )


class CsrfInvalidError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="AUTH_CSRF_INVALID",
            message=("Permintaan keamanan tidak valid. Muat ulang halaman lalu coba kembali."),
            status_code=403,
        )


class OriginForbiddenError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="AUTH_ORIGIN_FORBIDDEN",
            message="Asal permintaan tidak diizinkan.",
            status_code=403,
        )


class RateLimitedError(AppError):
    def __init__(self, retry_after: int) -> None:
        super().__init__(
            code="RATE_LIMITED",
            message="Terlalu banyak percobaan. Silakan tunggu lalu coba kembali.",
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )


class SettingsNotInitializedError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="SETTINGS_NOT_INITIALIZED",
            message="Pengaturan aplikasi belum siap.",
            status_code=503,
            retryable=True,
        )


class SettingsInvalidError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="SETTINGS_INVALID",
            message="Pengaturan aplikasi tidak valid.",
            status_code=503,
            retryable=True,
        )


class DocumentError(AppError):
    pass


def document_error(
    code: str,
    message: str,
    status_code: int,
    *,
    retryable: bool = False,
) -> DocumentError:
    return DocumentError(
        code=code,
        message=message,
        status_code=status_code,
        retryable=retryable,
    )


class ChatSessionBusyError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="CHAT_SESSION_BUSY",
            message="Sesi sedang memproses pesan lain. Silakan coba kembali.",
            status_code=409,
            retryable=True,
        )


class ChatRateLimitedError(AppError):
    def __init__(self, retry_after: int) -> None:
        super().__init__(
            code="CHAT_RATE_LIMITED",
            message="Terlalu banyak pesan. Silakan tunggu lalu coba kembali.",
            status_code=429,
            retryable=True,
            headers={"Retry-After": str(retry_after)},
        )


class KnowledgeUnavailableAppError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="KNOWLEDGE_UNAVAILABLE",
            message="Knowledge Base sedang tidak tersedia. Silakan coba kembali.",
            status_code=503,
            retryable=True,
        )


class AiServiceUnavailableAppError(AppError):
    def __init__(self, code: str = "AI_SERVICE_UNAVAILABLE") -> None:
        super().__init__(
            code=code,
            message="Layanan AI sedang tidak tersedia. Silakan coba kembali.",
            status_code=503,
            retryable=True,
        )
