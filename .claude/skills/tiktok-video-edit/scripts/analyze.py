#!/usr/bin/env python3
"""
analyze.py — análisis del material bruto y propuesta de montaje.

  analyze <clips...> -o carpeta_analisis [--interval N]
      Para cada clip genera:
        · métricas por segundo: movimiento, nitidez, luz, saturación, tono, volumen
        · cortes de escena detectados, tramos negros/congelados/mudos
        · una hoja de contactos (contact_<clip>.jpg) con la hora de cada fotograma,
          para MIRAR el material antes de decidir nada
      Y escribe analysis.json con todo, más los "mejores tramos" de cada clip.

  suggest carpeta_analisis/analysis.json -o plan.json [--target 30] [--style dynamic|cinematic|vlog|calm]
      Convierte el análisis en un plan de montaje (el JSON que entiende tiktok_edit.py render):
      qué tramo de cada clip usar, en qué orden, con qué efecto y qué transición hacia el siguiente.
      Escribe también plan.md con la justificación de cada decisión para revisarla y cambiarla.

Los números orientan; la decisión artística final se toma mirando las hojas de contactos.
"""
import argparse
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tiktok_edit import get_ffmpeg as find_ffmpeg, probe, run, filter_path  # noqa: E402

import tiktok_edit  # noqa: E402

# ----------------------------------------------------------------------------- parsing
FRAME_RE = re.compile(r"^frame:\d+\s+pts:\S+\s+pts_time:(\S+)")


def parse_metadata_file(path):
    """metadata=print escribe bloques 'frame: … pts_time:T' seguidos de 'clave=valor'."""
    rows = []
    cur = None
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = FRAME_RE.match(line)
            if m:
                cur = {"t": float(m.group(1))}
                rows.append(cur)
            elif cur is not None and "=" in line:
                k, v = line.strip().split("=", 1)
                try:
                    val = float(v)
                    # astats devuelve -inf en silencio absoluto; un valor finito mantiene las medias sanas
                    if math.isinf(val) or math.isnan(val):
                        val = -90.0 if val < 0 else 90.0
                    cur[k] = val
                except ValueError:
                    cur[k] = v
    return rows


def bucket(rows, key, dur):
    """Media por segundo de una clave. Devuelve lista de longitud ceil(dur)."""
    n = max(1, math.ceil(dur))
    acc = [[] for _ in range(n)]
    for r in rows:
        if key in r and isinstance(r[key], float):
            i = min(n - 1, int(r["t"]))
            acc[i].append(r[key])
    out = []
    for vals in acc:
        out.append(round(sum(vals) / len(vals), 2) if vals else None)
    # rellena huecos con el vecino anterior
    last = None
    for i, v in enumerate(out):
        if v is None:
            out[i] = last
        else:
            last = v
    return out


