import os
import uuid
import json
import base64
import asyncio
import requests
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from app.services.facturacion_service import (
    consultar_facturas,
    descargar_documento,
    crear_factura
)
from app.services.ia_service import (
    clasificar_siguiente_paso,
    generar_respuesta_final
)

from app.utils.redis_client import (
    agregar_mensaje_historial,
    obtener_historial,
    actualizar_historial,
    enqueue_user_message,
    dequeue_user_message,
    get_queue_length,
    acquire_user_lock,
    release_user_lock,
    refresh_user_lock,
)

TEMP_FOLDER = "archivos_temp"
os.makedirs(TEMP_FOLDER, exist_ok=True)

load_dotenv()

BAILEYS_API_URL = os.getenv("BAILEYS_API_URL", "http://localhost:3000/api/respuesta")
DOCUMENTS_API_URL = os.getenv("DOCUMENTS_API_URL", "https://api-documentos-577166035685.us-central1.run.app/process-file")

# ==========================================================
#            RETORNA MENSAJE PROCESADO A WHATSAPP
# ==========================================================

def enviar_respuesta_a_whatsapp(to: str, mensaje: str = None, ruta_archivo: str = None):
    """
    Envía mensajes o archivos a WhatsApp vía Baileys.
    
    :param to: ID del destinatario (ej. "5214492764608@s.whatsapp.net")
    :param mensaje: Texto a enviar
    :param ruta_archivo: Ruta local del archivo a enviar (ej. "archivos_temp/factura.pdf")
    """
    try:
        headers = {
            "X-To": to
        }

        if mensaje and not ruta_archivo:
            # Solo texto
            headers["Content-Type"] = "text/plain"
            response = requests.post(BAILEYS_API_URL, data=mensaje.encode("utf-8"), headers=headers)

        elif ruta_archivo:
            # Archivo (documento, imagen, etc.)
            mime_type = "application/octet-stream"
            ext = os.path.splitext(ruta_archivo)[1].lower()

            if ext in [".pdf"]:
                mime_type = "application/pdf"
            elif ext in [".jpg", ".jpeg"]:
                mime_type = "image/jpeg"
            elif ext in [".png"]:
                mime_type = "image/png"

            headers["Content-Type"] = mime_type
            headers["X-Filename"] = os.path.basename(ruta_archivo)

            with open(ruta_archivo, "rb") as f:
                response = requests.post(BAILEYS_API_URL, data=f.read(), headers=headers)

        else:
            raise ValueError("Debes especificar un mensaje o una ruta de archivo.")

        response.raise_for_status()
        print(f"✅ Enviado a WhatsApp ({to})")
        return True

    except Exception as e:
        print(f"❌ Error enviando a WhatsApp: {e}")
        return False

# ==========================================================
#                 UTILIDADES INTERNAS
# ==========================================================

def marcar_archivo_usado(historial, archivo_path):
    """Elimina el archivo y lo marca como usado en el historial"""
    if os.path.exists(archivo_path):
        os.remove(archivo_path)
    for msg in historial:
        if isinstance(msg["content"], dict) and msg["content"].get("archivo") == archivo_path:
            msg["content"]["archivo"] = None
    return historial

def enviar_archivo_por_whatsapp(x_from: str, archivo_path: str, filename: str):
    # Placeholder: aquí implementa el envío real con tu API/SDK de WhatsApp
    with open(archivo_path, "rb") as f:
        _ = f.read()
    print(f"Archivo {filename} enviado a {x_from} por WhatsApp")

# ==========================================================
#           WORKER SECUENCIAL POR USUARIO (COLA)
# ==========================================================

