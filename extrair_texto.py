"""
extrair_texto.py
----------------
Percorre uma pasta (e todas as subpastas), encontra IMAGENS e PDFs
e transforma o conteúdo deles em TEXTO, salvando um .txt para cada arquivo.

Como usar (no terminal):
    python extrair_texto.py  CAMINHO_DA_PASTA  [pasta_de_saida]

Exemplo:
    python extrair_texto.py  C:/Users/Eduardo/Documentos/scans  textos

Bibliotecas necessárias (instale uma vez):
    pip install pytesseract pillow pdfplumber pdf2image
E também os programas:
    - Tesseract OCR (com o idioma português "por")
    - Poppler (usado pelo pdf2image para transformar páginas de PDF em imagem)
"""

import sys
from pathlib import Path

import pdfplumber                       # lê o texto "digital" de PDFs
import pytesseract                      # faz OCR (lê texto de dentro de imagens)
from PIL import Image                   # abre arquivos de imagem
from pdf2image import convert_from_path # transforma páginas de PDF em imagens

# Se estiver no Windows e o Python não achar o Tesseract, descomente a linha
# abaixo e ajuste o caminho onde ele foi instalado:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Tipos de arquivo que o programa vai procurar
EXTENSOES_IMAGEM = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp", ".gif"}
EXTENSAO_PDF = ".pdf"

# Idiomas do OCR: português + inglês
IDIOMAS_OCR = "por+eng"


def texto_de_imagem(caminho: Path) -> str:
    """Abre uma imagem e usa OCR para 'ler' o texto que aparece nela."""
    with Image.open(caminho) as img:
        return pytesseract.image_to_string(img, lang=IDIOMAS_OCR)


def texto_de_pdf(caminho: Path) -> str:
    """
    Extrai o texto de um PDF, página por página.

    Existem dois tipos de PDF:
      1) PDF "digital" (criado no Word, por exemplo): o texto está guardado
         dentro do arquivo, então basta copiá-lo -> rápido e exato.
      2) PDF "escaneado": cada página é só uma FOTO. Não há texto guardado,
         então transformamos a página em imagem e usamos OCR.
    """
    partes = []
    with pdfplumber.open(caminho) as pdf:
        for numero, pagina in enumerate(pdf.pages, start=1):
            texto = pagina.extract_text() or ""

            # Se a página veio vazia, provavelmente é escaneada -> usa OCR
            if not texto.strip():
                imagens = convert_from_path(
                    str(caminho), dpi=300, first_page=numero, last_page=numero
                )
                texto = pytesseract.image_to_string(imagens[0], lang=IDIOMAS_OCR)
                texto = "[OCR] " + texto

            partes.append(f"--- Página {numero} ---\n{texto.strip()}")
    return "\n\n".join(partes)


def processar_pasta(pasta: Path, pasta_saida: Path) -> None:
    """
    Procura imagens e PDFs em todas as subpastas e salva UM .txt para cada
    arquivo, recriando a mesma estrutura de subpastas dentro de pasta_saida.

    Exemplo:
        pasta/            ->   pasta_saida/
          foto.png        ->     foto.png.txt
          sub/scan.pdf    ->     sub/scan.pdf.txt
    """
    # rglob("*") = procura recursivamente (em todas as subpastas)
    arquivos = sorted(
        a for a in pasta.rglob("*")
        if a.is_file() and (a.suffix.lower() in EXTENSOES_IMAGEM
                            or a.suffix.lower() == EXTENSAO_PDF)
    )

    if not arquivos:
        print("Nenhuma imagem ou PDF encontrado nessa pasta.")
        return

    print(f"Encontrei {len(arquivos)} arquivo(s). Começando...\n")
    ok, erros = 0, 0

    for i, arquivo in enumerate(arquivos, start=1):
        caminho_relativo = arquivo.relative_to(pasta)   # ex.: sub/scan.pdf
        print(f"[{i}/{len(arquivos)}] {caminho_relativo}")
        try:
            if arquivo.suffix.lower() == EXTENSAO_PDF:
                texto = texto_de_pdf(arquivo)
            else:
                texto = texto_de_imagem(arquivo)
            ok += 1
        except Exception as erro:  # um arquivo com problema não para o programa
            texto = f"(ERRO ao ler este arquivo: {erro})"
            erros += 1

        # Nome do .txt = nome original + ".txt" (ex.: scan.pdf.txt).
        # Manter a extensão original evita que "nota.pdf" e "nota.png"
        # tentem salvar no mesmo "nota.txt".
        destino = pasta_saida / caminho_relativo.parent / (arquivo.name + ".txt")
        destino.parent.mkdir(parents=True, exist_ok=True)  # cria as subpastas
        destino.write_text(texto.strip() + "\n", encoding="utf-8")

    print(f"\nPronto! {ok} lido(s) com sucesso, {erros} com erro.")
    print(f"Arquivos .txt salvos em: {pasta_saida.resolve()}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python extrair_texto.py CAMINHO_DA_PASTA [pasta_de_saida]")
        sys.exit(1)

    pasta = Path(sys.argv[1])
    saida = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("textos_extraidos")

    if not pasta.is_dir():
        print(f"A pasta '{pasta}' não existe.")
        sys.exit(1)

    processar_pasta(pasta, saida)
