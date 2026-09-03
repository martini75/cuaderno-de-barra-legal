#!/usr/bin/env bash
# Deja ffmpeg disponible para tiktok_edit.py. Prueba el gestor de paquetes y, si no hay
# permisos o red para apt, instala el binario estático de imageio-ffmpeg con pip.
set -u
if command -v ffmpeg >/dev/null 2>&1; then ffmpeg -version | head -1; exit 0; fi
if command -v apt-get >/dev/null 2>&1; then (apt-get install -y ffmpeg >/dev/null 2>&1 || sudo apt-get install -y ffmpeg >/dev/null 2>&1) && command -v ffmpeg >/dev/null 2>&1 && { ffmpeg -version | head -1; exit 0; }; fi
if command -v brew >/dev/null 2>&1; then brew install ffmpeg && exit 0; fi
python3 -c "import imageio_ffmpeg" 2>/dev/null || pip install -q imageio-ffmpeg || pip3 install -q imageio-ffmpeg
python3 -c "import imageio_ffmpeg,sys; print('ffmpeg estático:', imageio_ffmpeg.get_ffmpeg_exe())"
