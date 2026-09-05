# Dirección artística para vídeo corto vertical

Guía para decidir qué escenas usar, en qué orden, con qué efectos y con qué transiciones.
Los números de `analyze` orientan; la decisión se toma mirando las hojas de contactos.

## 1. Cómo leer el material

Para cada clip, mirando su hoja de contactos y su resumen, anota:

- **Qué pasa**: acción, persona, lugar, objeto. ¿Hay un momento que sorprenda o emocione?
- **Encuadre**: plano general / medio / detalle. Horizontal o vertical. ¿Dónde está el sujeto?
  Si está a un lado, `fit: cover` lo cortará; usa `blur` o recorta el tramo donde esté centrado.
- **Luz y color**: oscuro/luminoso, cálido/frío, apagado/colorido. Dos planos seguidos con luz muy
  distinta se pegan mal: sepáralos con `fadeblack`/`fadewhite` o unifícalos con un etalonaje.
- **Movimiento**: cámara quieta, paneo, andando, acción rápida. Marca la dirección del movimiento.
- **Sonido**: ¿hay voz que hay que respetar (no cortar frases)? ¿ruido de viento (mejor `mute_clips`
  y música)? ¿un sonido puntual que puede marcar un corte?
- **Basura**: arranques y finales (la mano acercándose al botón), enfoques perdidos, negros,
  temblores. `flags` y `best_segments` ya los evitan; confírmalo en la hoja.

## 2. Estructura: gancho, desarrollo, remate

- **Gancho (0-2 s)**: el plano más llamativo o el que plantea una pregunta. Puede ser el clímax
  adelantado. Si hace falta, un rótulo (`title`) de 3-5 palabras que prometa algo.
- **Desarrollo**: el orden cronológico suele ser el más claro. Alterna escalas (general → detalle)
  y evita dos planos casi iguales seguidos; si son iguales, quédate con el mejor.
- **Remate**: el momento de pago (el resultado, la reacción, el paisaje al final del camino).
  Termina en el punto alto, sin cola. Un final abrupto favorece que el vídeo se repita en bucle.

Duración: 15-35 s para la mayoría de piezas; hasta 60 s si hay historia. Cada plano entre 1.5 y 6 s;
en cuanto el espectador ya lo ha "leído", corta.

## 3. Ritmo y estilos

| Estilo | Plano | Corte típico | Efectos | Etalonaje | Cuándo |
| --- | --- | --- | --- | --- | --- |
| `dynamic` | 1.5-3.5 s | seco (`none`); `hblur` 0.45 s solo para disimular jump cuts | `punch`, `zoom_in`, x1.25 en planos lentos sin voz | `punchy` | deporte, viajes con acción, humor, "day in my life" rápido |
| `vlog` | 2.5-5 s | seco; `fade` 0.5 s entre planos quietos | `zoom_in_slow` en planos quietos | `warm` | hablar a cámara, comida, planes con amigos |
| `cinematic` | 3-6 s | `fade` 0.7 s; `fadeblack` entre bloques | `zoom_in_slow`, `fade_in`/`fade_out` en los extremos | `cinematic` | paisajes, arquitectura, atardeceres, piezas emotivas |
| `calm` | 4-6 s | `fade` 1 s | `zoom_out_slow` | `soft` | naturaleza, ASMR, meditación, lectura |

Si hay música, intenta que los cortes caigan en el pulso (escúchala o mira su forma de onda: un
tema a 120 bpm tiene un golpe cada 0.5 s; cortar cada 2 o 4 s cae en compás).

## 4. Transiciones: que no se noten

Una transición se ve natural cuando el espectador no la percibe como tal: solo nota que la
historia avanza. Las reglas, por orden de importancia:

1. **Corte seco (`none`) por defecto.** Es el 80-90 % de cualquier montaje profesional. Entre dos
   planos de la misma escena, entre dos planos con movimiento, o cuando el ritmo es rápido, corte.
2. **Corta en el momento adecuado.** El corte se disimula si el plano saliente termina en un
   instante calmado (fin de un gesto, cámara casi quieta) o justo en mitad de una acción que el
   plano entrante continúa ("cortar en la acción"). `analyze` ya prefiere tramos que entran y salen
   en calma; al ajustar `start`/`end` a mano, evita cortar a mitad de una palabra o de un gesto.
3. **Cuando hay que suavizar, encadenado (`fade`).** Es el cross-dissolve clásico: paso del tiempo
   o cambio de lugar. 0.5-0.7 s. En ffmpeg, la transición llamada `dissolve` NO es esto: es un
   fundido por píxeles que parece interferencia de televisión. No la uses.
4. **Salto dentro del mismo plano (jump cut): `hblur`.** Cuando quitas un trozo del medio de una
   toma, el corte seco produce un salto visible. Un desenfoque cruzado de 0.4-0.5 s lo disimula
   mejor que un encadenado. También sirve entre dos encuadres parecidos de escenas distintas.
