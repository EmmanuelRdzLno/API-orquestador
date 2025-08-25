import redis
import json
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://10.210.190.252:6379/0")
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

def agregar_mensaje_historial(user_id: str, rol: str, contenido: str):
    """
    Guarda un mensaje en el historial de un usuario.
    Expira automáticamente después de 10 minutos sin actividad.
    """
    key = f"historial:{user_id}"
    historial = obtener_historial(user_id)
    historial.append({"role": rol, "content": contenido})

    redis_client.set(key, json.dumps(historial), ex=600)  # 10 minutos TTL

def obtener_historial(user_id: str):
    """
    Obtiene el historial de conversación de un usuario.
    """
    key = f"historial:{user_id}"
    data = redis_client.get(key)
    return json.loads(data) if data else []

def limpiar_historial(user_id: str):
    """
    Borra el historial de un usuario.
    """
    key = f"historial:{user_id}"
    redis_client.delete(key)

def actualizar_historial(user_id: str, historial: list):
    """
    Sobrescribe todo el historial de un usuario.
    Mantiene el mismo TTL que agregar_mensaje_historial.
    """
    key = f"historial:{user_id}"
    redis_client.set(key, json.dumps(historial), ex=600)  # 10 minutos TTL

# Conexión a Redis (puede ser local o remoto)
#redis_client = redis.StrictRedis(
#    host=os.getenv("REDIS_HOST"),
#    port=int(os.getenv("REDIS_PORT")),
#    password=os.getenv("REDIS_PASSWORD"),
#    decode_responses=True  # Para guardar texto (JSON) directamente
#)