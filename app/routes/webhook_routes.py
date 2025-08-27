from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.services.webhook_service import procesar_mensaje_webhook

router = APIRouter()

router = APIRouter()

@router.post("/app/webhook/orquestador")
async def app_webhook_orquestador(request: Request):
    try:
        # Leer body crudo para debug
        raw_body = await request.body()
        print(f"📥 RAW BODY: {raw_body}")

        # Intentar parsear JSON
        payload = await request.json()
        print(f"📥 JSON PARSEADO: {payload}")

    except Exception as e:
        print(f"❌ ERROR LEYENDO JSON: {e}")
        return JSONResponse(
            status_code=400,
            content={"error": f"El cuerpo enviado no es un JSON válido: {str(e)}"}
        )

    try:
        # Procesar el webhook
        procesar_mensaje_webhook(payload)
        return JSONResponse(
            status_code=200,
            content={"message": "Webhook recibido correctamente"}
        )
    except Exception as e:
        print(f"❌ ERROR EN SERVICIO: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Error procesando webhook: {str(e)}"}
        )