5. **Dos planos quietos seguidos**: un `fade` o `hblur` breve (0.4-0.5 s) evita que el corte
   parezca un error. Dos planos movidos: corte seco, el movimiento ya los une.
6. **Cambios de luz grandes** (interior oscuro → exterior a pleno sol): `fadeblack` 0.7 s cierra
   un bloque y descansa el ojo; `fadewhite` 0.4 s solo hacia un plano luminoso y en piezas
   dinámicas, porque imita un destello de cámara.
7. **Duración proporcional.** Nunca más de un tercio del plano más corto que une (el render la
   recorta solo). Transiciones largas en planos cortos se comen el plano y se notan.
8. **Una sola familia por vídeo.** Si usas encadenados, que sean todos iguales de largos. Mezclar
   barridos, círculos y encadenados grita "plantilla de app".
9. **El audio manda.** Un corte de vídeo perfecto se nota si el sonido salta. El render iguala el
   volumen medio entre clips, pone microfundidos de 20 ms en cada corte seco (sin chasquidos) y
   cruza el audio con curvas de potencia constante en los encadenados. Si el ambiente de dos clips
   es muy distinto (viento vs. interior), mejor `mute_clips` y música, o cortar en un golpe de la
   música.
10. **Dirección del movimiento.** Si un plano panea a la izquierda y el siguiente empieza con el
    sujeto entrando por la derecha, el corte fluye. `smoothleft`/`smoothright` solo tienen sentido
    si siguen esa dirección; en sentido contrario chirrían.

Transiciones que casi nunca se ven naturales y quedan fuera de las propuestas automáticas:
`dissolve`, `pixelize`, `wipe*`, `slide*`, `circle*`, `radial`, `squeeze*`, `*wind`. `zoomin`
(zoom rápido hacia el siguiente plano) se tolera una vez en piezas muy dinámicas.

## 5. Efectos y cuándo usarlos

| Efecto | Para qué |
| --- | --- |
| `zoom_in`, `zoom_in_slow` | Dar vida a un plano fijo; dirigir la mirada al centro. El lento es casi siempre mejor. |
| `zoom_out`, `zoom_out_slow` | Revelar el contexto; buen final. |
| `punch` | Golpe de zoom en el primer cuarto de segundo; puntúa un corte en el pulso de la música. |
| `fade_in` / `fade_out` | Solo en el primer y último plano, o antes/después de un `fadeblack`. |
| `flash_in` | Entrada con destello; combina con corte seco en vídeos dinámicos. |
| `shake` | Impacto, susto, risa. 1-2 s como mucho. |
| `glitch` | Cambio de tema o "error"; 0.25 s. |
| `grain`, `vignette` | Textura cine/vintage. Discretos, en todo el vídeo o en nada. |
| `bw` (efecto o etalonaje) | Recuerdo, contraste "antes/después", tono serio. |
| `mirror` | Corregir dirección de mirada/movimiento para que dos planos "se miren". |
| `speed` (campo por clip) | x1.25-x2 acorta paseos y preparaciones; x0.5-0.75 subraya un gesto (el audio se estira, mejor con música). |

Regla: un efecto debe tener un porqué que puedas escribir en una línea. Si no lo tienes, quítalo.
Usa como máximo dos efectos por plano y mantén la misma familia en todo el vídeo.

## 6. Etalonaje (grade)

Aplica uno global para unificar clips grabados en momentos distintos; por clip solo para corregir
uno que desentone (por ejemplo `warm` a un clip azulado de interior).

- `punchy`: contraste y saturación; redes, deporte, comida.
- `cinematic`: negros levantados, sombras frías, luces cálidas, viñeta suave.
- `warm` / `cool`: corrige temperatura; `warm` para atardeceres y pieles, `cool` para nieve, agua, tecnología.
- `soft`: bajo contraste y desenfoque mínimo; calma, belleza.
- `vintage`: curvas retro, grano, viñeta.
- `vivid`: sube solo los colores apagados; paisajes.
- `bw`: blanco y negro con contraste.

## 7. Texto

- Título: 3-6 palabras, primeros 3 s, dentro de la zona segura (el script ya lo coloca).
- Subtítulos si hay voz; frases cortas, sincronizadas con el vídeo montado.
- No pongas texto sobre caras ni sobre el sujeto principal.

## 8. Checklist antes de renderizar

1. ¿El primer plano engancha en 2 s?
2. ¿Hay algún plano que no aporte nada nuevo? Fuera.
3. ¿Cada transición que no sea corte seco tiene motivo (jump cut, salto de luz, paso de tiempo) y dura menos de un tercio del plano?
3b. ¿El audio no salta entre planos (volumen parecido, sin chasquidos, sin frases cortadas)?
4. ¿Los efectos son de la misma familia y cada uno tiene un porqué?
5. ¿Luz y color son coherentes o el etalonaje los unifica?
6. ¿La duración total está entre 15 y 60 s?
7. ¿El último plano cierra o deja ganas de repetir?
