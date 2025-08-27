import os
import json
import uuid
import redis
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

# -----------------------------
# Conexión a Redis
# -----------------------------
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

# =============================
#   HISTORIAL DE CONVERSACIÓN
# =============================

def _historial_key(user_id: str) -> str:
    return f"historial:{user_id}"

def agregar_mensaje_historial(user_id: str, rol: str, contenido: str, ttl_seconds: int = 600) -> None:
    """
    Guarda un mensaje en el historial de un usuario.
    Expira automáticamente después de 'ttl_seconds' sin actividad (default 10 min).
    """
    key = _historial_key(user_id)
    historial = obtener_historial(user_id)
    historial.append({"role": rol, "content": contenido})
    redis_client.set(key, json.dumps(historial), ex=ttl_seconds)

def obtener_historial(user_id: str) -> List[Dict[str, Any]]:
    """
    Obtiene el historial de conversación de un usuario.
    """
    key = _historial_key(user_id)
    data = redis_client.get(key)
    return json.loads(data) if data else []

def limpiar_historial(user_id: str) -> None:
    """
    Borra el historial de un usuario.
    """
    key = _historial_key(user_id)
    redis_client.delete(key)

def actualizar_historial(user_id: str, historial: list, ttl_seconds: int = 600) -> None:
    """
    Sobrescribe todo el historial de un usuario con TTL.
    """
    key = _historial_key(user_id)
    redis_client.set(key, json.dumps(historial), ex=ttl_seconds)

# =============================
#           COLAS
# =============================

def _queue_key(user_id: str) -> str:
    return f"queue:{user_id}"

def enqueue_user_message(user_id: str, message: Dict[str, Any]) -> None:
    """
    Agrega un mensaje a la cola del usuario (FIFO).
    message debe ser serializable a JSON.
    """
    key = _queue_key(user_id)
    redis_client.rpush(key, json.dumps(message))

def dequeue_user_message(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Saca el siguiente mensaje de la cola del usuario.
    """
    key = _queue_key(user_id)
    msg = redis_client.lpop(key)
    return json.loads(msg) if msg else None

def get_queue_length(user_id: str) -> int:
    key = _queue_key(user_id)
    return redis_client.llen(key)

def get_all_users_with_queue() -> List[str]:
    """
    Retorna lista de user_id que tienen una cola creada (no necesariamente con elementos).
    """
    keys = redis_client.keys("queue:*")
    return [k.split(":", 1)[1] for k in keys]

# =============================
#            LOCKS
# =============================

def _lock_key(user_id: str) -> str:
    return f"lock:{user_id}"

def acquire_user_lock(user_id: str, ttl_seconds: int = 300) -> Optional[str]:
    """
    Intenta tomar un lock exclusivo por usuario para procesar su cola.
    Devuelve un token (string aleatorio) si lo obtiene, o None si ya está bloqueado.
    """
    key = _lock_key(user_id)
    token = str(uuid.uuid4())
    # SET NX EX -> set if not exists + expire
    acquired = redis_client.set(key, token, nx=True, ex=ttl_seconds)
    return token if acquired else None

# uso interno para liberar de forma atómica
_RELEASE_LOCK_LUA = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("DEL", KEYS[1])
else
  return 0
end
"""

def release_user_lock(user_id: str, token: str) -> bool:
    """
    Libera el lock sólo si el token coincide (evita liberar locks de otros procesos).
    """
    key = _lock_key(user_id)
    result = redis_client.eval(_RELEASE_LOCK_LUA, 1, key, token)
    return result == 1

def refresh_user_lock(user_id: str, ttl_seconds: int = 300) -> None:
    """
    Extiende el TTL del lock (útil en pipelines largos).
    """
    key = _lock_key(user_id)
    # Sólo renueva si el lock existe
    if redis_client.ttl(key) > 0:
        redis_client.expire(key, ttl_seconds)
