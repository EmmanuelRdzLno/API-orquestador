from fastapi import APIRouter, Request, Header
from app.services.whatsapp_service import procesar_mensaje_texto, procesar_archivo

router = APIRouter()

@router.post("/webhook/orquestador")
async def webhook_orquestador(
    request: Request,
    x_from: str = Header(...),
    x_filename: str | None = Header(None),
    content_type: str | None = Header(None)
):
    if content_type and content_type.startswith("text/plain"):
        texto_usuario = (await request.body()).decode('utf-8')
        return await procesar_mensaje_texto(x_from, texto_usuario)
    else:
        file_bytes = await request.body()
        filename = x_filename or "archivo_desconocido"
        return await procesar_archivo(x_from, filename, file_bytes)