# ----------------------------------------------------------------------------- análisis por clip
def analyze_clip(ffmpeg, path, workdir, interval):
    info = probe(path)
    dur = info["duration"]
    base = os.path.splitext(os.path.basename(path))[0]
    files = {k: os.path.join(workdir, f"{base}.{k}.txt") for k in ("stats", "edges", "scenes", "audio")}
    for f in files.values():
        if os.path.exists(f):
            os.remove(f)

    # todas las ramas se mapean al muxer null: nullsink dentro de filter_complex hace fallar a ffmpeg 7.0
    fc = [
        "[0:v]scale=320:-2:flags=fast_bilinear,split=2[full][slow]",
        "[slow]fps=2,split=2[s1][s2]",
        f"[s1]signalstats,metadata=print:file='{filter_path(files['stats'])}'[o1]",
        f"[s2]format=gray,edgedetect=low=0.08:high=0.2,signalstats,"
        f"metadata=print:key=lavfi.signalstats.YAVG:file='{filter_path(files['edges'])}'[o2]",
        # gte(scene,0) deja pasar todos los fotogramas (una rama vacía rompe ffmpeg) y anota su scene_score
        f"[full]select='gte(scene,0)',metadata=print:key=lavfi.scene_score:file='{filter_path(files['scenes'])}'[o3]",
    ]
    maps = ["-map", "[o1]", "-map", "[o2]", "-map", "[o3]"]
    if info["has_audio"]:
        fc.append("[0:a]aformat=sample_rates=48000:channel_layouts=mono,asetnsamples=48000,"
                  "astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level:"
                  f"file='{filter_path(files['audio'])}'[o4]")
        maps += ["-map", "[o4]"]
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", path, "-filter_complex", ";".join(fc),
           *maps, "-f", "null", "-"]
    res = run(cmd, check=False)
    if res.returncode != 0:
        sys.exit(f"ffmpeg falló analizando {path}:\n{res.stderr[-2000:]}")

    stats = parse_metadata_file(files["stats"])
    edges = parse_metadata_file(files["edges"])
    scenes = parse_metadata_file(files["scenes"])
    audio = parse_metadata_file(files["audio"]) if info["has_audio"] else []

    per_sec = {
        "brightness": bucket(stats, "lavfi.signalstats.YAVG", dur),      # 0-255
        "motion": bucket(stats, "lavfi.signalstats.YDIF", dur),          # diferencia entre fotogramas
        "saturation": bucket(stats, "lavfi.signalstats.SATAVG", dur),    # 0-~180
        "hue": bucket(stats, "lavfi.signalstats.HUEMED", dur),           # 0-360
        "sharpness": bucket(edges, "lavfi.signalstats.YAVG", dur),       # energía de bordes
        "loudness": bucket(audio, "lavfi.astats.Overall.RMS_level", dur) if audio else None,  # dBFS
    }
    cuts = [round(r["t"], 2) for r in scenes
            if r["t"] > 0.3 and isinstance(r.get("lavfi.scene_score"), float) and r["lavfi.scene_score"] >= 0.3]

    n = len(per_sec["brightness"])
    flags = []
    for i in range(n):
        b = per_sec["brightness"][i] or 0
        m = per_sec["motion"][i] or 0
        l = per_sec["loudness"][i] if per_sec["loudness"] else None
        f = []
        if b < 25:
            f.append("negro")
        elif b > 230:
            f.append("quemado")
        if m < 0.4:
            f.append("estático")
        if l is not None and l < -50:
            f.append("mudo")
        flags.append(f)

    scores = score_seconds(per_sec, flags)
    segments = best_segments(scores, cuts, dur, flags)
    sheet = contact_sheet(ffmpeg, path, workdir, base, dur, interval)

    return {
        **info,
        "contact_sheet": sheet,
        "sheet_interval": interval,
        "scene_cuts": cuts,
        "per_second": per_sec,
        "flags": flags,
        "scores": scores,
        "best_segments": segments,
        "summary": summarize(per_sec, flags, cuts, dur),
    }


def zscores(vals):
    xs = [v for v in vals if v is not None]
    if len(xs) < 2:
        return [0.0 for _ in vals]
    mean = sum(xs) / len(xs)
    sd = (sum((x - mean) ** 2 for x in xs) / len(xs)) ** 0.5 or 1.0
    return [((v - mean) / sd if v is not None else 0.0) for v in vals]


def score_seconds(per_sec, flags):
    """Puntuación 0-10 por segundo: interés visual y sonoro, penalizando material inutilizable."""
    zm = zscores(per_sec["motion"])
    zs = zscores(per_sec["sharpness"])
    zsat = zscores(per_sec["saturation"])
    zl = zscores(per_sec["loudness"]) if per_sec["loudness"] else [0.0] * len(zm)
    out = []
    for i in range(len(zm)):
        s = 5 + 1.2 * zm[i] + 1.5 * zs[i] + 0.6 * zsat[i] + 0.8 * zl[i]
        if "negro" in flags[i] or "quemado" in flags[i]:
            s -= 6
        if "estático" in flags[i]:
            s -= 1.5
        out.append(round(max(0.0, min(10.0, s)), 2))
    return out


