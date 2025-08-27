import os
import requests
from dotenv import load_dotenv
import base64
from tempfile import gettempdir
import json

load_dotenv()

FACTURACION_API_URL = os.getenv("FACTURACION_API_URL")  
FACTURACION_USER = os.getenv("PRODUCTION_FACTURAMA_USER")
FACTURACION_PASSWORD = os.getenv("PRODUCTION_FACTURAMA_PASSWORD")

def crear_factura(datos_factura: dict) -> dict:
    url = f"{FACTURACION_API_URL}"
    auth = (FACTURACION_USER, FACTURACION_PASSWORD)
    headers = {"Content-Type": "application/json"}
    print("📤 Enviando a Facturama:", json.dumps(datos_factura, indent=2, ensure_ascii=False))

    resp = requests.post(url, json=datos_factura, headers=headers)
    resp.raise_for_status()
    return resp.json()

def consultar_facturas(params: dict) -> dict:
    url = f"{FACTURACION_API_URL}"
    auth = (FACTURACION_USER, FACTURACION_PASSWORD)

    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return resp.json()

def descargar_documento(id: str, format: str = "pdf", type: str = "issued") -> tuple:
    """
    Descarga el documento de facturación y devuelve (bytes del archivo, nombre del archivo).
    """
    url = f"{FACTURACION_API_URL}/{id}/download"
    auth = (FACTURACION_USER, FACTURACION_PASSWORD)
    params = {"format": format, "type": type}

    resp = requests.get(url, params=params, auth=auth)
    resp.raise_for_status()

    # Obtener nombre de archivo para guardar temporalmente
    filename = f"{id}.{format}"
    
    # Retornar bytes y nombre para guardarlo donde se decida
    return resp.content, filename

    return {
        "ContentEncoding": "base64",
        "ContentType": f"application/{format}",
        "ContentLength": len(resp.content),
        "Content": archivo_base64
    }