from app.core.config import Settings
from app.schemas.system import SystemVersionData


def get_system_version(settings: Settings) -> SystemVersionData:
    return SystemVersionData(
        application=settings.app_name,
        backend_version=settings.app_version,
        environment=settings.environment,
        build=settings.build_id,
    )
