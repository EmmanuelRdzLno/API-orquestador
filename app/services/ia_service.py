import os
import json
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def preguntar_a_openai(messages, max_tokens=200, temperature=0.2):
    """Consulta genérica a OpenAI con historial de mensajes"""
    try:
        fecha_actual = datetime.now().strftime("%Y-%m-%d")
        system_prompt = {
            "role": "system",
            "content": (
                f"Eres un asistente de WhatsApp que puede orquestar múltiples servicios:\n"
                f"- FACTURACIÓN (consultar_facturas, descargar_documento)\n"
                f"- WHATSAPP (responder al usuario de forma humanizada)\n"
                f"La fecha actual es {fecha_actual}.\n"
                "Siempre analiza el historial y decide el siguiente paso a ejecutar.\n"
                "Responde siempre breve y precisa.\n"
                "Si el siguiente paso es WHATSAPP, significa que ya tienes toda la información y puedes redactar la respuesta final."
            )
        }
        all_messages = [system_prompt] + messages
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=all_messages,
            max_tokens=max_tokens,
            temperature=temperature
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error en OpenAI: {e}")
        return None


async def clasificar_siguiente_paso(historial):
    """
    Dado el historial completo (usuario + resultados de funciones),
    indica el siguiente servicio y función a ejecutar.
    Formato esperado:
    {
      "servicio": "FACTURACION" | "GMAIL" | "WHATSAPP",
      "funcion": "consultar_facturas" | "descargar_documento" | "enviar_correo" | "respuesta_final",
      "params": { ... }
    }
    """
    prompt = """
    Analiza el historial del asistente y determina el siguiente paso.
    Servicios posibles:
    - FACTURACION:
        consultar_facturas(params): Obtienes un JSON con los datos de factura/s, puedes filtrar con 1 o los varios parámetros
            parametros:
                type: issued/recived/payroll
                folioStart: inicio de folios
                folioEnd: final de folios
                rfc: rfc del receptor de la factura a consultar
                dateStart: fecha de inicio de la factura
                dateEnd: fecha final de la factura
                status: all/active/canceled/pending estado de la factura del CFDI
        descargar_documento(params): Obtienes el tipo de archivo (pdf o xml) con el id de la factura todos los parametros son obligatorios
            parametros:
                id: id de la factura
                format: pdf/xml tipo de formato
                type: issued/recived/payroll
    - WHATSAPP:
        respuesta_final(params)

    Devuelve SOLO un JSON con:
    {
      "servicio": "...",
      "funcion": "...",
      "params": { ... }
    }

    Importante:
    - Usa FACTURACION si falta consultar o descargar facturas.
    - Usa GMAIL si hay que enviar algo por correo.
    - Usa WHATSAPP si ya tienes todo y debes responder al usuario.
    """
    messages = historial + [{"role": "user", "content": prompt}]
    respuesta = await preguntar_a_openai(messages, max_tokens=200)

    if respuesta.startswith("```json"):
        respuesta = respuesta[len("```json"):].strip()
    if respuesta.endswith("```"):
        respuesta = respuesta[:-len("```")].strip()

    try:
        return json.loads(respuesta)
    except json.JSONDecodeError:
        return None


async def generar_respuesta_final(historial):
    """Genera la respuesta de WhatsApp con base en el historial"""
    prompt = """
    Con base en el historial, redacta una respuesta corta, amable y clara
    para enviar por WhatsApp al usuario. No repitas información técnica.
    """
    messages = historial + [{"role": "user", "content": prompt}]
    return await preguntar_a_openai(messages, max_tokens=150)
