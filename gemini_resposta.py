"""
gemini_resposta.py
------------------
Usa a IA do Gemini (que "enxerga" imagens) para transcrever uma página
e dizer QUAL ALTERNATIVA ESTÁ MARCADA em cada questão.

Por que não dá só com OCR? O OCR lê LETRAS. Um círculo, um X ou um
marca-texto em cima da alternativa não é letra, então ele simplesmente
ignora. A IA olha a imagem inteira, como uma pessoa olharia.

A chave vem da variável de ambiente GEMINI_API_KEY (a mesma do Gemini CLI).
Usa só a biblioteca padrão do Python (urllib), sem instalar nada.
"""

import base64
import io
import json
import os
import time
import urllib.error
import urllib.request

# Tenta o primeiro; se estiver lotado (503) ou sem cota (429), tenta o próximo.
# Teste de 2026-11-12 (prova difícil: marca-texto, ✓, bolinha, rasura):
#   gemini-3.5-flash 4/4 · gemini-flash-lite-latest 3/4 (errou a rasura).
# Os modelos Pro precisam de plano pago na API (no grátis dão erro 429).
MODELOS = ["gemini-3.5-flash", "gemini-flash-lite-latest", "gemini-flash-latest"]
URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"

INSTRUCAO = (
    "Você recebe a imagem de uma página (prova, exercício ou documento).\n"
    "1) Transcreva TODO o texto fielmente, em português, mantendo a ordem e as quebras de linha.\n"
    "2) Para cada questão de múltipla escolha, logo depois da última alternativa dela, "
    "acrescente uma linha exatamente assim: 'Resposta marcada: <letra>' "
    "(ou 'Resposta marcada: nenhuma' se nada estiver marcado). Considere marcação: "
    "círculo, X, risco, marca-texto, preenchimento ou qualquer destaque feito na alternativa.\n"
    "3) Se uma questão aberta tiver resposta escrita, transcreva a resposta também.\n"
    "Não invente nada que não esteja na imagem. Não adicione comentários seus."
)


class ErroGemini(Exception):
    """Erro ao falar com a IA (sem chave, sem internet, cota acabou...)."""


def _pegar_chave() -> str:
    chave = os.environ.get("GEMINI_API_KEY", "")
    if not chave and os.name == "nt":
        # App aberto antes de a variável existir: lê direto do registro do Windows.
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                chave, _ = winreg.QueryValueEx(k, "GEMINI_API_KEY")
        except OSError:
            chave = ""
    if not chave:
        raise ErroGemini("Chave GEMINI_API_KEY não encontrada no Windows.")
    return chave


def _chamar(modelo: str, png_bytes: bytes, chave: str) -> str:
    corpo = {
        "contents": [{
            "parts": [
                {"text": INSTRUCAO},
                {"inline_data": {"mime_type": "image/png",
                                 "data": base64.b64encode(png_bytes).decode("ascii")}},
            ]
        }],
        "generationConfig": {"temperature": 0},  # 0 = sem "criatividade"
    }
    pedido = urllib.request.Request(
        URL.format(modelo=modelo),
        data=json.dumps(corpo).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": chave},
        method="POST",
    )
    with urllib.request.urlopen(pedido, timeout=120) as resp:
        dados = json.loads(resp.read().decode("utf-8"))
    partes = dados["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in partes).strip()


def ler_pagina_com_ia(imagem) -> str:
    """
    Recebe uma imagem do Pillow (PIL.Image) e devolve o texto transcrito
    com as linhas 'Resposta marcada: ...'. Tenta de novo se o servidor
    estiver lotado.
    """
    chave = _pegar_chave()
    buffer = io.BytesIO()
    imagem.convert("RGB").save(buffer, format="PNG")
    png = buffer.getvalue()

    ultimo_erro = None
    for modelo in MODELOS:
        for tentativa in range(3):
            try:
                return _chamar(modelo, png, chave)
            except urllib.error.HTTPError as e:
                ultimo_erro = f"HTTP {e.code} no modelo {modelo}"
                if e.code in (429, 500, 503):      # lotado/sem cota: espera e tenta
                    time.sleep(2 * (tentativa + 1))
                    continue
                break                               # outro erro: troca de modelo
            except (urllib.error.URLError, TimeoutError) as e:
                ultimo_erro = f"sem conexão ({e})"
                time.sleep(2)
            except (KeyError, IndexError):
                ultimo_erro = f"resposta vazia do modelo {modelo}"
                break
    raise ErroGemini(f"A IA não respondeu: {ultimo_erro}")
