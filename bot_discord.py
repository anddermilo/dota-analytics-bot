import os
import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import time
from dotenv import load_dotenv

# --- SISTEMA DE CONTROL DEFENSIVO DE ENTORNO (WINDOWS PROOF) ---
ruta_actual = os.path.dirname(os.path.abspath(__file__))
ruta_env = os.path.join(ruta_actual, '.env')

if os.path.exists(ruta_env):
    load_dotenv(ruta_env)
    # Si python-dotenv falla por codificación, forzamos lectura manual limpia
    if not os.getenv("DISCORD_TOKEN") or not os.getenv("API_URL"):
        with open(ruta_env, "r", encoding="utf-8-sig") as f:
            for linea in f:
                if "=" in linea and not linea.strip().startswith("#"):
                    clave, valor = linea.split("=", 1)
                    os.environ[clave.strip()] = valor.strip().replace('"', '').replace("'", "")

TOKEN_BOT = os.getenv("DISCORD_TOKEN")
API_URL = os.getenv("API_URL", "http://localhost:8000")

if not TOKEN_BOT:
    print(f"❌ ERROR CRÍTICO INTERNO: No se pudo procesar el DISCORD_TOKEN.")
    print(f"Revisando ruta de configuración en: {ruta_env}")
    exit()

# Configuración limpia de Intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

CACHE_AUTOCOMPLETE = {}
CACHE_TTL_SEGUNDOS = 30
PARCHE_ACTUAL = "7.37e"

async def autocompletar_heroe(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    if not current: return [] 
    current_lower = current.lower()
    ahora = time.time()
    
    if current_lower in CACHE_AUTOCOMPLETE:
        datos_cache, expiracion = CACHE_AUTOCOMPLETE[current_lower]
        if ahora < expiracion: return datos_cache
            
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_URL}/heroes/buscar/{current}") as r:
            if r.status == 200:
                heroes = await r.json()
                opciones = [
                    app_commands.Choice(name=h['name'], value=f"{h['id']}|{h['system_name']}|{h['name']}") 
                    for h in heroes
                ][:15]
                CACHE_AUTOCOMPLETE[current_lower] = (opciones, ahora + CACHE_TTL_SEGUNDOS)
                return opciones
    return []

async def procesar_seleccion(session, input_str):
    if "|" in input_str:
        partes = input_str.split("|")
        return partes[0], partes[1], partes[2] 
    else:
        async with session.get(f"{API_URL}/heroes/buscar/{input_str}") as r:
            if r.status == 200:
                data = await r.json()
                return data[0]['id'], data[0]['system_name'], data[0]['name']
            return None, None, None

