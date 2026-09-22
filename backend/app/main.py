import asyncio
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from backend.app.agent.scheduler import RunScheduler
from backend.app.api import router
from backend.app.clocks import DataClock
from backend.app.config import Settings
from backend.app.contracts import ScenarioAck
from backend.app.db import Database
from backend.app.errors import DomainError
from backend.app.mqtt.client import MQTTConnection
from backend.app.simulator_control import ScenarioControl
from backend.app.telemetry.ingest import TelemetryStore


def create_app(
    settings: Settings | None = None, *, clock: DataClock | None = None, run_executor=None
) -> FastAPI:
    settings = settings or Settings()
    clock = clock or DataClock()
    db = Database(settings)
    mqtt = MQTTConnection(settings, clock)
    store = TelemetryStore(db, settings, clock)
    control = ScenarioControl(db, settings, clock, mqtt)
    scheduler = RunScheduler(db, clock, run_executor) if run_executor is not None else None

    async def consume():
        while True:
            topic, payload, received_at, retained = await mqtt.queue.get()
            try:
                if topic.endswith("/telemetry"):
                    await store.receive(payload, topic, received_at, retained)
                elif topic.endswith("/scenario/ack") and not retained and len(payload) <= 8192:
                    try:
                        ack = ScenarioAck.model_validate_json(payload)
                    except ValidationError:
                        await store.diagnostic(
                            "rejected_ack", None, "Malformed acknowledgement", received_at
                        )
                    else:
                        await control.ack(ack, topic)
            except SQLAlchemyError:
                logging.getLogger(__name__).exception("TELEMETRY_DATABASE_ERROR topic=%s", topic)
            finally:
                mqtt.queue.task_done()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            await db.initialize(clock)
            app.state.consumer = asyncio.create_task(consume(), name="mqtt-consumer")
            if settings.mqtt_enabled:
                await mqtt.start()
            yield
        finally:
            if scheduler:
                await scheduler.close()
            if settings.mqtt_enabled:
                await mqtt.close()
            if hasattr(app.state, "consumer"):
                try:
                    await asyncio.wait_for(
                        mqtt.queue.join(), settings.agent_cleanup_timeout_seconds
                    )
                except TimeoutError:
                    logging.getLogger(__name__).error("MQTT_DRAIN_TIMEOUT")
                app.state.consumer.cancel()
                await asyncio.gather(app.state.consumer, return_exceptions=True)
            await control.close()
            await db.close()

    app = FastAPI(title="Charge Operations Agent", lifespan=lifespan)
    app.state.settings, app.state.clock = settings, clock
    app.state.db, app.state.mqtt = db, mqtt
    app.state.store = store
    app.state.control = control
    app.state.scheduler = scheduler
    app.include_router(router)

    @app.middleware("http")
    async def request_identity(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError):
        return JSONResponse(
            status_code=exc.status,
            content={
                "error": {"code": exc.code, "message": exc.message},
                "request_id": request.state.request_id,
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def db_error(request: Request, exc: SQLAlchemyError):
        logging.getLogger(__name__).error(
            "DATABASE_ERROR request_id=%s type=%s", request.state.request_id, type(exc).__name__
        )
        return JSONResponse(
            status_code=503,
            content={
                "error": {"code": "DATABASE_UNAVAILABLE", "message": "数据库暂不可用"},
                "request_id": request.state.request_id,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {"code": "INVALID_ARGUMENTS", "message": "请求参数不符合接口合同"},
                "request_id": request.state.request_id,
            },
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {"code": "HTTP_ERROR", "message": str(exc.detail)},
                "request_id": request.state.request_id,
            },
        )

    @app.get("/api/health")
    async def health(request: Request):
        try:
            async with db.sessions() as session:
                await session.execute(text("SELECT 1"))
            db_status = "ready"
        except SQLAlchemyError:
            db_status = "unavailable"
        mqtt_status = (
            ("ready" if mqtt.connected else "unavailable") if settings.mqtt_enabled else "disabled"
        )
        ready = db_status == "ready" and mqtt_status in {"ready", "disabled"}
        return JSONResponse(
            status_code=200 if ready else 503,
            content={
                "data": {"db": db_status, "mqtt": mqtt_status, "llm_mode": settings.llm_mode},
                "request_id": request.state.request_id,
            },
        )

    return app
