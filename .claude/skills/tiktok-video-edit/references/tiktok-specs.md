# Especificaciones de TikTok (y Reels / Shorts)

## Archivo de subida
- Relación 9:16, 1080x1920 px. TikTok admite otras, pero las recorta o deja bandas.
- MP4 o MOV. H.264 (perfil high) + AAC. Sin HDR ni 10 bits: usar `yuv420p`.
- 30 fps (acepta hasta 60). Mantener constante.
- Duración: desde la app hasta 10 min; desde web hasta 60 min. Los vídeos de 15-60 s
  suelen tener mejor retención. Reels admite hasta 90 s (3 min en algunos países); Shorts hasta 3 min.
- Peso: máximo 287 MB en iOS y 72 MB en Android para subir desde la app. Con CRF 20-23
  un minuto a 1080p pesa entre 15 y 40 MB.
- Audio: estéreo 48 kHz, 128-192 kbps. Normalizar a unos -14 LUFS para que no suene bajo.

## Zonas seguras (para texto y subtítulos)
Sobre un lienzo de 1080x1920:
- Arriba: deja libres unos 250 px (barra de estado, "Para ti").
- Abajo: deja libres unos 400-450 px (descripción, nombre de usuario, música).
- Derecha: deja libres unos 130-150 px (botones de me gusta, comentarios, compartir).
El script coloca el título a 300 px del borde superior y los subtítulos a 420 px del inferior
con márgenes laterales de 90 px, dentro de esas zonas.

## Contenido que retiene
- Gancho en los 2 primeros segundos: empezar con la acción o con un rótulo que plantee algo.
- Cortes cada 2-4 s; los planos largos pierden espectadores.
- Subtítulos siempre: gran parte se ve sin sonido.
- Música con licencia: mejor añadirla en la app de TikTok (sonidos comerciales) que en el
  archivo, salvo que sea propia o libre de derechos.
- Terminar sin fundido largo; el bucle rápido ayuda a que se repita.

## Enlaces oficiales
- https://support.tiktok.com/es/using-tiktok/creating-videos
- https://ads.tiktok.com/help/article/video-ads-specifications