class CounterTabsView(discord.ui.View):
    def __init__(self, counter_c, hero_name, original_embed, original_view):
        super().__init__(timeout=120)
        self.counter_c = counter_c
        self.hero_name = hero_name
        self.original_embed = original_embed
        self.root_view = original_view
        self.active_tab = "items"

    @discord.ui.button(label="🎒 Ítems", style=discord.ButtonStyle.primary, custom_id="tab_items")
    async def btn_items(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.active_tab = "items"
        await self.render(interaction)

    @discord.ui.button(label="⚔️ Estrategia", style=discord.ButtonStyle.secondary, custom_id="tab_strategy")
    async def btn_strategy(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.active_tab = "strategy"
        await self.render(interaction)
        
    @discord.ui.button(label="🔙 Volver", style=discord.ButtonStyle.danger, custom_id="tab_back")
    async def btn_back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=self.original_embed, view=self.root_view)

    async def render(self, interaction: discord.Interaction):
        await interaction.response.defer()
        rival = self.counter_c['rival']
        sys_rival = rival.lower().replace(" ", "_").replace("-", "_").replace("'", "")
        
        embed_tab = discord.Embed(
            title=f"📖 Guía Táctica: {rival} vs {self.hero_name}",
            color=discord.Color.dark_purple()
        )
        embed_tab.set_thumbnail(url=f"https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/{sys_rival}.png")

        if self.active_tab == "items":
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{API_URL}/build/nombre/{rival}") as r:
                    if r.status == 200:
                        build = await r.json()
                        
                        def formatear_fase(lista_objetos, emoji):
                            if not lista_objetos: return "Datos insuficientes"
                            texto_salida = ""
                            for obj in lista_objetos:
                                texto_salida += f"{emoji} [{obj['name']}]({obj['cdn_url']})\n"
                            return texto_salida.strip()

                        texto = (
                            f"🟢 **Fase de Líneas (Min 0-10):**\n{formatear_fase(build['early'], '🟢')}\n\n"
                            f"🟡 **Medio Juego (Min 10-25):**\n{formatear_fase(build['mid'], '🟡')}\n\n"
                            f"🟠 **Juego Tardío (Min 25+):**\n{formatear_fase(build['late'], '🟠')}"
                        )
                        embed_tab.add_field(name="🎒 Build de Ítems Populares (CDN)", value=texto, inline=False)
        
        elif self.active_tab == "strategy":
            embed_tab.add_field(name="⚔️ Análisis de Matchup", value=self.counter_c.get("tactical_advise"), inline=False)
            embed_tab.add_field(name="💡 Consejos de Juego", value="Prioriza el control del mapa en jungla y deniega sus transiciones de rotación.", inline=False)

        embed_tab.set_footer(text=f"🎯 Winrate matchup: {self.counter_c['win_rate_porcentaje']}% | Parche: {PARCHE_ACTUAL}")
        await interaction.edit_original_response(embed=embed_tab, view=self)

class CounterSelectView(discord.ui.View):
    def __init__(self, counters_list, hero_name, embed_pantalla):
        super().__init__(timeout=120)
        for idx, c in enumerate(counters_list):
            boton = discord.ui.Button(
                label=f"Guía {c['rival']}", 
                style=discord.ButtonStyle.secondary,
                custom_id=f"btn_go_{idx}",
                emoji="📖"
            )
            boton.callback = self.crear_callback(c, hero_name, embed_pantalla)
            self.add_item(boton)

    def crear_callback(self, c, hero_name, embed_pantalla):
        async def a_ejecutar(interaction: discord.Interaction):
            tabs_view = CounterTabsView(c, hero_name, embed_pantalla, self)
            await tabs_view.render(interaction)
        return a_ejecutar

@bot.event
async def on_ready():
    print(f'⚡ DOTA ANALYTICS PRO - DESPLIEGUE SEGURO COMPLETO ⚡')
    try:
        mi_servidor = discord.Object(id=1515013096316473506)
        bot.tree.copy_global_to(guild=mi_servidor)
        synced = await bot.tree.sync(guild=mi_servidor)
        print(f"Comandos sincronizados de forma nativa: {len(synced)}")
    except Exception as e:
        print(f"Error en sincronización: {e}")

@bot.tree.command(name="counter", description="Averigua qué héroe elegir para contrarrestar a un enemigo.")
@app_commands.autocomplete(heroe=autocompletar_heroe)
@app_commands.describe(heroe="Nombre del héroe enemigo a consultar")
async def counter(interaction: discord.Interaction, heroe: str):
    await interaction.response.defer(thinking=True)
    async with aiohttp.ClientSession() as session:
        hero_id, system_name, hero_name = await procesar_seleccion(session, heroe)
        
        if not hero_id:
            await interaction.followup.send("⚠️ Héroe inválido. Selecciona una opción del autocompletado.", ephemeral=True)
            return

        url_api = f"{API_URL}/counters/{hero_id}"
        async with session.get(url_api) as r:
            if r.status == 200:
                datos = await r.json()
                avatar_url = f"https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/{system_name}.png"
                
                embed = discord.Embed(
                    title=f"⚔️ Counters para derrotar a {hero_name}",
                    description=f"💡 **Fase de Picks:** Si el rival aseguró a **{hero_name}**, tienes ventaja seleccionando:",
                    color=discord.Color.red()
                )
                embed.set_thumbnail(url=avatar_url)
                embed.set_footer(text=f"Dota Analytics Pro")
                
                for i, c in enumerate(datos["top_3_counters"], 1):
                    emoji = "🥇" if i==1 else "🥈" if i==2 else "🥉"
                    embed.add_field(
                        name=f"{emoji} {c['rival']}",
                        value=f"🎯 **Tasa de victoria:** {c['win_rate_porcentaje']}% *(Basado en {c['partidas_analizadas']} partidas)*",
                        inline=False
                    )
                
                vista_opciones = CounterSelectView(datos["top_3_counters"], hero_name, embed)
                await interaction.followup.send(embed=embed, view=vista_opciones)
            else:
                await interaction.followup.send("⚠️ No se encontraron registros para este héroe.", ephemeral=True)

if __name__ == "__main__":
    bot.run(TOKEN_BOT)