def best_segments(scores, cuts, dur, flags, min_len=2.0, max_len=6.0):
    """Tramos candidatos: ventanas de 2-6 s con mejor media, sin cruzar cortes de escena
    ni segundos negros/quemados. Devuelve hasta 4 por clip, ordenados por puntuación."""
    n = len(scores)
    boundaries = sorted({0.0, float(dur)} | {c for c in cuts})
    windows = []
    for a, b in zip(boundaries, boundaries[1:]):
        lo, hi = int(math.floor(a)), int(math.ceil(b))
        for length in (6, 5, 4, 3, 2):
            for start in range(lo, hi - length + 1):
                sl = scores[start:start + length]
                if any(("negro" in flags[k] or "quemado" in flags[k]) for k in range(start, start + length)):
                    continue
                if len(sl) < length:
                    continue
                windows.append((sum(sl) / length, start, start + length, a))
    windows.sort(key=lambda w: (-w[0], w[1]))
    chosen = []
    for sc, s, e, shot_start in windows:
        if any(not (e <= cs or s >= ce) for _, cs, ce in chosen):
            continue
        chosen.append((sc, s, e))
        if len(chosen) == 4:
            break
    return [{"start": float(s), "end": float(min(e, dur)), "score": round(sc, 2)} for sc, s, e in chosen]


def summarize(per_sec, flags, cuts, dur):
    def avg(xs):
        xs = [x for x in xs if x is not None]
        return round(sum(xs) / len(xs), 1) if xs else None
    b = avg(per_sec["brightness"]) or 0
    m = avg(per_sec["motion"]) or 0
    sat = avg(per_sec["saturation"]) or 0
    hue = avg(per_sec["hue"])
    light = "oscuro" if b < 70 else ("luminoso" if b > 160 else "medio")
    move = "estático" if m < 0.8 else ("tranquilo" if m < 2.5 else ("movido" if m < 6 else "muy movido"))
    color = "apagado" if sat < 25 else ("colorido" if sat > 60 else "natural")
    warm = None
    if hue is not None:
        warm = "cálido" if (hue < 60 or hue > 300) else ("frío" if 160 < hue < 280 else "neutro/verdoso")
    usable = sum(1 for f in flags if not ({"negro", "quemado"} & set(f)))
    return {
        "light": light, "movement": move, "color": color, "temperature": warm,
        "usable_seconds": usable, "shots": len(cuts) + 1,
        "text": f"{light}, {move}, {color}" + (f", {warm}" if warm else "") +
                f"; {len(cuts) + 1} plano(s), {usable}/{math.ceil(dur)} s aprovechables",
    }


def contact_sheet(ffmpeg, path, workdir, base, dur, interval):
    """Hoja de contactos: un fotograma cada `interval` s, con la hora rotulada, en rejilla de 5."""
    tiles = max(1, math.ceil(dur / interval))
    cols = 5 if tiles >= 5 else tiles
    rows = math.ceil(tiles / cols)
    tw, th = 216, 384  # miniatura vertical; los clips horizontales se ven enteros con bandas
    ass_path = os.path.join(workdir, f"{base}.sheet.ass")
    with open(ass_path, "w", encoding="utf-8") as fh:
        fh.write(f"[Script Info]\nScriptType: v4.00+\nPlayResX: {tw}\nPlayResY: {th}\n\n[V4+ Styles]\n"
                 "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
                 "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
                 "Alignment, MarginL, MarginR, MarginV, Encoding\n"
                 "Style: T,DejaVu Sans,22,&H0000FFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,2,0,7,6,6,4,1\n\n"
                 "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
        for k in range(tiles):
            t0 = k * interval
            fh.write(f"Dialogue: 0,{tiktok_edit.ass_time(t0)},{tiktok_edit.ass_time(t0 + interval)},T,,0,0,0,,{t0:g}s\n")
    out = os.path.join(workdir, f"contact_{base}.jpg")
    vf = (f"fps=1/{interval},scale={tw}:{th}:force_original_aspect_ratio=decrease,"
          f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:black,ass=filename='{filter_path(ass_path)}',"
          f"tile={cols}x{rows}:padding=4:margin=4:color=0x202020")
    res = run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", path, "-vf", vf,
               "-frames:v", "1", "-q:v", "3", out], check=False)
    if res.returncode != 0:
        print(f"AVISO: no se pudo generar la hoja de contactos de {path}: {res.stderr[-300:]}")
        return None
    return out


