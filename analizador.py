import requests

def obtener_matchups_heroe(hero_id):
    """Obtiene el historial de enfrentamientos de un héroe."""
    url = f"https://api.opendota.com/api/heroes/{hero_id}/matchups"
    try:
        respuesta = requests.get(url)
        respuesta.raise_for_status()
        return respuesta.json()
    except requests.exceptions.RequestException as error:
        print(f"Error al obtener matchups: {error}")
        return None

def obtener_diccionario_heroes():
    """
    Se conecta a la API para obtener todos los héroes y crea un 
    diccionario donde la 'llave' es el ID y el 'valor' es el nombre real.
    """
    url = "https://api.opendota.com/api/heroes"
    try:
        respuesta = requests.get(url)
        respuesta.raise_for_status()
        lista_heroes = respuesta.json()
        
        # Transformamos la lista en un diccionario: {86: 'Rubick', 14: 'Pudge', ...}
        diccionario = {}
        for heroe in lista_heroes:
            diccionario[heroe['id']] = heroe['localized_name']
            
        return diccionario
    except requests.exceptions.RequestException as error:
        print(f"Error al obtener la lista de héroes: {error}")
        return {}

# --- LÓGICA PRINCIPAL ---
if __name__ == "__main__":
    ID_HEROE_ANALIZAR = 86 # Rubick
    
    print("1. Descargando diccionario de héroes...")
    nombres_heroes = obtener_diccionario_heroes()
    
    print("2. Consultando matchups históricos...\n")
    datos_matchups = obtener_matchups_heroe(ID_HEROE_ANALIZAR)
    
    if datos_matchups and nombres_heroes:
        matchups_validos = [m for m in datos_matchups if m['games_played'] > 50]
        
        top_counters = sorted(
            matchups_validos, 
            key=lambda x: x['wins'] / x['games_played'], 
            reverse=True
        )
        
        # Obtenemos el nombre del héroe que estamos analizando
        nombre_mi_heroe = nombres_heroes.get(ID_HEROE_ANALIZAR, "Héroe Desconocido")
        print(f"--- TOP 3 PEORES ENFRENTAMIENTOS PARA {nombre_mi_heroe.upper()} ---")
        
        for i in range(3):
            rival = top_counters[i]
            id_rival = rival['hero_id']
            # Usamos nuestro diccionario para traducir el ID al nombre real
            nombre_rival = nombres_heroes.get(id_rival, f"ID {id_rival}")
            
            win_rate_rival = (rival['wins'] / rival['games_played']) * 100
            print(f"{i+1}. {nombre_rival}: Gana el {win_rate_rival:.1f}% de las partidas.")