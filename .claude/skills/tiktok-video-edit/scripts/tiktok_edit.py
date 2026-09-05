#!/usr/bin/env python3
"""
tiktok_edit.py — monta un vídeo vertical listo para TikTok a partir de varios
clips grabados con el móvil, usando solo ffmpeg.

Subcomandos:
  probe  <clips...>            Muestra duración, resolución, rotación y audio de cada clip.
  render <clips...> -o out.mp4 Une los clips (en el orden dado) y exporta 1080x1920 H.264/AAC.

Sintaxis de clip para recortar sin editar nada más:  ruta@INICIO-FIN   (segundos, ambos opcionales)
  ejemplo:  IMG_001.mp4@3-11   IMG_002.mp4@-8   IMG_003.mp4@2-

Un plan JSON (--plan plan.json) permite lo mismo con más control:
  {
    "clips": [
      {"path": "IMG_001.mp4", "start": 3, "end": 11, "speed": 1.0},
      {"path": "IMG_002.mp4", "end": 8, "effects": ["zoom_in", "fade_out"], "transition": "fadeblack",
       "transition_duration": 0.5, "grade": "warm"}
    ],
    "grade": "cinematic",
    "title": "Mi primer TikTok", "title_duration": 3,
    "captions": "subs.srt",
    "music": "beat.mp3", "music_volume": 0.25, "mute_clips": false,
    "transition": "fade", "transition_duration": 0.4,
    "fit": "cover", "fps": 30, "output": "tiktok.mp4"
  }
Las opciones de línea de comandos tienen prioridad sobre el plan.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

W, H = 1080, 1920
TIKTOK_MAX_SECONDS = 600  # límite de subida desde la app


# ----------------------------------------------------------------------------- ffmpeg
def find_ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg  # type: ignore
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    sys.exit(
        "No encuentro ffmpeg. Instálalo con `apt-get install ffmpeg`, `brew install ffmpeg` "
        "o, sin permisos de sistema, `pip install imageio-ffmpeg`."
    )


FFMPEG = None


def get_ffmpeg():
    """Resuelve ffmpeg una sola vez; sirve también cuando analyze.py importa este módulo."""
    global FFMPEG
    if FFMPEG is None:
        FFMPEG = find_ffmpeg()
    return FFMPEG


def run(cmd, check=True):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=check)


# ----------------------------------------------------------------------------- probe
DUR_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
VID_RE = re.compile(r"Stream #\d+:\d+.*?: Video: .*?,\s*(\d{2,5})x(\d{2,5})")
AUD_RE = re.compile(r"Stream #\d+:\d+.*?: Audio:")
ROT_RE = re.compile(r"rotation of\s*(-?\d+(?:\.\d+)?)\s*degrees|^\s*rotate\s*:\s*(-?\d+)", re.M)
FPS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*fps")


def probe(path):
    if not os.path.isfile(path):
        sys.exit(f"No existe el archivo: {path}")
    out = run([get_ffmpeg(), "-hide_banner", "-i", path], check=False).stderr
    m = DUR_RE.search(out)
    if not m:
        sys.exit(f"ffmpeg no pudo leer {path}:\n{out[-800:]}")
    duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    v = VID_RE.search(out)
    width, height = (int(v.group(1)), int(v.group(2))) if v else (0, 0)
    r = ROT_RE.search(out)
    rotation = float(r.group(1) or r.group(2)) if r else 0.0
    if abs(rotation) % 180 == 90:  # ffmpeg autorrota: la salida efectiva está girada
        width, height = height, width
    f = FPS_RE.search(out)
    return {
        "path": path,
        "duration": round(duration, 3),
        "width": width,
        "height": height,
        "rotation": rotation,
        "fps": float(f.group(1)) if f else None,
        "has_audio": bool(AUD_RE.search(out)),
        "orientation": "vertical" if height > width else ("horizontal" if width > height else "cuadrado"),
    }


def cmd_probe(args):
    rows = [probe(p.split("@")[0]) for p in args.clips]
    total = sum(r["duration"] for r in rows)
    if args.json:
        print(json.dumps({"clips": rows, "total_duration": round(total, 2)}, ensure_ascii=False, indent=2))
        return
    print(f"{'clip':40} {'dur(s)':>7} {'tamaño':>10} {'rot':>5} {'audio':>5}  orientación")
    for r in rows:
        print(f"{os.path.basename(r['path'])[:40]:40} {r['duration']:7.2f} {r['width']}x{r['height']:<5} "
              f"{int(r['rotation']):5d} {'sí' if r['has_audio'] else 'no':>5}  {r['orientation']}")
    print(f"\nDuración total sin recortar: {total:.1f} s")
    if total > TIKTOK_MAX_SECONDS:
        print(f"AVISO: supera el máximo de TikTok ({TIKTOK_MAX_SECONDS} s). Recorta clips.")
    elif total > 180:
        print("AVISO: más de 3 min. Los vídeos de 15-60 s suelen retener mejor en TikTok.")


# ----------------------------------------------------------------------------- plan
def parse_clip_spec(spec):
    """'ruta@3-11' -> dict. La ruta puede contener '@' si se usa un plan JSON en su lugar."""
    if "@" in spec:
        path, rng = spec.rsplit("@", 1)
        m = re.fullmatch(r"(\d+(?:\.\d+)?)?-?(\d+(?:\.\d+)?)?", rng)
        if m and (m.group(1) or m.group(2)):
            d = {"path": path}
            if m.group(1):
                d["start"] = float(m.group(1))
            if m.group(2):
                d["end"] = float(m.group(2))
            return d
    return {"path": spec}


def build_plan(args):
    plan = {}
    if args.plan:
        with open(args.plan, encoding="utf-8") as fh:
            plan = json.load(fh)
        base = os.path.dirname(os.path.abspath(args.plan))
        for c in plan.get("clips", []):
            if not os.path.isabs(c["path"]):
                c["path"] = os.path.join(base, c["path"])
        for key in ("captions", "music", "output"):
            if plan.get(key) and not os.path.isabs(plan[key]):
                plan[key] = os.path.join(base, plan[key])
    if args.clips:
        plan["clips"] = [parse_clip_spec(s) for s in args.clips]
    for key in ("title", "title_duration", "captions", "music", "music_volume", "transition",
                "transition_duration", "fit", "fps", "output", "crf", "grade"):
        val = getattr(args, key, None)
        if val is not None:
            plan[key] = val
    if args.mute_clips:
        plan["mute_clips"] = True
    plan.setdefault("title_duration", 3.0)
    plan.setdefault("music_volume", 0.25)
    plan.setdefault("transition", "none")
    plan.setdefault("transition_duration", 0.4)
    plan.setdefault("fit", "cover")
    plan.setdefault("fps", 30)
    plan.setdefault("crf", 20)
    plan.setdefault("grade", "none")
    plan.setdefault("mute_clips", False)
    plan.setdefault("output", "tiktok.mp4")
    if not plan.get("clips"):
        sys.exit("Indica al menos un clip (argumentos o --plan).")
    return plan


# ----------------------------------------------------------------------------- subtítulos
def srt_to_events(path):
    """Devuelve [(inicio_s, fin_s, texto)] de un .srt sencillo."""
    with open(path, encoding="utf-8-sig") as fh:
        blocks = re.split(r"\n\s*\n", fh.read().strip())
    ts = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")
    events = []
    for b in blocks:
        lines = b.strip().splitlines()
        for i, line in enumerate(lines):
            m = ts.search(line)
            if m:
                g = [int(x) for x in m.groups()]
                start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
                end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
                text = " ".join(l.strip() for l in lines[i + 1:] if l.strip())
                if text:
                    events.append((start, end, text))
                break
    return events


def ass_time(t):
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def ass_escape(text):
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def write_ass(path, title, title_duration, captions):
    """Un solo archivo ASS con el título (arriba) y los subtítulos (zona segura inferior)."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,DejaVu Sans,88,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,8,80,80,300,1
