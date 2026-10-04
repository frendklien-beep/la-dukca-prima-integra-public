from fastapi import Depends, Request

from app.api.dependencies.auth import AuthContext, get_current_admin_context
from app.core.csrf import validate_csrf
from app.core.exceptions import CsrfInvalidError
from app.core.origin import validate_origin


def require_admin_mutation_context(
    request: Request,
    context: AuthContext = Depends(get_current_admin_context),
) -> AuthContext:
    """Validate admin session first, then exact Origin, then CSRF."""

    validate_origin(request, request.app.state.settings)
    if not validate_csrf(
        request.headers.get("x-csrf-token"),
        context.session.csrf_token_hash,
    ):
        raise CsrfInvalidError()
    return context
