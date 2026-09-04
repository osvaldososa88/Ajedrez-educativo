# Módulo de Torneos (`apps.tournaments`) — Fase 6

## 1. Objetivo

Permitir usar la plataforma durante campeonatos escolares, apoyándose sobre el sistema de
partidas ya existente (`apps.games`) sin modificarlo: cada emparejamiento de torneo que no es un
bye crea una `games.Game` normal, jugada con el mismo tablero, WebSocket y validación de
movimientos en servidor que cualquier otra partida.

## 2. Modelos

- **`Tournament`**: nombre, descripción, `organizers` (M2M, admite co-organizadores),
  `format` (`ROUND_ROBIN` / `SWISS`, extensible), `status`
  (`DRAFT` → `REGISTRATION_OPEN` → `IN_PROGRESS` → `COMPLETED` / `CANCELLED`), fecha,
  `rounds_total` (obligatorio para Suizo, calculado automáticamente en Todos contra Todos),
  ritmo de juego (`time_control_minutes`/`increment`, mismo patrón que `games.Challenge`).
- **`TournamentParticipant`**: inscripción de un usuario, con `seed_rating` (snapshot del ELO al
  inscribirse, para que cambios posteriores no alteren el sembrado retroactivamente) y
  `had_bye`.
- **`Round`**: número de ronda y estado (`PENDING` / `IN_PROGRESS` / `COMPLETED`).
- **`Pairing`**: un tablero de una ronda — blancas, negras (o bye), `game` (`OneToOneField` a
  `games.Game`, `null=True`), `result`, y flags de ausencia (`white_absent`/`black_absent`).

## 3. Arquitectura de emparejamiento (extensible)

`apps/tournaments/pairing.py` define `BasePairingService` y un registro `PAIRING_SERVICES`
resuelto por `get_pairing_service(tournament)`. Añadir un formato nuevo (ej. eliminación directa)
solo requiere implementar la interfaz y registrarla — no toca `TournamentService` ni los modelos.

- **`RoundRobinPairingService`** (`supports_all_rounds_upfront = True`): método del círculo
  clásico. Con N participantes (se añade un "bye" si N es impar) genera **todo el calendario de
  antemano**: N-1 rondas si N es par, N rondas si es impar (incluyendo el bye). Cada participante
  recibe como máximo un bye en todo el torneo.
- **`SwissPairingService`** (`supports_all_rounds_upfront = False`): cada ronda se genera a partir
  de la clasificación actual. Ordena por puntos (y ELO de inscripción como desempate inicial),
  empareja secuencialmente evitando repetir rivales cuando hay alternativa, y asigna el bye al
  jugador de menor puntaje que todavía no haya tenido uno. El color se asigna equilibrando cuántas
  veces cada jugador ya jugó con blancas.
  **Simplificación documentada**: no implementa el sistema Suizo-Holandés completo de la FIDE
  (sin "floaters" entre grupos de puntaje ni balance de color histórico complejo) — suficiente
  para un torneo escolar, con posibilidad de reemplazo futuro sin tocar el resto del sistema.

## 4. Clasificación (`standings.py`)

`StandingsService.compute_standings(tournament)` calcula, para cada participante: puntos
(victoria=1, tablas=0.5, derrota=0, bye=1 punto completo), victorias/tablas/derrotas,
partidas jugadas, y **desempate Buchholz** (suma de los puntos finales de todos sus rivales,
excluyendo byes). El orden final es `(-puntos, -Buchholz, -victorias, username)`, con
**ranking de competición**: jugadores empatados en los tres criterios comparten la misma
posición. Otros sistemas de desempate (Sonneborn-Berger, encuentro directo, puntaje progresivo)
quedan documentados como extensión futura, no implementados todavía.

## 5. Ciclo de vida (`services.py` — `TournamentService`)

```
DRAFT ──(abrir inscripción)──▶ REGISTRATION_OPEN ──(iniciar, ≥2 inscritos)──▶ IN_PROGRESS ──▶ COMPLETED
                                                                                  │
                                                                                  └──▶ CANCELLED (en cualquier momento salvo COMPLETED)
```

- **`start_tournament`**: Round Robin genera y persiste **todas** las rondas/emparejamientos de
  una vez (el calendario es determinista) y abre la primera; Suizo exige `rounds_total` y genera
  solo la ronda 1.
- **`open_round`**: crea las `games.Game` reales para los emparejamientos sin bye de esa ronda
  (reutilizando el modelo existente, `is_competitive=True`) y marca la ronda `IN_PROGRESS`.