# ----------------------------------------------------------------------------- comandos
def cmd_analyze(args):
    ffmpeg = find_ffmpeg()
    os.makedirs(args.output, exist_ok=True)
    clips = []
    for p in args.clips:
        info = probe(p)
        interval = args.interval or max(1, math.ceil(info["duration"] / 40))
        print(f"Analizando {os.path.basename(p)} ({info['duration']:.1f}s)…", flush=True)
        clips.append(analyze_clip(ffmpeg, os.path.abspath(p), args.output, interval))
    result = {"clips": clips, "total_duration": round(sum(c["duration"] for c in clips), 2)}
    out = os.path.join(args.output, "analysis.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)
    print(f"\n{'clip':28} {'dur':>6}  resumen")
    for c in clips:
        print(f"{os.path.basename(c['path'])[:28]:28} {c['duration']:6.1f}  {c['summary']['text']}")
        best = ", ".join(f"{s['start']:g}-{s['end']:g}s ({s['score']})" for s in c["best_segments"][:3])
        print(f"{'':28} {'':6}  mejores tramos: {best or 'ninguno aprovechable'}")
        if c["scene_cuts"]:
            print(f"{'':28} {'':6}  cortes de escena en: {', '.join(f'{t:g}s' for t in c['scene_cuts'][:8])}")
    print(f"\nAnálisis: {out}")
    print("Hojas de contactos (míralas antes de decidir): " +
          ", ".join(os.path.basename(c["contact_sheet"]) for c in clips if c["contact_sheet"]))


STYLES = {
    # ritmo (s por plano), transición por defecto, transición para saltos de luz, efectos, etalonaje
    "dynamic":   {"shot": (1.5, 3.5), "transition": "none", "td": 0.25, "alt": "fadewhite",
                  "grade": "punchy", "zoom": "zoom_in", "speed_slow": 1.25},
    "cinematic": {"shot": (3.0, 6.0), "transition": "dissolve", "td": 0.6, "alt": "fadeblack",
                  "grade": "cinematic", "zoom": "zoom_in_slow", "speed_slow": 1.0},
    "vlog":      {"shot": (2.5, 5.0), "transition": "fade", "td": 0.35, "alt": "fadeblack",
                  "grade": "warm", "zoom": "zoom_in_slow", "speed_slow": 1.0},
    "calm":      {"shot": (4.0, 6.0), "transition": "dissolve", "td": 0.8, "alt": "fadeblack",
                  "grade": "soft", "zoom": "zoom_out_slow", "speed_slow": 1.0},
}


def cmd_suggest(args):
    with open(args.analysis, encoding="utf-8") as fh:
        data = json.load(fh)
    style = STYLES[args.style]
    clips = data["clips"]
    lo, hi = style["shot"]
    target = float(args.target)

    # 1) candidatos: mejores tramos de cada clip, recortados al ritmo del estilo
    cands = []
    for ci, c in enumerate(clips):
        for si, seg in enumerate(c["best_segments"]):
            length = min(hi, seg["end"] - seg["start"])
            if length < min(lo, 1.5):
                continue
            # centra el tramo en su parte mejor puntuada
            start = seg["start"]
            cands.append({"clip": ci, "path": c["path"], "start": start, "end": start + length,
                          "score": seg["score"], "rank_in_clip": si})
    if not cands:
        sys.exit("El análisis no encontró tramos aprovechables. Revisa las hojas de contactos y escribe el plan a mano.")

    # 2) selección: primero el mejor tramo de cada clip (en orden cronológico), luego segundos tramos
    chosen = []
    total = 0.0
    for rank in range(4):
        for cand in sorted((x for x in cands if x["rank_in_clip"] == rank), key=lambda x: x["clip"]):
            if total + (cand["end"] - cand["start"]) > target + 1.5:
                continue
            chosen.append(cand)
            total += cand["end"] - cand["start"]
        if total >= target - lo:
            break
    chosen.sort(key=lambda x: (x["clip"], x["start"]))

    # 3) gancho: el tramo con más puntuación abre el vídeo si el estilo es dinámico
    if args.style == "dynamic" and len(chosen) > 1:
        best = max(chosen, key=lambda x: x["score"])
        chosen.remove(best)
        chosen.insert(0, best)

    # 4) efectos y transiciones por tramo
    plan_clips, notes = [], []
    for i, cand in enumerate(chosen):
        c = clips[cand["clip"]]
        s0, s1 = int(cand["start"]), max(int(cand["start"]) + 1, int(math.ceil(cand["end"])))
        motion = [m for m in c["per_second"]["motion"][s0:s1] if m is not None]
        bright = [b for b in c["per_second"]["brightness"][s0:s1] if b is not None]
        m_avg = sum(motion) / len(motion) if motion else 0
        b_avg = sum(bright) / len(bright) if bright else 128
        effects = []
        why = []
        if m_avg < 1.0:
            effects.append(style["zoom"])
            why.append("plano casi estático: un zoom lento le da vida")
        speed = 1.0
        if m_avg < 0.8 and (cand["end"] - cand["start"]) >= 3 and style["speed_slow"] > 1.0:
            speed = style["speed_slow"]
            why.append(f"acelerado x{speed} para no perder ritmo")
        if c["orientation"] == "horizontal":
            why.append("horizontal: se recorta al centro (cambia fit a blur si el encuadre lo pide)")
        entry = {"path": c["path"], "start": round(cand["start"], 2), "end": round(cand["end"], 2)}
        if speed != 1.0:
            entry["speed"] = speed
        if effects:
            entry["effects"] = effects
        if i < len(chosen) - 1:
            nxt = clips[chosen[i + 1]["clip"]]
            n0 = int(chosen[i + 1]["start"])
            nb = nxt["per_second"]["brightness"][n0] or 128
            nm = nxt["per_second"]["motion"][n0] or 0
            if abs(nb - b_avg) > 70:
                tr = style["alt"]
                why.append(f"salto de luz grande hacia el siguiente plano: transición {tr}")
            elif m_avg > 4 and nm > 4 and args.style != "calm":
                tr = "none"
                why.append("dos planos con mucho movimiento: corte seco")
            else:
                tr = style["transition"]
            entry["transition"] = tr
            if tr != "none":
                entry["transition_duration"] = style["td"]
        plan_clips.append(entry)
        notes.append(f"{i + 1}. {os.path.basename(c['path'])} {cand['start']:g}-{cand['end']:g}s "
                     f"(puntuación {cand['score']}) — " + ("; ".join(why) if why else "tal cual"))

    plan = {
        "clips": plan_clips,
        "fit": "cover",
        "grade": style["grade"],
        "transition": style["transition"],
        "transition_duration": style["td"],
        "output": args.render_output,
    }
    if args.title:
        plan["title"] = args.title
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, ensure_ascii=False, indent=2)
    md = os.path.splitext(args.output)[0] + ".md"
    dur = sum(e["end"] - e["start"] for e in plan_clips) / 1.0
    with open(md, "w", encoding="utf-8") as fh:
        fh.write(f"# Propuesta de montaje ({args.style}, ~{dur:.0f}s de {len(plan_clips)} planos)\n\n")
        fh.write(f"Etalonaje: {style['grade']}. Transición base: {style['transition']} {style['td']}s.\n\n")
        fh.write("\n".join(notes) + "\n\n")
        fh.write("Revisa las hojas de contactos y ajusta start/end, el orden, los efectos o las "
                 "transiciones en el JSON antes de renderizar.\n")
    print(open(md, encoding="utf-8").read())
    print(f"Plan: {args.output}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze", help="analiza clips y genera hojas de contactos")
    a.add_argument("clips", nargs="+")
    a.add_argument("-o", "--output", default="analysis", help="carpeta de salida")
    a.add_argument("--interval", type=int, help="segundos entre fotogramas de la hoja de contactos")
    a.set_defaults(func=cmd_analyze)
    s = sub.add_parser("suggest", help="propone un plan de montaje a partir del análisis")
    s.add_argument("analysis", help="analysis.json")
    s.add_argument("-o", "--output", default="plan.json")
    s.add_argument("--target", type=float, default=30, help="duración objetivo en segundos")
    s.add_argument("--style", choices=sorted(STYLES), default="dynamic")
    s.add_argument("--title", help="rótulo de gancho")
    s.add_argument("--render-output", default="tiktok.mp4", help="nombre del mp4 que generará render")
    s.set_defaults(func=cmd_suggest)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
