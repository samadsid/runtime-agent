from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.application_container import ApplicationContainer
from app.api.routes import router
from app.config.settings import settings




@asynccontextmanager
async def lifespan(app: FastAPI):

    application_container = ApplicationContainer(settings=settings)
    await application_container.startup()

    app.state.application_container = application_container

    try:
        yield
    finally:
        await application_container.shutdown()


app = FastAPI(
    title="AI Commerce Agent",
    lifespan=lifespan,
)

app.include_router(router)