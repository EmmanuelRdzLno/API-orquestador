from fastapi import FastAPI
from app.routes import whatsapp_routes, webhook_routes

app = FastAPI()

app.include_router(whatsapp_routes.router)
app.include_router(webhook_routes.router)