Style: Caption,DejaVu Sans,64,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,90,90,420,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    if title:
        lines.append(f"Dialogue: 0,{ass_time(0)},{ass_time(title_duration)},Title,,0,0,0,,"
                     f"{{\\fad(200,300)}}{ass_escape(title)}\n")
    for start, end, text in captions:
        lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Caption,,0,0,0,,{ass_escape(text)}\n")
    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(lines)


def filter_path(p):
    """Escapa una ruta para usarla dentro de un filtergraph de ffmpeg."""
    return p.replace("\\", "/").replace(":", "\\:").replace("'", "\\'").replace(",", "\\,")


# ----------------------------------------------------------------------------- render
GRADES = {
    # etalonajes: todos suaves, pensados para material de móvil ya procesado por el teléfono
    "none": "",
    "punchy": "eq=contrast=1.12:saturation=1.25,unsharp=5:5:0.6",
    "cinematic": "curves=m='0/0 0.25/0.21 0.75/0.79 1/1',colorbalance=rs=0.05:bs=-0.05:gh=0.02,"
                 "eq=saturation=0.9,vignette=PI/5",
    "warm": "colortemperature=temperature=5200,eq=saturation=1.1:brightness=0.02",
    "cool": "colortemperature=temperature=8000,eq=saturation=1.05",
    "soft": "eq=contrast=0.95:saturation=0.9:brightness=0.03,gblur=sigma=0.6",
    "bw": "hue=s=0,eq=contrast=1.15",
    "vintage": "curves=vintage,noise=alls=8:allf=t,vignette=PI/4.5",
    "vivid": "vibrance=intensity=0.4,eq=contrast=1.05",
}