async def _procesar_evento(user_id: str, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    # 🔑 Normalizar en caso de que event venga como string
    if isinstance(event, str):
        try:
            event = json.loads(event)
        except Exception:
            print(f"[WARN] Evento corrupto en Redis para {user_id}: {event}")
            return None

    etype = event.get("type")
    if etype == "text":
        return await procesar_mensaje_texto(user_id, event.get("content", ""))
    elif etype == "file":
        file_bytes = base64.b64decode(event.get("base64", ""))
        return await procesar_archivo(user_id, event.get("filename", "archivo"), file_bytes)
    else:
        print(f"[WARN] Evento no soportado para {user_id}: {event}")
        return None

async def run_user_queue_worker(user_id: str, max_to_process: int = 20, lock_ttl: int = 300) -> None:
    """
    Toma un lock por usuario y procesa eventos de la cola en orden (FIFO).
    - max_to_process: para no alargar demasiado una ejecución (Cloud Run friendly).
    - lock_ttl: TTL del lock; se refresca durante el procesamiento.
    """
    token = acquire_user_lock(user_id, ttl_seconds=lock_ttl)
    if not token:
        # Ya hay otro worker procesando este usuario.
        print(f"🔒 Lock en uso para {user_id}, se deja en cola para el siguiente ciclo.")
        return

    print(f"✅ Lock adquirido para {user_id}. Procesando su cola...")
    processed = 0
    try:
        while processed < max_to_process:
            event = dequeue_user_message(user_id)
            if not event:
                print(f"✅ Cola vacía para {user_id}.")
                break

            # Mantener vivo el lock por si el pipeline tarda
            refresh_user_lock(user_id, ttl_seconds=lock_ttl)

            try:
                await _procesar_evento(user_id, event)
            except Exception as e:
                # Loguear y continuar con el siguiente, NO queremos frenar la cola completa por un fallo
                print(f"❌ Error procesando evento de {user_id}: {e}")

            processed += 1
            await asyncio.sleep(0)  # ceder control al loop

        remaining = get_queue_length(user_id)
        print(f"ℹ️ Procesados {processed} eventos para {user_id}. En cola: {remaining}")
    finally:
        released = release_user_lock(user_id, token)
        print(f"🔓 Lock liberado para {user_id}: {released}")

# ==========================================================
#         ENTRADAS PÚBLICAS (WEBHOOK / ROUTES)
# ==========================================================

async def recibir_mensaje_texto(x_from: str, texto_usuario: str) -> Dict[str, Any]:
    """
    Punto de entrada cuando Baileys/WhatsApp entrega un texto.
    Encola y dispara un worker breve para drenar.
    """
    enqueue_user_message(x_from, {"type": "text", "content": texto_usuario})
    queue_size = get_queue_length(x_from)
    # Dispara un worker "rápido" para drenar en este request (si es posible)
    asyncio.create_task(run_user_queue_worker(x_from))
    return {"status": "queued", "queued_items": queue_size}

async def recibir_archivo(x_from: str, filename: str, file_bytes: bytes) -> Dict[str, Any]:
    """
    Punto de entrada cuando Baileys/WhatsApp entrega un archivo.
    Encola y dispara un worker breve para drenar.
    """
    file_base64 = base64.b64encode(file_bytes).decode("utf-8")
    enqueue_user_message(x_from, {"type": "file", "filename": filename, "base64": file_base64})
    queue_size = get_queue_length(x_from)
    asyncio.create_task(run_user_queue_worker(x_from))
    return {"status": "queued", "queued_items": queue_size}

# ==========================================================
#        LÓGICA EXISTENTE (AHORA SECUENCIAL POR COLA)
# ==========================================================

async def procesar_mensaje_texto(x_from: str, texto_usuario: str):
    """
    PROCESA **UN** MENSAJE (ya encolado y tomado por el worker).
    Mantiene compatibilidad con tu pipeline actual.
    """
    print(f"Texto recibido de {x_from}: {texto_usuario}")
    agregar_mensaje_historial(x_from, "user", texto_usuario)

    # Bucle de planificación por pasos (function-calling/plan)
    while True:
        historial = obtener_historial(x_from)

        # Construir messages para OpenAI, siempre como strings
        messages = []
        for msg in historial:
            content = msg["content"]
            if not isinstance(content, str):
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
            enviar_respuesta_a_whatsapp(to=x_from, mensaje=respuesta)
            return {"status": "ok", "respuesta": respuesta}

        servicio = (siguiente.get("servicio") or "").upper()
        funcion = siguiente.get("funcion", "")
        params = siguiente.get("params", {}) or {}

        resultado = None
        archivo_path = None

        if servicio == "FACTURACION" or servicio == "FACTURACIÓN":
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
                # Asegúrate de que params sea el payload correcto para tu servicio
                # file_bytes, file_name = crear_factura(**params)
                # unique_name = f"{uuid.uuid4()}_{file_name}"
                # archivo_path = os.path.join(TEMP_FOLDER, unique_name)
                # with open(archivo_path, "wb") as f:
                #     f.write(file_bytes)
                # resultado = {
                #     "mensaje": f"Factura generada: {file_name}",
                #     "archivo": archivo_path
                # }
                resultado = crear_factura(params)

            else:
                resultado = "Función de facturación no reconocida."

        elif servicio == "WHATSAPP":
            # Generar la respuesta final con tu IA
            respuesta = await generar_respuesta_final(messages)
            agregar_mensaje_historial(x_from, "assistant", respuesta)

            # Revisar si hay archivos pendientes en historial para enviar por WhatsApp
            for msg in reversed(historial):
                content = msg["content"]
                try:
                    contenido = json.loads(content) if isinstance(content, str) else content
                except Exception:
                    contenido = content

                if isinstance(contenido, dict) and contenido.get("archivo"):
                    archivo_path = contenido["archivo"]
                    if os.path.exists(archivo_path):
                        print(f"📂 Enviando archivo por WhatsApp: {archivo_path}")

                        # Enviar archivo
                        enviar_respuesta_a_whatsapp(to=x_from, ruta_archivo=archivo_path)

                        # Marcar archivo como enviado y actualizar historial
                        historial = marcar_archivo_usado(historial, archivo_path)
                        actualizar_historial(x_from, historial)

                        # Enviar mensaje de texto que acompaña al archivo, si existe
                        mensaje_texto = siguiente.get("params", {}).get("mensaje")
                        if mensaje_texto:
                            print(f"💬 Respuesta al cliente: {mensaje_texto}")
                            enviar_respuesta_a_whatsapp(to=x_from, mensaje=mensaje_texto)

                        # Retornar confirmación
                        return {
                            "status": "ok",
                            "respuesta": f"Archivo enviado: {os.path.basename(archivo_path)}"
                        }

            # Si no hay archivos, enviar el texto final
            print(f"💬 Respuesta al cliente: {respuesta}")
            enviar_respuesta_a_whatsapp(to=x_from, mensaje=respuesta)

            return {
                "status": "ok",
                "respuesta": respuesta
            }

        else:
            resultado = f"Servicio '{servicio}' no reconocido."

        # Guardar resultado en historial (string seguro)
        if archivo_path:
            agregar_mensaje_historial(
                x_from,
                "assistant",
                json.dumps({"mensaje": resultado.get("mensaje"), "archivo": archivo_path}, ensure_ascii=False)
            )
            print(f"📑 Historial de redis: {obtener_historial(x_from)}")
        else:
            if not isinstance(resultado, str):
                resultado = json.dumps(resultado, ensure_ascii=False)
            agregar_mensaje_historial(x_from, "assistant", resultado)
            print(f"📑 Historial de redis: {obtener_historial(x_from)}")

        # Si el plan requiere varios pasos, este while continuará;
        # si ya no hay "siguiente paso", se romperá arriba y retornará.

async def procesar_archivo(x_from: str, filename: str, file_bytes: bytes):
    """
    PROCESA **UN** ARCHIVO (ya encolado y tomado por el worker).
    Envía el archivo al microservicio Node.js y devuelve su respuesta.
    """
    print(f"Archivo recibido de {x_from}: {filename} ({len(file_bytes)} bytes)")

    # 1. Convertir a base64
    file_base64 = base64.b64encode(file_bytes).decode('utf-8')

    try:
        # 3. Enviar POST al servicio Node.js
        response = requests.post(DOCUMENTS_API_URL, json={"base64": file_base64})
        response.raise_for_status()
        data = response.json()
        print("📄 Respuesta del servicio Node.js:")
        print(data)

        # Opcional: guardar en historial alguna referencia
        agregar_mensaje_historial(x_from, "api-document", json.dumps({"archivo_procesado": filename, "resultado": data}, ensure_ascii=False))
        return data
    except requests.exceptions.RequestException as e:
        print(f"❌ Error al comunicar con el servicio Node.js: {e}")
        agregar_mensaje_historial(x_from, "api-document", f"Error procesando archivo: {str(e)}")
        return {"error": str(e)}
