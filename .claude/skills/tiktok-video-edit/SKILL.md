---
name: tiktok-video-edit
description: Monta y exporta vídeos verticales listos para TikTok (también Reels y Shorts) a partir de varios clips grabados con el móvil, usando ffmpeg desde la línea de comandos. Analiza el material (hojas de contactos, movimiento, luz, color, sonido, cortes de escena), hace una lectura artística de cada clip, elige las mejores escenas, el orden, los efectos (zoom, punch, grano, etalonaje...) y las transiciones, y luego une los clips en 9:16 (1080x1920) con título, subtítulos .srt y música, exportando H.264/AAC en el formato que TikTok acepta. Usa este skill SIEMPRE que el usuario quiera editar, montar, unir, recortar, elegir las mejores escenas, poner música, efectos o subtítulos, o "preparar para subir" vídeos cortos para TikTok, Instagram Reels o YouTube Shorts, aunque no diga "ffmpeg" ni "skill": frases como "tengo varios vídeos del móvil y quiero hacer un TikTok", "elige lo mejor de estos vídeos", "júntame estos clips en vertical", "ponle música y subtítulos" o "recorta estos vídeos para Reels" deben activarlo.
---

# Edición de vídeo para TikTok con ffmpeg

Dos scripts de Python que solo necesitan ffmpeg: `scripts/analyze.py` (análisis y propuesta de
montaje) y `scripts/tiktok_edit.py` (render). El flujo es: analizar → mirar → proponer → montar → revisar.
Genera un MP4 vertical 1080x1920 a 30 fps, H.264 (perfil high, yuv420p) + AAC 192 kbps, con
`faststart` y el volumen normalizado a -14 LUFS. Ese es el formato que TikTok recomienda y no
recodifica mal.

## 1. Comprobar ffmpeg

```bash
python3 scripts/tiktok_edit.py probe --help >/dev/null && echo ok
```

Si falla por falta de ffmpeg, ejecuta `bash scripts/ensure_ffmpeg.sh` (usa apt/brew si hay
permisos y, si no, instala el binario estático `pip install imageio-ffmpeg`, que el script
detecta solo).

## 2. Analizar el material y mirarlo

```bash
python3 scripts/analyze.py analyze IMG_*.mp4 -o analisis
```

Por cada clip escribe en `analisis/`: una hoja de contactos `contact_<clip>.jpg` (un fotograma
cada N segundos con su hora rotulada) y, en `analysis.json`, métricas por segundo (movimiento,
nitidez, luz, saturación, tono, volumen), cortes de escena, tramos negros/quemados/estáticos/mudos,
una puntuación 0-10 por segundo y los `best_segments` de cada clip. En consola sale un resumen
("luminoso, movido, colorido, cálido; 2 planos, 18/21 s aprovechables") y los mejores tramos.

Después abre las hojas de contactos con la herramienta de leer imágenes y míralas de verdad: los
números no saben qué es una cara, un gesto o un paisaje. Con `references/direccion-artistica.md`
delante, anota para cada clip qué pasa, encuadre, luz, movimiento y sonido, y decide gancho,
desarrollo y remate. Ese análisis se lo cuentas al usuario en pocas líneas antes de montar, para
que pueda corregir el rumbo (qué quiere destacar, tono, duración, si hay voz que respetar).

## 3. Proponer el montaje

```bash
python3 scripts/analyze.py suggest analisis/analysis.json -o plan.json --target 30 --style dynamic --title "Gancho"
```

Genera un `plan.json` listo para renderizar y un `plan.md` con el porqué de cada decisión: tramo
elegido de cada clip, orden (en `dynamic` el mejor tramo abre como gancho), efectos por plano
(zoom lento en planos quietos, aceleración en tramos lentos), transición hacia el siguiente plano
(corte seco entre planos movidos, `fadeblack`/`fadewhite` cuando cambia mucho la luz) y etalonaje
del estilo. Estilos: `dynamic`, `vlog`, `cinematic`, `calm` (tabla en la referencia).

La propuesta es un borrador hecho con métricas. Corrígela con lo que has visto en las hojas:
ajusta `start`/`end` para que un gesto quede entero, cambia el orden si la historia lo pide,
quita efectos sin motivo, cambia `fit` a `blur` cuando un plano horizontal no admite recorte.
Cada clip del plan admite `start`, `end`, `speed`, `effects` (lista), `grade`, `transition` y
`transition_duration` (la transición es hacia el clip siguiente). Lista de efectos y etalonajes:
`python3 scripts/tiktok_edit.py render --list-effects`.