EFFECTS = {
    # efectos por clip; {D} = duración del tramo en segundos (se sustituye al construir la cadena)
    "zoom_in": "scale=w='{W}*(1+0.18*t/{D})':h='{H}*(1+0.18*t/{D})':eval=frame,crop={W}:{H}",
    "zoom_in_slow": "scale=w='{W}*(1+0.08*t/{D})':h='{H}*(1+0.08*t/{D})':eval=frame,crop={W}:{H}",
    "zoom_out": "scale=w='{W}*(1.18-0.18*t/{D})':h='{H}*(1.18-0.18*t/{D})':eval=frame,crop={W}:{H}",
    "zoom_out_slow": "scale=w='{W}*(1.08-0.08*t/{D})':h='{H}*(1.08-0.08*t/{D})':eval=frame,crop={W}:{H}",
    "punch": "scale=w='{W}*(1.25-0.25*min(t,0.3)/0.3)':h='{H}*(1.25-0.25*min(t,0.3)/0.3)':eval=frame,crop={W}:{H}",
    "fade_in": "fade=t=in:st=0:d=0.5",
    "fade_out": "fade=t=out:st={D_OUT}:d=0.5",
    "flash_in": "fade=t=in:st=0:d=0.25:color=white",
    "vignette": "vignette=PI/4.5",
    "grain": "noise=alls=10:allf=t",
    "glitch": "rgbashift=rh=6:bh=-6:enable='lt(t,0.25)'",
    "shake": "crop=w={W}-40:h={H}-40:x='20+15*sin(t*23)':y='20+15*cos(t*31)',scale={W}:{H}",
    "mirror": "hflip",
    "bw": GRADES["bw"],
}


