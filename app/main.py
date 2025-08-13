from fastapi import FastAPI
from app.routes import whatsapp_routes

app = FastAPI()

app.include_router(whatsapp_routes.router)
