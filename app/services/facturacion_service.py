import os
import requests
from dotenv import load_dotenv
import base64

load_dotenv()

FACTURACION_API_URL = os.getenv("FACTURACION_API_URL")  
FACTURACION_USER = os.getenv("PRODUCTION_FACTURAMA_USER")
FACTURACION_PASSWORD = os.getenv("PRODUCTION_FACTURAMA_PASSWORD")

def crear_factura(datos_factura: dict) -> dict:
    url = f"{FACTURACION_API_URL}"
    auth = (FACTURACION_USER, FACTURACION_PASSWORD)
    headers = {"Content-Type": "application/json"}

    resp = requests.post(url, json=datos_factura, headers=headers)
    resp.raise_for_status()
    return resp.json()

def consultar_facturas(params: dict) -> dict:
    url = f"{FACTURACION_API_URL}"
    auth = (FACTURACION_USER, FACTURACION_PASSWORD)

    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return resp.json()

def descargar_documento(id: str, format: str = "pdf", type: str = "issued") -> dict:
    # format: "pdf" o "xml"
    url = f"{FACTURACION_API_URL}/{id}/download"
    auth = (FACTURACION_USER, FACTURACION_PASSWORD)
    params = {"format": format, "type": type}

    resp = requests.get(url, params=params, auth=auth)
    resp.raise_for_status()

    # La respuesta es el archivo binario, lo codificamos a base64
    archivo_base64 = base64.b64encode(resp.content).decode('utf-8')

    return {
        "ContentEncoding": "base64",
        "ContentType": f"application/{format}",
        "ContentLength": len(resp.content),
        "Content": archivo_base64
    }