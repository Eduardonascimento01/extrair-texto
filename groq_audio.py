"""
groq_audio.py
-------------
Transforma ÁUDIO e VÍDEO em texto usando o Whisper (IA de transcrição)
rodando nos servidores do Groq, que são muito rápidos.

Como funciona, passo a passo:
  1. O ffmpeg tira o som do arquivo (serve para vídeo também) e o deixa
     "leve": 1 canal (mono), 16 mil amostras por segundo, MP3 de 32 kbps.
     É a qualidade de uma ligação telefônica: suficiente para fala e
     MUITO menor (1 hora fica com uns 14 MB).
  2. Corta em pedaços de 10 minutos, porque o Groq aceita no máximo
     25 MB por envio no plano grátis.
  3. Manda cada pedaço para o Whisper e junta os textos na ordem.

A chave vem da variável de ambiente GROQ_API_KEY.
Usa só a biblioteca padrão do Python + o programa ffmpeg (já instalado).
"""

import os
import shutil
import subprocess
import tempfile
import time
import json
import urllib.error
import urllib.request
import uuid
from pathlib import Path

EXTENSOES_AUDIO_VIDEO = {
    ".mp3", ".wav", ".m4a", ".ogg", ".opus", ".flac", ".aac", ".wma",   # áudio
    ".mp4", ".mkv", ".webm", ".mov", ".avi", ".wmv",                    # vídeo
}

URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MODELO = "whisper-large-v3-turbo"
MINUTOS_POR_PEDACO = 10


class ErroAudio(Exception):
    """Erro ao transcrever (sem ffmpeg, sem chave, sem internet, limite...)."""


def _pegar_chave() -> str:
    chave = os.environ.get("GROQ_API_KEY", "")
    if not chave and os.name == "nt":
        # App aberto antes de a variável existir: lê direto do registro do Windows.
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                chave, _ = winreg.QueryValueEx(k, "GROQ_API_KEY")
        except OSError:
            chave = ""
    if not chave:
        raise ErroAudio("Chave GROQ_API_KEY não encontrada no Windows.")
    return chave


def _cortar_em_pedacos(arquivo: Path, pasta_temp: Path) -> list[Path]:
    """Usa o ffmpeg para extrair o som e cortar em pedaços leves de 10 minutos."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ErroAudio("ffmpeg não encontrado (instale com: winget install Gyan.FFmpeg).")
    molde = pasta_temp / "pedaco_%03d.mp3"
    comando = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(arquivo),
        "-vn",                    # ignora a imagem (vídeo)
        "-ac", "1",               # mono
        "-ar", "16000",           # 16 mil amostras por segundo
        "-b:a", "32k",            # 32 kbps
        "-f", "segment", "-segment_time", str(MINUTOS_POR_PEDACO * 60),
        str(molde),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    pedacos = sorted(pasta_temp.glob("pedaco_*.mp3"))
    if resultado.returncode != 0 or not pedacos:
        raise ErroAudio("O ffmpeg não conseguiu ler o som deste arquivo "
                        f"({resultado.stderr.strip()[:150] or 'sem áudio?'}).")
    return pedacos


def _enviar(pedaco: Path, chave: str, idioma: str | None) -> str:
    """Manda um pedaço para o Whisper (formulário 'multipart', como um upload de site)."""
    fronteira = uuid.uuid4().hex
    campos = {"model": MODELO, "response_format": "text", "temperature": "0"}
    if idioma:
        campos["language"] = idioma
    corpo = bytearray()
    for nome, valor in campos.items():
        corpo += (f"--{fronteira}\r\nContent-Disposition: form-data; name=\"{nome}\"\r\n\r\n"
                  f"{valor}\r\n").encode("utf-8")
    corpo += (f"--{fronteira}\r\nContent-Disposition: form-data; name=\"file\"; "
              f"filename=\"{pedaco.name}\"\r\nContent-Type: audio/mpeg\r\n\r\n").encode("utf-8")
    corpo += pedaco.read_bytes() + f"\r\n--{fronteira}--\r\n".encode("utf-8")

    pedido = urllib.request.Request(URL, data=bytes(corpo), method="POST", headers={
        "Authorization": f"Bearer {chave}",
        "Content-Type": f"multipart/form-data; boundary={fronteira}",
        "User-Agent": "extrair-texto",
    })
    for tentativa in range(4):
        try:
            with urllib.request.urlopen(pedido, timeout=300) as resp:
                return resp.read().decode("utf-8").strip()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and tentativa < 3:
                # Limite por minuto/hora do plano grátis: espera o que o servidor pedir
                espera = int(e.headers.get("retry-after", 0) or 0) or 15 * (tentativa + 1)
                time.sleep(min(espera, 120))
                continue
            try:
                motivo = json.loads(e.read())["error"]["message"][:150]
            except Exception:
                motivo = ""
            raise ErroAudio(f"Groq recusou (HTTP {e.code}). {motivo}")
        except (urllib.error.URLError, TimeoutError) as e:
            if tentativa < 3:
                time.sleep(5)
                continue
            raise ErroAudio(f"Sem conexão com o Groq ({e}).")
    raise ErroAudio("O Groq não respondeu depois de várias tentativas.")


def transcrever(arquivo: Path, idioma: str | None = "pt", avisar=None) -> str:
    """
    Transcreve um áudio ou vídeo e devolve o texto.
    idioma: "pt" ajuda o Whisper; None deixa ele descobrir sozinho.
    avisar: função opcional que recebe mensagens de progresso (para o app).
    """
    chave = _pegar_chave()
    with tempfile.TemporaryDirectory(prefix="extrator_audio_") as temp:
        pedacos = _cortar_em_pedacos(Path(arquivo), Path(temp))
        textos = []
        for i, pedaco in enumerate(pedacos, start=1):
            if avisar and len(pedacos) > 1:
                avisar(f"  pedaço {i}/{len(pedacos)} de {Path(arquivo).name}")
            texto = _enviar(pedaco, chave, idioma)
            if len(pedacos) > 1:
                inicio = (i - 1) * MINUTOS_POR_PEDACO
                textos.append(f"--- {inicio // 60:02d}:{inicio % 60:02d}:00 ---\n{texto}")
            else:
                textos.append(texto)
        return "\n\n".join(textos)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: python groq_audio.py ARQUIVO_DE_AUDIO_OU_VIDEO")
        sys.exit(1)
    print(transcrever(Path(sys.argv[1]), avisar=print))
