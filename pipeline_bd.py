import requests
import time 
import pg8000.dbapi

# Configuración de conexión usando pg8000
# Nota: pg8000 usa 'database' en lugar de 'dbname' y el puerto debe ser un número
DB_CONFIG = {
    "database": "dota_analytics",
    "user": "postgres",
    "password": "123456", # Reemplaza con tu clave de pgAdmin
    "host": "localhost",
    "port": 5432  
}

def obtener_datos_api(url): 
    """Consulta la API de OpenDota y devuelve los datos en formato JSON.""" 
    try:
        respuesta = requests.get(url)
        respuesta.raise_for_status()
        return respuesta.json()
    except requests.exceptions.RequestException as e:
        print(f"Error de conexión con la API en {url}: {e}")
        return None

def inicializar_base_de_datos(): 
    """Verifica y crea las tablas necesarias en PostgreSQL si no existen."""
    comandos = (
        """
        CREATE TABLE IF NOT EXISTS heroes (
            id INTEGER PRIMARY KEY,
            name VARCHAR(100) NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS matchups (
            hero_id INTEGER REFERENCES heroes(id) ON DELETE CASCADE,
            rival_id INTEGER REFERENCES heroes(id) ON DELETE CASCADE,
            games_played INTEGER NOT NULL,
            wins INTEGER NOT NULL,
            PRIMARY KEY (hero_id, rival_id)
        )
        """
    )
    conexion = None
    try:
        conexion = pg8000.dbapi.connect(**DB_CONFIG)
        cursor = conexion.cursor()
        for comando in comandos:
            cursor.execute(comando)
        cursor.close()
        conexion.commit()
        print("Estructura de Base de Datos verificada correctamente.")
    except Exception as error:
        print(f"Error al inicializar la BD: {error}")
    finally:
        if conexion is not None:
            conexion.close()

def guardar_heroes(lista_heroes):
    """Inserta o actualiza el catálogo maestro de héroes en la tabla 'heroes'."""
    sql = """
        INSERT INTO heroes(id, name) VALUES(%s, %s)
        ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;
    """
    conexion = None
    try:
        conexion = pg8000.dbapi.connect(**DB_CONFIG)
        cursor = conexion.cursor()
        
        datos_insertar = [(h['id'], h['localized_name']) for h in lista_heroes]
        cursor.executemany(sql, datos_insertar)
        conexion.commit()
        cursor.close()
        print(f"Catálogo actualizado: {len(lista_heroes)} héroes guardados.")
    except Exception as error:
        print(f"Error al guardar héroes: {error}")
    finally:
        if conexion is not None:
            conexion.close()

def guardar_matchups(hero_id, lista_matchups):
    """Inserta o actualiza los enfrentamientos en la tabla 'matchups'."""
    sql = """
        INSERT INTO matchups(hero_id, rival_id, games_played, wins) 
        VALUES(%s, %s, %s, %s)
        ON CONFLICT (hero_id, rival_id) DO UPDATE SET 
            games_played = EXCLUDED.games_played,
            wins = EXCLUDED.wins;
    """
    conexion = None
    try:
        conexion = pg8000.dbapi.connect(**DB_CONFIG)
        cursor = conexion.cursor()
        
        datos_insertar = [
            (hero_id, m['hero_id'], m['games_played'], m['wins']) 
            for m in lista_matchups
        ]
        
        cursor.executemany(sql, datos_insertar)
        conexion.commit()
        cursor.close()
        print(f"Historial de Matchups guardado exitosamente para el héroe ID {hero_id}.")
    except Exception as error:
        print(f"Error al guardar matchups: {error}")
    finally:
        if conexion is not None:
            conexion.close()

# ==========================================
# LÓGICA PRINCIPAL (PIPELINE DE DATOS)
# ==========================================
# ==========================================
# LÓGICA PRINCIPAL (PIPELINE MASIVO)
# ==========================================
if __name__ == "__main__":
    print("--- INICIANDO PIPELINE DE EXTRACCIÓN MASIVA ---")
    
    inicializar_base_de_datos()
    
    print("\n1. Consultando catálogo global de héroes...")
    datos_heroes = obtener_datos_api("https://api.opendota.com/api/heroes")
    
    if datos_heroes:
        guardar_heroes(datos_heroes)
        
        print("\n2. Descargando enfrentamientos para TODOS los héroes...")
        print("NOTA: Esto tomará un par de minutos para no saturar el servidor.\n")
        
        # Recorremos la lista completa de héroes
        for heroe in datos_heroes:
            id_actual = heroe['id']
            nombre_actual = heroe['localized_name']
            
            print(f"Procesando a {nombre_actual} (ID: {id_actual})...")
            
            # Consultamos la API para el héroe actual
            datos_matchups = obtener_datos_api(f"https://api.opendota.com/api/heroes/{id_actual}/matchups")
            
            if datos_matchups:
                guardar_matchups(id_actual, datos_matchups)
            
            # Pausa de 1 segundo (¡Crucial para que no nos bloqueen!)
            time.sleep(1)
            
    print("\n--- BASE DE DATOS POBLADA AL 100% ---")