def effect_chain(names, duration):
    """Traduce nombres de efectos a filtros. Los efectos se aplican tras encajar el clip a 9:16,
    así todos trabajan sobre 1080x1920 y las expresiones con t empiezan en 0 en cada tramo."""
    out = []
    for name in names or []:
        if name not in EFFECTS:
            sys.exit(f"Efecto desconocido: {name}. Disponibles: {', '.join(sorted(EFFECTS))}")
        out.append(EFFECTS[name].replace("{W}", str(W)).replace("{H}", str(H))
                   .replace("{D_OUT}", f"{max(0.0, duration - 0.5):.3f}").replace("{D}", f"{duration:.3f}"))
    return out


def video_chain(idx, clip, info, fit, fps, duration=None, grade="none"):
    parts = []
    if clip.get("start") is not None or clip.get("end") is not None:
        s = clip.get("start", 0.0)
        e = clip.get("end", info["duration"])
        parts.append(f"trim=start={s}:end={e},setpts=PTS-STARTPTS")
    speed = float(clip.get("speed", 1.0))
    if speed != 1.0:
        parts.append(f"setpts=PTS/{speed}")
    if fit == "blur":
        # fondo desenfocado a pantalla completa + clip entero centrado encima
        parts.append(
            f"split[bg{idx}][fg{idx}];"
            f"[bg{idx}]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:5[bgb{idx}];"
            f"[fg{idx}]scale={W}:{H}:force_original_aspect_ratio=decrease[fgs{idx}];"
            f"[bgb{idx}][fgs{idx}]overlay=(W-w)/2:(H-h)/2"
        )
    elif fit == "pad":
        parts.append(f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black")
    else:  # cover: rellena la pantalla recortando los bordes
        parts.append(f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}")
    parts.append(f"setsar=1,fps={fps}")
    fx = effect_chain(clip.get("effects"), duration or info["duration"])
    if fx:
        parts += fx + ["setsar=1"]  # los zooms reescalan a tamaños impares y alteran el SAR; concat exige SAR igual
    g = clip.get("grade", grade)
    if g not in GRADES:
        sys.exit(f"Etalonaje desconocido: {g}. Disponibles: {', '.join(sorted(GRADES))}")
    if GRADES[g]:
        parts.append(GRADES[g])
    parts.append("format=yuv420p,settb=AVTB")  # xfade exige la misma base de tiempos en sus dos entradas
    return f"[{idx}:v]" + ",".join(parts) + f"[v{idx}]"


def audio_chain(idx, clip, info, mute):
    if mute or not info["has_audio"]:
        return None
    parts = []
    if clip.get("start") is not None or clip.get("end") is not None:
        s = clip.get("start", 0.0)
        e = clip.get("end", info["duration"])
        parts.append(f"atrim=start={s}:end={e},asetpts=PTS-STARTPTS")
    speed = float(clip.get("speed", 1.0))
    if speed != 1.0:
        parts.append(f"atempo={min(max(speed, 0.5), 2.0)}")
    parts.append("aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo")
    return f"[{idx}:a]" + ",".join(parts) + f"[a{idx}]"


def clip_duration(clip, info):
    s = clip.get("start", 0.0) or 0.0
    e = clip.get("end", info["duration"])
    e = min(e, info["duration"])
    if e <= s:
        sys.exit(f"Recorte inválido en {clip['path']}: inicio {s} >= fin {e}")
    return (e - s) / float(clip.get("speed", 1.0))


def cmd_render(args):
    plan = build_plan(args)
    clips = plan["clips"]
    infos = [probe(c["path"]) for c in clips]
    durs = [clip_duration(c, i) for c, i in zip(clips, infos)]
    n = len(clips)
    # transición de cada clip hacia el siguiente: la del clip si la define, si no la global
    trans_list, td_list = [], []
    for i in range(n - 1):
        tr = clips[i].get("transition", plan["transition"])
        d = float(clips[i].get("transition_duration", plan["transition_duration"])) if tr != "none" else 0.0
        trans_list.append(tr)
        td_list.append(d)
    use_xfade = any(t != "none" for t in trans_list)
    for i in range(n - 1):
        if td_list[i] and (durs[i] <= td_list[i] * 2 or durs[i + 1] <= td_list[i] * 2):
            sys.exit(f"El clip {i + 1} o el {i + 2} dura menos del doble de la transición de {td_list[i]}s. "
                     "Baja la duración de la transición o alarga el tramo.")
    total = sum(durs) - sum(td_list)
    trans = "mixta" if len(set(trans_list)) > 1 else (trans_list[0] if trans_list else "none")
    if total > TIKTOK_MAX_SECONDS:
        sys.exit(f"El montaje dura {total:.0f}s y TikTok admite {TIKTOK_MAX_SECONDS}s como máximo. Recorta clips.")

    mute = bool(plan["mute_clips"]) and bool(plan.get("music"))
    fc = []
    inputs = []
    for i, (c, info) in enumerate(zip(clips, infos)):
        inputs += ["-i", c["path"]]
        fc.append(video_chain(i, c, info, plan["fit"], plan["fps"], durs[i], plan["grade"]))
    # audio de los clips: silencio para los mudos, así concat/acrossfade siempre tienen entrada.
    # Con --mute-clips y música no se toca el audio original: solo se usa la pista de música.
    if not mute:
        for i, (c, info) in enumerate(zip(clips, infos)):
            ch = audio_chain(i, c, info, mute)
            if ch:
                fc.append(ch)
            else:
                fc.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{durs[i]:.3f},asetpts=PTS-STARTPTS[a{i}]")

    alabel = None
    if n == 1:
        vlabel = "[v0]"
        alabel = None if mute else "[a0]"
    elif use_xfade:
        # xfade admite duration=0 como corte seco, así se mezclan cortes y transiciones en una cadena
        offset = 0.0
        prev_v, prev_a = "[v0]", "[a0]"
        for i in range(1, n):
            tr, td = trans_list[i - 1], td_list[i - 1]
            offset += durs[i - 1] - td
            if td:
                fc.append(f"{prev_v}[v{i}]xfade=transition={tr}:duration={td}:offset={offset:.3f}[xv{i}]")
                if not mute:
                    fc.append(f"{prev_a}[a{i}]acrossfade=d={td}:c1=tri:c2=tri[xa{i}]")
            else:
                fc.append(f"{prev_v}[v{i}]concat=n=2:v=1:a=0,settb=AVTB[xv{i}]")
                if not mute:
                    fc.append(f"{prev_a}[a{i}]concat=n=2:v=0:a=1[xa{i}]")
            prev_v = f"[xv{i}]"
            if not mute:
                prev_a = f"[xa{i}]"
        vlabel = prev_v
        alabel = None if mute else prev_a
    elif mute:
        fc.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[cv]")
        vlabel = "[cv]"
    else:
        fc.append("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[cv][ca]")
        vlabel, alabel = "[cv]", "[ca]"

    tmpdir = tempfile.mkdtemp(prefix="tiktok_edit_")
    captions = srt_to_events(plan["captions"]) if plan.get("captions") else []
    if plan.get("title") or captions:
        ass_path = os.path.join(tmpdir, "overlay.ass")
        write_ass(ass_path, plan.get("title"), float(plan["title_duration"]), captions)
        fc.append(f"{vlabel}ass=filename='{filter_path(ass_path)}'[vt]")
        vlabel = "[vt]"

    if plan.get("music"):
        m_idx = n
        inputs += ["-stream_loop", "-1", "-i", plan["music"]]
        fade = min(2.0, total / 4)
        fc.append(f"[{m_idx}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
                  f"atrim=0:{total:.3f},asetpts=PTS-STARTPTS,"
                  f"afade=t=out:st={max(0.0, total - fade):.3f}:d={fade:.3f},"
                  f"volume={float(plan['music_volume'])}[music]")
        if mute:
            alabel_final = "[music]"
        else:
            fc.append(f"{alabel}[music]amix=inputs=2:duration=first:normalize=0[mixed]")
            alabel_final = "[mixed]"
    else:
        alabel_final = alabel
    fc.append(f"{alabel_final}loudnorm=I=-14:TP=-1.5:LRA=11[aout]")

    out = plan["output"]
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    cmd = [get_ffmpeg(), "-hide_banner", "-y", *inputs,
           "-filter_complex", ";".join(fc),
           "-map", vlabel, "-map", "[aout]",
           "-c:v", "libx264", "-preset", "medium", "-crf", str(plan["crf"]),
           "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p", "-r", str(plan["fps"]),
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-movflags", "+faststart", "-t", f"{total:.3f}", out]
    if args.dry_run:
        import shlex
        print(shlex.join(cmd))
        return
    print(f"Montando {n} clip(s), {total:.1f}s, transición={trans}, ajuste={plan['fit']} -> {out}")
    res = run(cmd, check=False)
    if res.returncode != 0:
        # el filtergraph es enorme: enseña solo las líneas que explican el fallo
        key = re.compile(r"error|invalid|failed|not match|unable|no such|cannot|unknown|option", re.I)
        lines = [l for l in res.stderr.splitlines() if key.search(l) and not l.startswith("Failed to set value")]
        sys.exit("ffmpeg falló:\n" + ("\n".join(lines[-15:]) if lines else res.stderr[-2000:]))
    info = probe(out)
    print(f"OK: {out}  {info['width']}x{info['height']}  {info['duration']:.2f}s  audio={'sí' if info['has_audio'] else 'no'}")
    if total > 180:
        print("Nota: el vídeo supera 3 min; en TikTok suelen funcionar mejor los de menos de 60 s.")


# ----------------------------------------------------------------------------- cli
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("probe", help="inspecciona los clips")
    p.add_argument("clips", nargs="+")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_probe)

    r = sub.add_parser("render", help="monta y exporta el vídeo")
    r.add_argument("clips", nargs="*", help="clips en orden; admite ruta@inicio-fin")
    r.add_argument("--plan", help="plan JSON de montaje")
    r.add_argument("-o", "--output", help="archivo de salida .mp4")
    r.add_argument("--title", help="texto grande al inicio")
    r.add_argument("--title-duration", type=float, dest="title_duration")
    r.add_argument("--captions", help="subtítulos .srt (se dibujan en la zona segura inferior)")
    r.add_argument("--music", help="pista de audio de fondo (se repite y se funde al final)")
    r.add_argument("--music-volume", type=float, dest="music_volume", help="0-1, por defecto 0.25")
    r.add_argument("--mute-clips", action="store_true", dest="mute_clips", help="quita el audio original si hay música")
    r.add_argument("--transition", choices=["none", "fade", "fadeblack", "fadewhite", "wipeleft", "wiperight",
                                            "slideleft", "slideright", "slideup", "slidedown", "dissolve",
                                            "circleopen", "smoothleft", "smoothright"])
    r.add_argument("--transition-duration", type=float, dest="transition_duration")
    r.add_argument("--fit", choices=["cover", "blur", "pad"], help="cómo encajar clips horizontales en 9:16")
    r.add_argument("--grade", choices=sorted(GRADES), help="etalonaje global (por clip: campo grade en el plan)")
    r.add_argument("--list-effects", action="store_true", help="lista efectos y etalonajes disponibles")
    r.add_argument("--fps", type=int)
    r.add_argument("--crf", type=int, help="calidad H.264 (18 mejor, 23 más ligero)")
    r.add_argument("--dry-run", action="store_true", help="solo imprime el comando ffmpeg")
    r.set_defaults(func=cmd_render)

    args = ap.parse_args()
    if getattr(args, "list_effects", False):
        print("Efectos por clip (campo \"effects\"): " + ", ".join(sorted(EFFECTS)))
        print("Etalonajes (--grade o campo \"grade\"): " + ", ".join(sorted(GRADES)))
        return
    get_ffmpeg()
    args.func(args)


if __name__ == "__main__":
    main()