- **`generate_next_round`**: en Round Robin simplemente abre la siguiente ronda ya calculada; en
  Suizo exige que la ronda anterior esté `COMPLETED`, recalcula la clasificación y genera los
  nuevos emparejamientos.
- **`sync_finished_games`**: cuando una partida termina jugándose normalmente (jaque mate, tiempo,
  abandono, tablas acordadas — toda la lógica ya existente de `apps.games`), esta función copia el
  resultado a su `Pairing` la próxima vez que se consulta el torneo. No se usan señales; se invoca
  explícitamente al ver el detalle del torneo/ronda o al cerrar una ronda.
- **`record_incident`**: el organizador registra una ausencia (una o ambas); calcula el resultado
  (`WHITE_WIN`/`BLACK_WIN`/`DOUBLE_FORFEIT`) y, si la partida ya se había creado, la marca
  `ABANDONED` (reutilizando `Game.FinishReason.RESIGNATION`, sin agregar un motivo nuevo al
  modelo de partidas).
- **`close_round`**: exige que todos los emparejamientos tengan resultado (sincronizando primero
  las partidas terminadas); si falta alguno, pide registrar el resultado o una ausencia primero.
- **`finalize_tournament`**: exige que todas las rondas generadas estén `COMPLETED`.

## 6. Competición: sin motor, sin pistas, sin análisis

Las partidas de torneo son instancias normales de `games.Game` con `is_competitive=True`, jugadas
con el mismo `GameConsumer` ya existente — **la validación de movimientos en servidor** viene
gratis, sin duplicar lógica. Para bloquear el análisis mientras la ronda está en curso, se agregó
una única comprobación en
[`apps/analysis/views.py`](../analysis/views.py) (`create_game_analysis_job`): si la partida está
`IN_PROGRESS` y tiene un `tournament_pairing` asociado (relación inversa del `OneToOneField` de
`Pairing.game`), se rechaza con 403. Terminada la partida, el análisis vuelve a estar disponible
para revisión posterior, igual que cualquier otra partida. La evaluación rápida de posición
(`analyze_single_fen_api`) ya rechazaba `mode=COMPETITION` desde la Fase 2; no fue necesario
tocarla. Las pistas de entrenamiento (Fase 3) solo aplican a `Puzzle`, no a `Game`, por lo que no
hay superposición que gestionar ahí.

## 7. Permisos

| Acción | Quién puede |
|---|---|
| Crear un torneo | `TEACHER`/`ADMIN`/`is_staff`. |
| Inscribirse / retirarse | Cualquier usuario autenticado, mientras el torneo esté en `DRAFT`/`REGISTRATION_OPEN` (retirarse durante `IN_PROGRESS` requiere contactar al organizador). |
| Abrir inscripción, iniciar, generar ronda, finalizar, cancelar | Solo organizadores del torneo (`Tournament.is_organizer`). |
| Cerrar ronda, registrar incidencia, corregir resultado | Solo organizadores del torneo. |
| Ver torneo, rondas y clasificación | Cualquier usuario autenticado (transparencia pública del campeonato escolar). |

## 8. Tests

Ver [tests/test_tournaments.py](../../tests/test_tournaments.py) (33 tests): calendario de
Round Robin (par/impar, cobertura completa de emparejamientos, un bye por jugador), emparejamiento
Suizo (ronda 1 por rating, evita revanchas, bye al de menor puntaje sin bye previo, balance de
color), clasificación (puntos/victorias/tablas/derrotas, Buchholz, orden y empates de ranking),
ciclo de vida completo (inscripción, inicio, apertura de rondas con creación real de `Game`,
incidencias de ausencia simple/doble, cierre de ronda, finalización), sincronización automática de
resultados desde partidas terminadas, y permisos (creación, inicio, incidencias — organizador vs.
no organizador) incluyendo el bloqueo de análisis durante una partida de torneo en curso y su
liberación al finalizar.

## 9. Extensiones futuras

- Formatos adicionales (eliminación directa/simple, doble ronda) vía `PAIRING_SERVICES`.
- Desempates adicionales configurables por torneo (Sonneborn-Berger, encuentro directo).
- Emparejamiento Suizo completo estilo FIDE (Dutch system) con balance de color y floaters.
- Notificaciones a los participantes cuando se genera una nueva ronda.
- Exportar clasificación final y calendario a PDF/PGN para publicar en la cartelera del colegio.
