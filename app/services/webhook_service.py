import os
import uuid
import json
import base64
import requests

def procesar_mensaje_webhook(payload: dict):
    # Por ahora solo imprime el JSON recibido
    print("Webhook recibido:")
    print(payload)