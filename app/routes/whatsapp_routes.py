from fastapi import APIRouter, Request, Header
from app.services.whatsapp_service import (recibir_mensaje_texto, recibir_archivo)
import json

router = APIRouter()

@router.post("/webhook/orquestador")
async def webhook_orquestador(
    request: Request,
    x_from: str = Header(...),
    x_filename: str | None = Header(None),
    content_type: str | None = Header(None)
):
    """
    Webhook que recibe mensajes de WhatsApp y los encola en Redis para que
    el worker los procese en orden (FIFO).
    """
    if content_type and content_type.startswith("text/plain"):
        texto_usuario = (await request.body()).decode('utf-8')
        await recibir_mensaje_texto(x_from, texto_usuario)
    else:
        file_bytes = await request.body()
        filename = x_filename or "archivo_desconocido"
        await recibir_archivo(x_from, filename, file_bytes)

    # Respondemos rápido al proveedor de WhatsApp (no bloqueamos la request)
    return {"status": "accepted", "message": "Mensaje encolado"}
