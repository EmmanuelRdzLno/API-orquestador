import os
import json
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Inicializar cliente de OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def preguntar_a_openai(prompt, max_tokens=200, temperature=0.2):
    """Función genérica para consultar OpenAI"""
    try:
        fecha_actual = datetime.now().strftime("%Y-%m-%d")
        system_prompt = (
            f"Eres un asistente de WhatsApp que ofrece los siguientes servicios: \n"
            f"FACTURACIÓN y WHATSAPP (responder al usuario de forma humanizada).\n"
            f"La fecha actual es {fecha_actual}.\n"
            "Responde de forma breve y precisa."
        )
        response = client.chat.completions.create(
            model="gpt-4o",  # Rápido y barato para orquestar
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=temperature
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error en OpenAI: {e}")
        return None

async def clasificar_mensaje(texto_usuario):
    """Determina si es una consulta normal o facturación"""
    prompt = f"Solo contesta con 'WHATSAPP' o 'FACTURACION' para clasificar el siguiente mensaje del usuario: {texto_usuario}"
    return await preguntar_a_openai(prompt, max_tokens=5)

async def generar_instruccion_facturacion(texto_usuario):
    """Genera JSON con instrucciones para llamar API de facturación"""
    prompt = f"""
    De acuerdo a lo que solicita el usuario: "{texto_usuario}".
    Tienes las siguientes funciones de facturación de la API Facturama:
    - consultar_facturas: Obtienes un JSON con los datos de factura/s, puedes filtrar con 1 o los 7 parámetros del siguiente ejemplo dependiendo si los ocupas en la consulta: 
      'http://localhost:8080/api/cfdi?type=issued&folioStart=1&folioEnd=2&rfc=MIR191015553&dateStart=2025-07-31T11%3A59%3A17&dateEnd=2025-07-31T11%3A59%3A17&status=active'
    - parametros:
      type: issued/recived/payroll
      folioStart: inicio de folios
      folioEnd: final de folios
      rfc: rfc del receptor de la factura a consultar
      dateStart: fecha de inicio de la factura
      dateEnd: fecha final de la factura
      status: all/active/canceled/pending estado de la factura del CFDI 
    - descargar_documento: Obtienes el tipo de archivo (pdf o xml) con el id de la factura todos los parametros son obligatorios:
      'http://localhost:8080/api/cfdi/{{id}}/download?format=pdf&type=issued'
    - parametros:
      id: id de la factura
      format: pdf/xml tipo de formato
      type: issued/recived/payroll
    Solo contesta con formato JSON:
    - "funcion": "consultar_facturas" o "descargar_documento"
    - "params": parámetros necesarios
    """
    respuesta = await preguntar_a_openai(prompt, max_tokens=150)
    # Limpia el bloque de código ```json ... ```
    if respuesta.startswith("```json"):
        respuesta = respuesta[len("```json"):].strip()
    if respuesta.endswith("```"):
        respuesta = respuesta[:-len("```")].strip()
    try:
        return json.loads(respuesta)
    except json.JSONDecodeError:
        return None

async def generar_respuesta_final(texto_usuario, datos_factura):
    """Genera la respuesta de WhatsApp con base en los datos obtenidos"""
    prompt = f"""
    El usuario preguntó: "{texto_usuario}".
    El resultado fue: {datos_factura}.
    Redacta una respuesta corta, amable y clara para enviar por WhatsApp.
    """
    return await preguntar_a_openai(prompt, max_tokens=100)