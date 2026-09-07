# 🤖 Bots de Entrenamiento

Modo de progresión para jugar contra bots de ajedrez cuando no hay compañeros
disponibles. Las partidas contra bots son **partidas normales** de la plataforma
(modelo `games.Game` jugadas por el mismo `GameConsumer`), por lo que **reutilizan
sin cambios** el historial, el análisis con Stockfish, la creación de problemas y
el sistema para compartirlos.

## Modelos (`apps/bots/models.py`)

| Modelo | Qué representa |
|---|---|
| `BotProfile` | **Cómo juega** el bot: `engine_depth`, `move_time_ms`, `skill_level` (0–20), `multipv`, `error_probability`, `uci_elo` (opcional). Compartido por muchos bots. |
| `Bot` | **Quién es** el bot: `display_name`, `nickname`, `avatar` (emoji), `description`, `quote`, `category` (BEGINNER/INTERMEDIATE/ADVANCED), `order` (progresión dentro de la categoría), `displayed_elo` (etiqueta de dificultad, **estática**), `profile` (fuerza), `is_active`. Tiene una cuenta interna `CustomUser` (rol `BOT`, sin contraseña) vía `bot_profile`. |
| `BotProgress` | Progreso **por estudiante**: `unlocked` / `defeated` / `defeated_at`. Filas creadas bajo demanda. |

Identidad vs. nombre: el nombre mostrado (`display_name`) se edita en el Admin y
puede repetirse entre categorías ("Mateo" principiante, intermedio y avanzado son
tres bots distintos con cuentas internas diferentes `bot_xxxxx`).

## Desbloqueo

- El **primer bot ACTIVO de cada categoría** (por `order`) está siempre
  desbloqueado para todos (derivado, sin fila en BD).
- Derrotar a un bot desbloquea al **siguiente bot ACTIVO** de la **misma
  categoría** (`BotProgress.unlocked=True`) + notificación.
- Derrotas y tablas no desbloquean nada. Progresión independiente por estudiante
  y por categoría.
- **Bot desactivado**: deja de ser seleccionable y la progresión lo salta (el
  "siguiente bot activo" pasa a ser el desbloqueable). No rompe nada.

## Partidas contra bots

- Se crean con `is_competitive=False` y `vs_bot=True` (además `RatingService`
  excluye explícitamente partidas con bots) → **no modifican el ELO competitivo
  de nadie**. El ELO del bot es estático y solo cambia si un docente lo edita.
- **Sin reloj**: el reloj nunca arranca en partidas de bot (`GameConsumer`
  omite el arranque en ply 2 si `vs_bot`).
- El bot responde automáticamente por el mismo WebSocket: tras cada jugada
  humana (y al reconectar si le toca), `BotService.prepare_bot_move` →
  `compute_uci` (Stockfish en hilo worker) → se aplica con el mismo
  `process_move` server-authoritative que usan los humanos.
- Si el mismo jugador ya tiene una partida activa contra ese bot, se retoma en
  lugar de crear otra.
- Color: blancas / negras / aleatorio, elegido en la ficha del bot.

## Motor (`apps/bots/engine.py`)

- **Un solo proceso Stockfish por worker**, creado perezosamente al primer
  movimiento de bot y compartido con un `Lock` (nunca 90 motores). Reutiliza la
  resolución de binario de `apps.core.stockfish_engine`
  (`settings.STOCKFISH_PATH` o PATH del sistema).
- Debilidad pedagógica: `Skill Level` bajo + profundidad limitada + con
  probabilidad `error_probability` juega un **candidato secundario de MultiPV**
  (líneas razonables del motor), nunca jugadas absurdas al azar.
- Si el binario no está disponible o el proceso muere: reintenta reiniciando el
  proceso; como último recurso usa un movimiento de emergencia (captura/jaque o
  legal aleatorio) para que la partida no se cuelgue.

## Administración (Django Admin → "Bots de Entrenamiento")

- **Bots**: crear/editar/ordenar, cambiar nombre, apodo, avatar, descripción,
  frase, categoría, orden, ELO mostrado, activar/desactivar, perfil de fuerza.
  Filtros por categoría/activo/perfil y búsqueda por nombre.
- **Perfiles de Bot**: dificultad real del motor.
- **Progresos de Bot**: consulta del progreso de los estudiantes.

### "¿Cómo cambio los nombres el próximo año?"

Admin → Bots → editar `Nombre mostrado` (y apodo/frase si querés) → guardar.
No hay que tocar código ni datos en otra parte: tablero, historial, PGN,
análisis y pantalla de bots usan siempre el nombre actual.

### "¿Cómo agrego un bot?"

Admin → Bots → Agregar: elegir categoría y `order` (el siguiente libre),
perfil de fuerza, ELO mostrado y datos de identidad. La cuenta interna se crea
con `Bot.create_bot_account()` (o vía `python manage.py seed_bots` para lotes).

### "¿Cómo cambio la dificultad?"

Editar el **perfil** del bot (depth/skill/multipv/error) o asignarle otro perfil.
El "ELO mostrado" es solo etiqueta.

## Datos iniciales

```bash
python manage.py seed_bots
```

Crea 12 perfiles (4 por categoría) y 90 bots (30 por categoría, ELO
progresivo 700–990 / 1050–1340 / 1400–1835). Idempotente: se puede volver a
ejecutar para reparar/actualizar sin duplicar.

## Tests

`tests/test_bots.py` (33 tests): modelos, nombres repetidos, orden, desbloqueo
(primer bot, victoria, independencia por alumno/categoría, bots desactivados),
creación de partidas, aislamiento de ELO, seguridad (bot bloqueado/inactivo,
retos y torneos), historial filtrable, análisis, título de puzzles, seed,
selección de jugada del motor y respuesta automática por WebSocket.
