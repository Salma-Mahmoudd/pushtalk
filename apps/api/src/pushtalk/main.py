from fastapi import FastAPI

from pushtalk import health


def create_app() -> FastAPI:
    application = FastAPI(
        title="PushTalk API", docs_url="/api/docs", openapi_url="/api/openapi.json"
    )
    application.include_router(health.router)
    return application


app = create_app()