## 4. Montar

Forma rápida, con recortes en la propia ruta (`ruta@inicio-fin`, en segundos, ambos opcionales):

```bash
python3 scripts/tiktok_edit.py render "IMG_001.mp4@2-9" "IMG_002.mp4@-6" IMG_003.mp4 \
  -o tiktok.mp4 --transition fade --title "Día 1 en Lisboa" \
  --captions subs.srt --music beat.mp3 --music-volume 0.2
```

Forma con plan JSON (`--plan plan.json`), mejor cuando hay muchos clips o el usuario va a
iterar: permite `start`, `end` y `speed` por clip y todas las opciones globales. El formato está
en la cabecera del script (`python3 scripts/tiktok_edit.py --help`). Guarda el plan junto a los
vídeos para poder rehacer el montaje cambiando una línea.

Opciones que más cambian el resultado:

| Opción | Cuándo usarla |
| --- | --- |
| `--fit cover` (por defecto) | Clips verticales o cuando no importa perder los bordes de un clip horizontal. |
| `--fit blur` | Clips horizontales que hay que ver enteros: fondo desenfocado y el clip centrado, el look habitual de TikTok. |
| `--fit pad` | Bandas negras. Solo si el usuario lo pide. |
| `--transition fade\|dissolve\|slideleft…` | Cortes suaves. 0.3-0.5 s. Cada clip debe durar más del doble de la transición. |
| `--title "texto"` | Rótulo grande arriba durante 3 s (`--title-duration`). Sirve de gancho. |
| `--captions subs.srt` | Subtítulos en la zona segura inferior (por encima de la barra de TikTok). |
| `--music pista.mp3` | Se repite en bucle, se funde al final; `--mute-clips` para quitar el audio original. |
| `--grade cinematic\|punchy\|warm…` | Etalonaje global que unifica clips grabados en momentos distintos. |
| `--crf 18` | Más calidad y peso; 23 para archivos ligeros. |
| `--dry-run` | Imprime el comando ffmpeg sin ejecutarlo, útil para depurar. |

## 5. Comprobar y entregar

El script imprime al final resolución, duración y si hay audio. Saca dos o tres fotogramas del
resultado (`ffmpeg -ss T -i out.mp4 -frames:v 1 f.png`) y míralos: encuadre, texto legible, que el
etalonaje no queme pieles. Entrega el archivo al usuario (con `SendUserFile` si existe) junto con
el `plan.md`, para que sepa qué se eligió y por qué y pueda pedir cambios concretos.
Recomienda subirlo desde la app y añadir allí los sonidos con licencia de TikTok si la música
que ha dado el usuario no tiene derechos.

## Subtítulos

Si el usuario quiere subtítulos y no tiene un `.srt`, escríbelo tú: bloques numerados con
`hh:mm:ss,mmm --> hh:mm:ss,mmm` y una o dos líneas cortas (máx. ~35 caracteres por línea para
que quepan a 1080 px). Los tiempos van referidos al vídeo final ya montado, no a los clips
originales. Para transcribir el audio automáticamente hace falta un modelo de voz (por ejemplo
`pip install faster-whisper`), que no forma parte del skill.

## Detalles de vídeo que conviene saber

- Los vídeos de móvil llevan a menudo un metadato de rotación; ffmpeg lo aplica solo y el
  script ya cuenta con ello, así que no gires nada a mano.
- Clips sin audio se rellenan con silencio para que el montaje no se rompa.
- `speed` por clip usa `setpts`/`atempo`; el audio solo acepta entre 0.5x y 2x.
- Mezclar formatos (25 fps y 30 fps, 720p y 4K) es normal: todo se reescala a 1080x1920 30 fps.
- Si ffmpeg falla, el script imprime el final del error. Los fallos típicos son rutas con
  caracteres raros (renombra el archivo) y transiciones más largas que los clips.

Especificaciones de TikTok en `references/tiktok-specs.md`. Criterios de selección de escenas, ritmo,
transiciones, efectos y etalonaje en `references/direccion-artistica.md`.
