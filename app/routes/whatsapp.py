from fastapi import APIRouter, Request, Header
from app.services.facturacion_service import (
    consultar_facturas,
    descargar_documento
)
from app.services.ia_service import (
    clasificar_mensaje,
    generar_instruccion_facturacion,
    generar_respuesta_final,
    preguntar_a_openai
)
from datetime import date

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
        print(f"Texto recibido de {x_from}: {texto_usuario}")

        # 1️⃣ Clasificación inicial
        tipo = await clasificar_mensaje(texto_usuario)
        print(f"🔍 Clasificación IA: {tipo}")

        if "facturacion" or "facturación" in tipo.lower():
            # 2️⃣ Generar instrucción para facturación
            instruccion = await generar_instruccion_facturacion(texto_usuario)
            print(f"🛠 Instrucción API Facturación: {instruccion}")

            if instruccion and "funcion" in instruccion and "params" in instruccion:
                funcion = instruccion["funcion"]
                parametros = instruccion["params"]

                # 3️⃣ Ejecutar la función del servicio de facturación
                if funcion == "consultar_facturas":
                    resultado = consultar_facturas(parametros)
                    print(f"Resultado de la funcion consultar_facturas: {resultado}")
                elif funcion == "descargar_documento":
                    resultado = descargar_documento(**parametros)
                    print(f"Resultado de la funcion descargar_documento: {resultado}")
                    return {"status": "ok", "respuesta": resultado}
                else:
                    resultado = "Función de facturación no reconocida."

                # 4️⃣ Generar respuesta final
                respuesta = await generar_respuesta_final(texto_usuario, resultado)
            else:
                respuesta = "No pude interpretar la solicitud de facturación."

        else:
            # Mensaje normal de chat
            respuesta = await preguntar_a_openai(f"Responde al usuario: {texto_usuario}")

        print(f"💬 Respuesta al cliente: {respuesta}")
        return {"status": "ok", "respuesta": respuesta}

    else:
        # Procesar archivos binarios (igual que antes)
        file_bytes = await request.body()
        filename = x_filename or "archivo_desconocido"
        print(f"Archivo recibido de {x_from}: {filename} ({len(file_bytes)} bytes)")
        return {"status": f"archivo {filename} recibido"}
