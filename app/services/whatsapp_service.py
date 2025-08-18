import os
import uuid
import json
import base64
import requests
from app.services.facturacion_service import (
    consultar_facturas,
    descargar_documento,
    crear_factura
)

from app.services.ia_service import (
    clasificar_siguiente_paso,
    generar_respuesta_final
)
from app.utils.redis_client import agregar_mensaje_historial, obtener_historial, actualizar_historial

TEMP_FOLDER = "archivos_temp"
os.makedirs(TEMP_FOLDER, exist_ok=True)


def marcar_archivo_usado(historial, archivo_path):
    """Elimina el archivo y lo marca como usado en el historial"""
    if os.path.exists(archivo_path):
        os.remove(archivo_path)
    for msg in historial:
        if isinstance(msg["content"], dict) and msg["content"].get("archivo") == archivo_path:
            msg["content"]["archivo"] = None
    return historial

def enviar_archivo_por_whatsapp(x_from: str, archivo_path: str, filename: str):
    # Aquí abres el archivo, lo preparas y haces la llamada al API / SDK que usas para enviar archivos
    with open(archivo_path, "rb") as f:
        file_bytes = f.read()
    # Lógica específica según tu API de WhatsApp:
    # Por ejemplo, si usas Twilio, WhatsApp Cloud API o similar, aquí iría la llamada.
    # Ejemplo pseudocódigo:
    # await whatsapp_api.send_file(to=x_from, file_bytes=file_bytes, filename=filename)
    
    print(f"Archivo {filename} enviado a {x_from} por WhatsApp")


async def procesar_mensaje_texto(x_from: str, texto_usuario: str):
    print(f"Texto recibido de {x_from}: {texto_usuario}")

    # Guardar mensaje usuario
    agregar_mensaje_historial(x_from, "user", texto_usuario)

    while True:
        historial = obtener_historial(x_from)

        # Construir messages para OpenAI, siempre como strings
        messages = []
        for msg in historial:
            content = msg["content"]
            if not isinstance(content, str):
                # Convierte dict o cualquier otro tipo a JSON string para evitar error
                content = json.dumps(content, ensure_ascii=False)
            messages.append({
                "role": "assistant" if msg["role"] == "assistant" else "user",
                "content": content
            })

        siguiente = await clasificar_siguiente_paso(messages)
        print(f"🔍 Siguiente paso IA: {siguiente}")

        if not siguiente:
            respuesta = "No pude entender tu solicitud."
            agregar_mensaje_historial(x_from, "assistant", respuesta)
            return {"status": "ok", "respuesta": respuesta}

        servicio = siguiente.get("servicio", "").upper()
        funcion = siguiente.get("funcion", "")
        params = siguiente.get("params", {})

        resultado = None
        archivo_path = None

        if servicio == "FACTURACION":
            if funcion == "consultar_facturas":
                resultado = consultar_facturas(params)

            elif funcion == "descargar_documento":
                file_bytes, file_name = descargar_documento(**params)
                unique_name = f"{uuid.uuid4()}_{file_name}"
                archivo_path = os.path.join(TEMP_FOLDER, unique_name)
                with open(archivo_path, "wb") as f:
                    f.write(file_bytes)

                resultado = {
                    "mensaje": f"Documento descargado: {file_name}",
                    "archivo": archivo_path
                }
            elif funcion == "crear_factura":
                print(f"este es el json para generar factura: {json}")
                #file_bytes, file_name = crear_factura(**json)
                #unique_name = f"{uuid.uuid4()}_{file_name}"
                #archivo_path = os.path.join(TEMP_FOLDER, unique_name)
                #with open(archivo_path, "wb") as f:
                #    f.write(file_bytes)

                #resultado = {
                #    "mensaje": f"Documento descargado: {file_name}",
                #    "archivo": archivo_path
                #} 

            else:
                resultado = "Función de facturación no reconocida."

        elif servicio == "WHATSAPP":
            respuesta = await generar_respuesta_final(messages)
            agregar_mensaje_historial(x_from, "assistant", respuesta)

            # Revisa si hay archivos pendientes en historial para enviar por WhatsApp
            for msg in reversed(historial):
                content = msg["content"]
                try:
                    # Intenta cargar JSON si es string para verificar si contiene archivo
                    contenido = json.loads(content) if isinstance(content, str) else content
                except Exception:
                    contenido = content

                if isinstance(contenido, dict) and contenido.get("archivo"):
                    archivo_path = contenido["archivo"]
                    if os.path.exists(archivo_path):
                        print(f"📂 Enviando archivo por WhatsApp: {archivo_path}")
                        with open(archivo_path, "rb") as f:
                            archivo_bytes = f.read()
                        archivo_b64 = base64.b64encode(archivo_bytes).decode()
                        format = os.path.splitext(archivo_path)[1].lower().strip('.')
                        historial = marcar_archivo_usado(historial, archivo_path)
                        actualizar_historial(x_from, historial)
                        return {
                            "status": "ok",
                            "respuesta": {
                                "ContentEncoding": "base64",
                                "ContentType": f"application/{format}",
                                "ContentLength": len(archivo_b64),
                                "Content": archivo_b64
                            }
                        }

            print(f"💬 Respuesta al cliente: {respuesta}")
            return {"status": "ok", "respuesta": respuesta}

        else:
            resultado = f"Servicio '{servicio}' no reconocido."

        # Guardar resultado, siempre como string para evitar problemas con OpenAI
        if archivo_path:
            agregar_mensaje_historial(x_from, "assistant", json.dumps({
                "mensaje": resultado["mensaje"],
                "archivo": archivo_path
            }, ensure_ascii=False))
        else:
            # Si resultado no es string, conviértelo
            if not isinstance(resultado, str):
                resultado = json.dumps(resultado, ensure_ascii=False)
            agregar_mensaje_historial(x_from, "assistant", resultado)


async def procesar_archivo(x_from: str, filename: str, file_bytes: bytes):
    print(f"Archivo recibido de {x_from}: {filename} ({len(file_bytes)} bytes)")

    # 1. Convertir a base64
    file_base64 = base64.b64encode(file_bytes).decode('utf-8')

    # 2. Definir URL del servicio Node.js
    node_service_url = "http://localhost:3030/process-file"

    try:
        # 3. Enviar POST al servicio Node.js
        response = requests.post(node_service_url, json={"base64": file_base64})
        response.raise_for_status()  # Lanza error si el status != 200

        # 4. Leer respuesta
        data = response.json()
        print("📄 Respuesta del servicio Node.js:")
        print(data)

        return data
    except requests.exceptions.RequestException as e:
        print(f"❌ Error al comunicar con el servicio Node.js: {e}")
        return {"error": str(e)}