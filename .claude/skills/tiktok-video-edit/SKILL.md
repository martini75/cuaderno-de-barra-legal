---
name: tiktok-video-edit
description: Monta y exporta vídeos verticales listos para TikTok (también Reels y Shorts) a partir de varios clips grabados con el móvil, usando ffmpeg desde la línea de comandos. Une clips en orden, recorta, convierte a 9:16 (1080x1920), añade transiciones, título, subtítulos .srt y música de fondo, y exporta H.264/AAC con el formato que TikTok acepta. Usa este skill SIEMPRE que el usuario quiera editar, montar, unir, recortar, poner música o subtítulos, o "preparar para subir" vídeos cortos para TikTok, Instagram Reels o YouTube Shorts, aunque no diga "ffmpeg" ni "skill": frases como "tengo varios vídeos del móvil y quiero hacer un TikTok", "júntame estos clips en vertical", "ponle música y subtítulos a este vídeo" o "recorta estos vídeos para Reels" deben activarlo.
---

# Edición de vídeo para TikTok con ffmpeg

Todo el trabajo lo hace `scripts/tiktok_edit.py`, un script de Python que solo necesita ffmpeg.
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

## 2. Inspeccionar los clips antes de decidir nada

```bash
python3 scripts/tiktok_edit.py probe IMG_001.mp4 IMG_002.mp4 IMG_003.mp4
```

Muestra duración, tamaño real (ya corregida la rotación del móvil), si tiene audio y la
orientación. Con esto se decide el orden, qué recortar y cómo encajar los clips horizontales.
Piensa en el resultado: en TikTok funcionan mejor los vídeos de 15 a 60 s con un gancho en los
primeros 2 segundos, así que propón recortes al usuario si la suma es muy larga. El límite duro
de subida es 10 minutos y el script se niega a superarlo.

## 3. Montar

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
| `--crf 18` | Más calidad y peso; 23 para archivos ligeros. |
| `--dry-run` | Imprime el comando ffmpeg sin ejecutarlo, útil para depurar. |

## 4. Comprobar y entregar

El script imprime al final resolución, duración y si hay audio. Comprueba que es 1080x1920, que
la duración es la esperada y entrega el archivo al usuario (con `SendUserFile` si existe).
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

Especificaciones de TikTok y consejos de contenido en `references/tiktok-specs.md`.
