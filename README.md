# Extrator de Texto

Transforma **imagens e PDFs em texto (.txt)**, um arquivo por documento, mantendo as subpastas.
Tem uma versão de **linha de comando** e um **app com janela**.

## O que faz
- **PDF digital**: copia o texto direto (rápido e exato).
- **PDF escaneado e imagens**: usa OCR (Tesseract) em português e inglês.
- **Resposta marcada (opcional)**: com a IA do Gemini, detecta a alternativa circulada, com X, ✓ ou destacada e escreve `Resposta marcada: <letra>` depois de cada questão.
- **Áudio e vídeo** (mp3, wav, m4a, ogg, mp4, mkv, webm, mov...): transcreve a fala com o Whisper do Groq. Arquivos longos são cortados em pedaços de 10 minutos, com a marcação de tempo no texto.

## App com janela (`app.py`)
- Adicionar pastas ou arquivos pelos botões
- Arrastar do Explorer para a janela
- **Ctrl+V**: cola arquivos copiados no Explorer ou um print da tela
- Botão **⚡ Extrair**, barra de progresso e painel com o texto (botão **Copiar texto**)

No Windows, abra com dois cliques em `Abrir Extrator.bat`.

## Linha de comando
```
python extrair_texto.py CAMINHO_DA_PASTA [pasta_de_saida]
```

## Instalação (Windows)
1. Python 3.12 ou 3.13, depois:
   ```
   python -m venv venv
   venv\Scripts\pip install -r requirements.txt
   ```
2. **Tesseract OCR** (`winget install UB-Mannheim.TesseractOCR`) com o idioma português (`por.traineddata`).
3. **Poppler** (`winget install oschwartz10612.Poppler`), com a pasta `Library\bin` no PATH.
4. Para a resposta marcada: uma chave do [Google AI Studio](https://aistudio.google.com/apikey) na variável de ambiente `GEMINI_API_KEY`.
5. Para áudio e vídeo: o **ffmpeg** (`winget install Gyan.FFmpeg`) e uma chave do [Groq](https://console.groq.com/keys) na variável de ambiente `GROQ_API_KEY`.

> A opção de resposta marcada envia as imagens para a IA do Google, e a transcrição envia o áudio para o Groq. Não use com conteúdo sigiloso.

## Arquivos
| Arquivo | O que é |
|---|---|
| `app.py` | App com janela (PySide6) |
| `extrair_texto.py` | Funções de extração + versão de linha de comando |
| `gemini_resposta.py` | Leitura com IA (detecta a alternativa marcada) |
| `groq_audio.py` | Transcrição de áudio e vídeo (Whisper no Groq) |
| `exemplo/` | Arquivos de teste: imagem, PDF digital, PDF escaneado e provas marcadas |
