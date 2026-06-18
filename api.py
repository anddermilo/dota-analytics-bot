from fastapi import FastAPI, HTTPException
import requests
import psycopg2
import os
from dotenv import load_dotenv, find_dotenv

app = FastAPI()

# --- RASTREADOR ABSOLUTO DE VARIABLES ---
archivo_env = find_dotenv() # Busca el .env automáticamente en todo el proyecto
if archivo_env:
    # override=True obliga a sobreescribir cualquier caché viejo de Uvicorn
    load_dotenv(archivo_env, override=True) 
    
    # Lector manual de emergencia por si Windows corrompe el texto
    if not os.getenv("DATABASE_URL"):
        with open(archivo_env, "r", encoding="utf-8-sig") as f:
            for linea in f:
                if "=" in linea and not linea.strip().startswith("#"):
                    clave, valor = linea.split("=", 1)
                    os.environ[clave.strip()] = valor.strip().replace('"', '').replace("'", "")

print("\n" + "="*40)
print("🔍 DIAGNÓSTICO DE INICIO DE API")
print(f"Ruta del .env encontrada: {archivo_env if archivo_env else 'NINGUNA ❌'}")
print(f"DATABASE_URL cargada: {'SÍ ✅' if os.getenv('DATABASE_URL') else 'NO ❌'}")
print("="*40 + "\n")

def obtener_conexion():
    """Conecta a Supabase usando la variable de entorno."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("❌ DATABASE_URL no configurada en el entorno.")
    
    # Agregamos sslmode si no está para evitar bloqueos de Supabase
    if "?" not in db_url:
        db_url += "?sslmode=require"
        
    conexion = psycopg2.connect(db_url)
    conexion.set_client_encoding('latin1')
    return conexion

# ... (De aquí en adelante sigue el resto de tu código api.py: CACHE_ITEMS, etc.) ...

CACHE_ITEMS = {}
CACHE_HEROES_OD = {}

def cargar_constantes():
    global CACHE_ITEMS, CACHE_HEROES_OD
    if not CACHE_ITEMS:
        try:
            r_items = requests.get("https://api.opendota.com/api/constants/items")
            if r_items.status_code == 200:
                for k, d in r_items.json().items():
                    if "id" in d and "dname" in d:
                        CACHE_ITEMS[str(d["id"])] = {
                            "dname": d["dname"],
                            "sysname": d["name"].replace("item_", "") if "name" in d else ""
                        }
        except Exception as e:
            print(f"Error cargando ítems: {e}")
            
    if not CACHE_HEROES_OD:
        try:
            r_heroes = requests.get("https://api.opendota.com/api/constants/heroes")
            if r_heroes.status_code == 200:
                for k, d in r_heroes.json().items():
                    CACHE_HEROES_OD[d["localized_name"].lower()] = d
        except Exception as e:
            print(f"Error cargando héroes OD: {e}")

# Inicializamos cachés al encender la API
cargar_constantes()

@app.get("/heroes/buscar/{query}")
def buscar_heroes(query: str):
    conexion = None
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        sql = "SELECT id, name FROM heroes WHERE name ILIKE %s LIMIT 15;"
        cursor.execute(sql, (f"%{query}%",))
        resultados = cursor.fetchall()
        
        heroes = []
        for fila in resultados:
            system_name = fila[1].lower().replace(" ", "_").replace("-", "_").replace("'", "").replace("&", "")
            heroes.append({"id": fila[0], "system_name": system_name, "name": fila[1]})
        return heroes
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conexion: conexion.close()

@app.get("/counters/{hero_id}")
def obtener_counters(hero_id: int):
    conexion = None
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        sql = """
            SELECT 
                h.name AS rival_name,
                COALESCE(ROUND((m.wins::numeric / NULLIF(m.games_played, 0)) * 100, 2), 0.0) AS win_rate,
                m.games_played
            FROM matchups m
            JOIN heroes h ON m.rival_id = h.id
            WHERE m.hero_id = %s
            ORDER BY win_rate DESC
            LIMIT 3;
        """
        cursor.execute(sql, (hero_id,))
        resultados = cursor.fetchall()
        
        top_counters = []
        for fila in resultados:
            rival_nombre = fila[0]
            info_od = CACHE_HEROES_OD.get(rival_nombre.lower(), {})
            ataque = info_od.get('attack_type', 'Melee')
            atributo = info_od.get('primary_attr', 'agi').upper()
            
            if atributo == "STR": atributo = "Fuerza 💪"
            elif atributo == "AGI": atributo = "Agilidad ⚡"
            elif atributo == "INT": atributo = "Inteligencia 🔮"
            else: atributo = "Universal 🌀"

            consejo = (
                f"Contra **{rival_nombre}** ({ataque} - {atributo}): "
                f"Aprovecha su dependencia de atributos para denegar farm en fase de líneas. "
                f"Al ser {ataque}, controla el posicionamiento estratégico en las peleas de equipo."
            )
            
            top_counters.append({
                "rival": rival_nombre,                  
                "win_rate_porcentaje": float(fila[1]), 
                "partidas_analizadas": fila[2],
                "tactical_advise": consejo
            })
        return {"top_3_counters": top_counters}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conexion: conexion.close()

@app.get("/build/nombre/{nombre_heroe}")
def obtener_build_en_vivo(nombre_heroe: str):
    conexion = None
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        sql = "SELECT id FROM heroes WHERE name ILIKE %s LIMIT 1;"
        cursor.execute(sql, (f"%{nombre_heroe}%",))
        resultado = cursor.fetchone()
        
        if not resultado: raise HTTPException(status_code=404, detail="Héroe no encontrado.")
        
        url_opendota = f"https://api.opendota.com/api/heroes/{resultado[0]}/itemPopularity"
        respuesta = requests.get(url_opendota)
        datos_items = respuesta.json() if respuesta.status_code == 200 else {}
        
        def procesar_items_cdn(fase_dict):
            if not fase_dict: return []
            ordenados = sorted(fase_dict.items(), key=lambda x: x[1], reverse=True)[:3]
            lista_objetos = []
            for item in ordenados:
                item_id = item[0]
                datos_item = CACHE_ITEMS.get(str(item_id), {"dname": f"Item {item_id}", "sysname": "branches"})
                url_icono = f"https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/items/{datos_item['sysname']}.png"
                lista_objetos.append({
                    "name": datos_item["dname"],
                    "cdn_url": url_icono
                })
            return lista_objetos

        return {
            "early": procesar_items_cdn(datos_items.get("early_game_items", {})),
            "mid": procesar_items_cdn(datos_items.get("mid_game_items", {})),
            "late": procesar_items_cdn(datos_items.get("late_game_items", {}))
        }
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))
    finally:
        if conexion: conexion.close()