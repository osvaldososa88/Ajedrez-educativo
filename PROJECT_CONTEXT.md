♟️ Chess School Platform — Contexto Maestro
1. Objetivo

Construir una plataforma web de ajedrez orientada a un entorno escolar.

La plataforma permitirá que estudiantes y docentes:

Jueguen partidas entre sí en tiempo real.
Se desafíen entre compañeros.
Participen en torneos escolares.
Resuelvan problemas de ajedrez.
Practiquen tácticas, aperturas, medio juego y finales.
Analicen partidas utilizando Stockfish.
Creen sus propios problemas de ajedrez.
Compartan problemas con otros estudiantes.
Reciban entrenamiento basado en sus errores y progreso.
Permitan al docente crear actividades y observar el progreso de los estudiantes.

La idea NO es crear simplemente otro sitio para jugar ajedrez.

El objetivo es crear una:

Plataforma educativa de ajedrez para el aula y la competición escolar.

2. Principios del proyecto
Educación antes que gamificación

La plataforma debe favorecer el aprendizaje.

Los puntos, rankings y medallas son secundarios.

El estudiante debe ser también creador

Los estudiantes no solamente resuelven problemas.

También pueden crear, publicar y compartir problemas.

El motor debe ayudar a aprender

Stockfish no debe convertirse simplemente en un "botón para obtener la respuesta".

En entrenamiento se deben poder utilizar:

pistas
evaluación
variantes
mejores jugadas
análisis posterior

Durante una competición no debe estar disponible.

Arquitectura simple

No construir microservicios innecesariamente.

Preferir un monolito Django bien estructurado.

Desarrollo incremental

No intentar construir toda la plataforma de una vez.

Cada fase debe producir una aplicación funcional.

3. Stack tecnológico preferido

Backend:

Python
Django
PostgreSQL
Django Channels
Redis
Celery o una alternativa equivalente para trabajos asíncronos
Django REST Framework cuando sea necesario
python-chess
Stockfish

Frontend inicial:

Django Templates
HTMX
JavaScript
CSS/Tailwind o Bootstrap

Infraestructura:

Linux VPS
Docker/Docker Compose
Nginx
HTTPS
PostgreSQL
Redis

No utilizar React/Vue inicialmente salvo que exista una razón técnica clara.

4. Biblioteca de ajedrez

Utilizar python-chess como núcleo de la lógica ajedrecística.

No implementar manualmente:

movimientos legales
FEN
SAN
UCI
PGN
reglas de ajedrez

cuando python-chess pueda resolverlo.

La aplicación debe confiar en python-chess para la validación de posiciones y movimientos.

5. Motor

Utilizar Stockfish.

No desarrollar un motor de ajedrez propio.

Stockfish debe utilizarse para:

análisis
evaluación
mejores movimientos
variantes
validación de problemas
entrenamiento

El análisis pesado debe ejecutarse mediante trabajos asíncronos.

Nunca bloquear una petición HTTP durante un análisis prolongado de Stockfish.

6. Concepto arquitectónico importante

La posición de ajedrez es un concepto central.

Una posición representada mediante FEN puede formar parte de:

una partida
un problema
un ejercicio
un entrenamiento
un final
una apertura
un análisis

No diseñar el sistema suponiendo que todo gira exclusivamente alrededor de las partidas.

7. Módulos previstos

Inicialmente se contemplan:

accounts
classrooms
games
tournaments
puzzles
training
analysis
openings
endgames
ratings
notifications
core

No necesariamente todos deben implementarse desde el principio.

8. Roles
ADMIN

Control total del sistema.

DOCENTE

Puede:

gestionar aulas
gestionar estudiantes
crear actividades
crear problemas
crear desafíos
crear torneos
analizar progreso
moderar problemas
consultar estadísticas
ESTUDIANTE

Puede:

jugar
desafiar compañeros
resolver problemas
crear problemas
analizar sus partidas
entrenar
consultar su progreso
participar en torneos
9. Modos de utilización
Competición
Sin Stockfish.
Sin pistas.
Sin sugerencias.
Solo reglas y reloj.
Entrenamiento

Puede incluir:

pistas
intentos
feedback
evaluación controlada
Análisis

Permite:

Stockfish
variantes
evaluación
exploración de posiciones
10. Evolución prevista
Fase 1 — Partidas

Construir:

usuarios
perfiles
tablero
desafíos
partidas en tiempo real
reloj
movimientos legales
finalización
almacenamiento PGN
Fase 2 — Análisis

Construir:

visor de partidas
PGN
FEN
análisis Stockfish
variantes
evaluación
importación/exportación PGN
Fase 3 — Entrenamiento

Construir:

problemas
categorías
dificultad
pistas
soluciones
tácticas
aperturas
finales
estadísticas
Fase 4 — Creación de contenido

Construir:

creador de problemas
validación
publicación
problemas creados por estudiantes
moderación docente
compartir
favoritos
Fase 5 — Aula

Construir:

aulas
actividades
desafíos docentes
tareas
seguimiento
estadísticas
progreso individual
Fase 6 — Torneos

Construir:

torneos
rondas
sistema suizo
resultados
clasificación
desempates
rankings
Fase 7 — Entrenamiento personalizado

A partir de:

partidas
errores
problemas resueltos
problemas fallados
temas débiles
aperturas
finales

generar recomendaciones personalizadas.

11. Funcionalidad especialmente importante

Una partida analizada puede generar automáticamente posiciones de entrenamiento.

Flujo:

JUGAR
→ ANALIZAR
→ DETECTAR ERROR
→ EXTRAER POSICIÓN
→ CREAR EJERCICIO
→ ENTRENAR
→ VOLVER A JUGAR

Esta característica debe tenerse en cuenta al diseñar los modelos de datos.

12. Filosofía de desarrollo

Antes de implementar cada módulo:

Analizar requisitos.
Revisar arquitectura existente.
Revisar modelos existentes.
Evitar duplicar funcionalidades.
Proponer cambios.
Implementar.
Crear pruebas.
Ejecutar pruebas.
Revisar seguridad.
Documentar.

Nunca modificar arquitectura existente sin comprender primero el código.

No borrar funcionalidades existentes simplemente para simplificar.

13. Calidad

El código debe ser:

mantenible
modular
probado
documentado
seguro
preparado para crecer

Prestar especial atención a:

autenticación
autorización
permisos por rol
validación de movimientos
WebSockets
concurrencia
partidas simultáneas
seguridad de PostgreSQL
protección de datos de estudiantes
rate limiting
validación de archivos PGN
ejecución segura de Stockfish
14. Regla para el agente

Antes de escribir código, inspeccionar el proyecto existente.

Si existe una decisión arquitectónica previa, respetarla salvo que exista una razón técnica clara para modificarla.

Si se detecta un problema importante, explicarlo antes de realizar un cambio estructural.

No implementar funcionalidades de fases futuras sin necesidad.

Cada fase debe dejar el sistema funcionando.