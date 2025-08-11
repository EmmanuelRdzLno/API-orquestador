from fastapi import FastAPI
from app.routes import whatsapp

app = FastAPI()

app.include_router(whatsapp.router)
