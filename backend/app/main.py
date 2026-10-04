import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.engine import make_url

from app.api.router import register_routes
from app.core.clock import SystemClock
from app.core.config import Environment, Settings, get_settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import configure_logging
from app.db.engine import create_database_engine
from app.db.migration_state import inspect_migration_state
from app.db.session import create_session_factory
from app.middleware.request_id import register_middleware
from app.services.conversation.chat_service import ChatService
from app.services.conversation.openai_chat import (
    OpenAIResponseGenerator,
    UnavailableGenerationProvider,
)
from app.services.conversation.retrieval import (
    KnowledgeUnavailableError,
    RetrievalEngine,
)
from app.services.documents.document_dispatcher import (
    DeferredDocumentProcessingDispatcher,
    InProcessDocumentProcessingDispatcher,
)
from app.services.documents.document_service import document_service
from app.services.health_service import check_storage
from app.services.knowledge.embedding import OpenAIEmbeddingProvider
from app.services.knowledge.processor import DocumentProcessor
from app.services.settings_service import settings_service

logger = logging.getLogger(__name__)


class UnavailableQueryEmbeddingProvider:
    async def embed(self, texts):
        raise KnowledgeUnavailableError("Embedding query belum dikonfigurasi.")


def _database_exists_or_memory(settings: Settings) -> bool:
    url = make_url(settings.database_url)
    if not url.drivername.startswith("sqlite"):
        return True
    if url.database in {None, "", ":memory:"}:
        return url.database == ":memory:"
    path = Path(url.database)
    if not path.is_absolute():
        path = settings.project_dir / path
    return path.exists()


def create_lifespan(settings: Settings):
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.started_at = datetime.now(UTC)
        try:
            app.state.storage_status = check_storage(settings)
        except Exception:
            app.state.storage_status = "unavailable"
        processing_started = False
        if _database_exists_or_memory(settings):
            migration = inspect_migration_state(app.state.engine, settings.project_dir)
            if migration.status == "ready":
                with app.state.session_factory() as session:
                    settings_service.ensure_defaults(
                        session, settings=settings, request_id="startup"
                    )
                await app.state.processing_dispatcher.start()
                processing_started = True
                await app.state.processing_dispatcher.recover_pending()
        logger.info("application_start environment=%s", settings.environment.value)
        try:
            yield
        finally:
            if processing_started:
                await app.state.processing_dispatcher.stop()
            if app.state.openai_client is not None:
                await app.state.openai_client.close()
            app.state.engine.dispose()
            logger.info("application_stop environment=%s", settings.environment.value)

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    configure_logging(resolved.log_level)
    application = FastAPI(
        title="La Dukca PRIMA Integra API",
        version=resolved.app_version,
        description="Backend API resmi untuk konsultasi layanan Dukcapil.",
        lifespan=create_lifespan(resolved),
        docs_url="/docs" if resolved.docs_enabled else None,
        redoc_url="/redoc" if resolved.docs_enabled else None,
        openapi_url="/openapi.json" if resolved.docs_enabled else None,
        debug=resolved.debug,
        openapi_tags=[
            {"name": "System", "description": "Health, readiness, and safe build metadata."},
            {"name": "Public Chat", "description": "Grounded public Dukcapil consultation."},
        ],
    )
    application.state.settings = resolved
    application.state.clock = SystemClock()
    application.state.engine = create_database_engine(resolved)
    application.state.session_factory = create_session_factory(application.state.engine)
    application.state.openai_client = None
    if resolved.openai_api_key is not None and resolved.openai_api_key.get_secret_value().strip():
        try:
            from openai import AsyncOpenAI
        except ImportError:
            query_embedding_provider = UnavailableQueryEmbeddingProvider()
            generation_provider = UnavailableGenerationProvider()
        else:
            application.state.openai_client = AsyncOpenAI(
                api_key=resolved.openai_api_key.get_secret_value(),
                timeout=resolved.openai_generation_timeout_seconds,
                max_retries=0,
            )
            query_embedding_provider = OpenAIEmbeddingProvider(
                resolved, client=application.state.openai_client
            )
            generation_provider = OpenAIResponseGenerator(resolved, application.state.openai_client)
    else:
        query_embedding_provider = UnavailableQueryEmbeddingProvider()
        generation_provider = UnavailableGenerationProvider()
    application.state.chat_service = ChatService(
        settings=resolved,
        session_factory=application.state.session_factory,
        retrieval=RetrievalEngine(
            settings=resolved,
            session_factory=application.state.session_factory,
            embedding_provider=query_embedding_provider,
        ),
        generator=generation_provider,
    )
    if resolved.environment is Environment.TESTING:
        processing_dispatcher = DeferredDocumentProcessingDispatcher()
    else:
        processor = DocumentProcessor(
            settings=resolved,
            session_factory=application.state.session_factory,
        )
        processing_dispatcher = InProcessDocumentProcessingDispatcher(
            settings=resolved,
            processor=processor,
            session_factory=application.state.session_factory,
        )
    application.state.processing_dispatcher = processing_dispatcher
    document_service.dispatcher = processing_dispatcher
    register_exception_handlers(application)
    register_middleware(application)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    register_routes(application, resolved)
    return application


app = create_app()
