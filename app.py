import os
import sys
import glob
from pathlib import Path
from datetime import datetime

# Configuração automática antes dos imports
if "TESSDATA_PREFIX" not in os.environ:
    tessdata_path = Path.home() / "tessdata"
    if tessdata_path.is_dir():
        os.environ["TESSDATA_PREFIX"] = str(tessdata_path)

tesseract_dir = Path(r"C:\Program Files\Tesseract-OCR")
if tesseract_dir.is_dir():
    path_env = os.environ.get("PATH", "")
    if str(tesseract_dir) not in path_env:
        os.environ["PATH"] = str(tesseract_dir) + os.pathsep + path_env

local_app_data = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
poppler_pattern = str(Path(local_app_data) / "Microsoft" / "WinGet" / "Packages" / "oschwartz10612.Poppler*" / "poppler-*" / "Library" / "bin")
poppler_matches = glob.glob(poppler_pattern)
if poppler_matches:
    poppler_bin = poppler_matches[0]
    if poppler_bin not in os.environ.get("PATH", ""):
        os.environ["PATH"] = poppler_bin + os.pathsep + os.environ.get("PATH", "")

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QListWidgetItem, QLineEdit, QLabel,
    QProgressBar, QSplitter, QPlainTextEdit, QFileDialog, QMessageBox, QCheckBox
)

from PIL import Image
from pdf2image import convert_from_path

from extrair_texto import texto_de_imagem, texto_de_pdf, EXTENSOES_IMAGEM, EXTENSAO_PDF
from gemini_resposta import ler_pagina_com_ia, ErroGemini


def texto_com_ia(arquivo: Path) -> str:
    """Lê o arquivo com a IA, que enxerga a alternativa marcada. PDF: página por página."""
    if arquivo.suffix.lower() == EXTENSAO_PDF:
        partes = []
        for numero, pagina in enumerate(convert_from_path(str(arquivo), dpi=200), start=1):
            partes.append(f"--- Página {numero} ---\n{ler_pagina_com_ia(pagina)}")
        return "\n\n".join(partes)
    with Image.open(arquivo) as img:
        return ler_pagina_com_ia(img)


class Trabalhador(QThread):
    progresso = Signal(int, int)
    log = Signal(str)
    texto = Signal(str)
    terminou = Signal(int, int)

    def __init__(self, itens, pasta_saida, usar_ia=False):
        super().__init__()
        self.itens = itens
        self.pasta_saida = Path(pasta_saida)
        self.usar_ia = usar_ia

    def run(self):
        # try/finally: aconteça o que acontecer, o sinal "terminou" sai,
        # e a janela religa os botões (senão ela ficaria travada).
        ok_count = err_count = 0
        try:
            ok_count, err_count = self._extrair()
        except Exception as e:
            self.log.emit(f"Erro inesperado: {e}")
        finally:
            self.terminou.emit(ok_count, err_count)

    def _extrair(self):
        tarefas = []
        valid_exts = EXTENSOES_IMAGEM | {EXTENSAO_PDF}

        for item_str in self.itens:
            p = Path(item_str)
            if not p.exists():
                continue
            if p.is_dir():
                # Raiz de um drive (ex.: G:\) não tem nome: vira "Unidade G"
                nome_pasta = p.name or f"Unidade {p.drive.rstrip(':')}"
                try:
                    encontrados = sorted(p.rglob("*"))
                except OSError as e:  # ex.: subpasta sem permissão
                    self.log.emit(f"Não consegui ler toda a pasta {p}: {e}")
                    encontrados = []
                for subp in encontrados:
                    if subp.is_file() and subp.suffix.lower() in valid_exts:
                        rel = subp.relative_to(p)
                        dest_rel = Path(nome_pasta) / rel
                        tarefas.append((subp, dest_rel))
            elif p.is_file():
                if p.suffix.lower() in valid_exts:
                    tarefas.append((p, Path(p.name)))

        total = len(tarefas)
        ok_count = 0
        err_count = 0

        self.log.emit(f"Iniciando extração de {total} arquivo(s)...")

        for i, (arq, dest_rel) in enumerate(tarefas, start=1):
            self.log.emit(f"Processando: {arq}")
            try:
                ext = arq.suffix.lower()
                if self.usar_ia:
                    try:
                        txt = texto_com_ia(arq)
                    except ErroGemini as e:
                        # Sem IA (sem internet, cota acabou...): usa o OCR comum e avisa
                        self.log.emit(f"IA falhou em {arq.name} ({e}). Usando OCR comum.")
                        txt = texto_de_pdf(arq) if ext == EXTENSAO_PDF else texto_de_imagem(arq)
                        txt = "(Sem detecção de resposta: a IA não respondeu)\n" + txt
                elif ext == EXTENSAO_PDF:
                    txt = texto_de_pdf(arq)
                else:
                    txt = texto_de_imagem(arq)
                ok_count += 1
                self.texto.emit(txt)
            except Exception as e:
                err_count += 1
                txt = f"(ERRO ao ler este arquivo: {e})"
                self.log.emit(f"Erro em {arq}: {e}")
                self.texto.emit(txt)

            saida_arq = self.pasta_saida / f"{dest_rel}.txt"
            try:
                saida_arq.parent.mkdir(parents=True, exist_ok=True)
                with open(saida_arq, "w", encoding="utf-8") as f:
                    f.write(txt)
            except Exception as e:
                self.log.emit(f"Erro ao salvar {saida_arq}: {e}")

            self.progresso.emit(i, total)  # só conta depois de salvar

        resumo = f"Pronto! {ok_count} lido(s), {err_count} com erro. Salvo em: {self.pasta_saida}"
        self.log.emit(resumo)
        return ok_count, err_count


class JanelaPrincipal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Extrator de Texto")
        self.resize(900, 650)
        self.setAcceptDrops(True)

        self.worker = None

        self.init_ui()

        self.shortcut_paste = QShortcut(QKeySequence.Paste, self)
        self.shortcut_paste.activated.connect(self.colar)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 1. Linha de botões
        btn_layout = QHBoxLayout()
        self.btn_add_pasta = QPushButton("📁 Adicionar pasta")
        self.btn_add_arq = QPushButton("📄 Adicionar arquivos")
        self.btn_colar = QPushButton("📋 Colar (Ctrl+V)")
        self.btn_remover = QPushButton("🗑 Remover selecionado")
        self.btn_limpar = QPushButton("Limpar lista")
        self.btn_abrir_pasta = QPushButton("📂 Abrir pasta de saída")
        self.btn_abrir_pasta.setEnabled(False)

        self.btn_add_pasta.clicked.connect(self.adicionar_pasta)
        self.btn_add_arq.clicked.connect(self.adicionar_arquivos)
        self.btn_colar.clicked.connect(self.colar)
        self.btn_remover.clicked.connect(self.remover_selecionado)
        self.btn_limpar.clicked.connect(self.limpar_lista)
        self.btn_abrir_pasta.clicked.connect(self.abrir_pasta_saida)

        btn_layout.addWidget(self.btn_add_pasta)
        btn_layout.addWidget(self.btn_add_arq)
        btn_layout.addWidget(self.btn_colar)
        btn_layout.addWidget(self.btn_remover)
        btn_layout.addWidget(self.btn_limpar)
        btn_layout.addWidget(self.btn_abrir_pasta)
        main_layout.addLayout(btn_layout)

        # 2. QListWidget com label de ajuda acima
        label_ajuda = QLabel("Arraste pastas ou arquivos para cá, ou use os botões")
        main_layout.addWidget(label_ajuda)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        main_layout.addWidget(self.list_widget)

        # 3. Linha "Salvar em:"
        salvar_layout = QHBoxLayout()
        salvar_layout.addWidget(QLabel("Salvar em:"))
        self.txt_saida = QLineEdit(str(Path.home() / "Documents" / "Textos extraidos"))
        salvar_layout.addWidget(self.txt_saida)
        self.btn_escolher = QPushButton("Escolher...")
        self.btn_escolher.clicked.connect(self.escolher_pasta_saida)
        salvar_layout.addWidget(self.btn_escolher)
        main_layout.addLayout(salvar_layout)

        # 4. Botão grande "⚡ Extrair" + QProgressBar
        extrair_layout = QHBoxLayout()
        self.btn_extrair = QPushButton("⚡ Extrair")
        self.btn_extrair.setStyleSheet("font-size: 14pt; font-weight: bold; padding: 8px;")
        self.btn_extrair.clicked.connect(self.iniciar_extracao)
        extrair_layout.addWidget(self.btn_extrair)

        self.chk_ia = QCheckBox("🎯 Detectar resposta marcada (IA, precisa de internet)")
        self.chk_ia.setToolTip(
            "Envia as imagens para a IA do Google (Gemini), que enxerga círculos, X e destaques.\n"
            "Mais lento que o OCR comum. Não use com documentos sigilosos."
        )
        extrair_layout.addWidget(self.chk_ia)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        extrair_layout.addWidget(self.progress_bar)
        main_layout.addLayout(extrair_layout)

        # 5. QSplitter horizontal
        splitter = QSplitter(Qt.Horizontal)

        # Esquerda: Registro (log)
        widget_esq = QWidget()
        layout_esq = QVBoxLayout(widget_esq)
        layout_esq.addWidget(QLabel("Registro"))
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        layout_esq.addWidget(self.log_edit)
        splitter.addWidget(widget_esq)

        # Direita: Texto extraído + Botão Copiar texto
        widget_dir = QWidget()
        layout_dir = QVBoxLayout(widget_dir)
        layout_dir.addWidget(QLabel("Texto extraído"))
        self.texto_edit = QPlainTextEdit()
        self.texto_edit.setReadOnly(True)
        layout_dir.addWidget(self.texto_edit)

        self.btn_copiar = QPushButton("Copiar texto")
        self.btn_copiar.clicked.connect(self.copiar_texto)
        layout_dir.addWidget(self.btn_copiar)
        splitter.addWidget(widget_dir)

        splitter.setSizes([450, 450])
        main_layout.addWidget(splitter)

    def log(self, mensagem):
        self.log_edit.appendPlainText(mensagem)

    def adicionar(self, caminho_str):
        p = Path(caminho_str)
        if not p.exists():
            return

        for i in range(self.list_widget.count()):
            item_existente = self.list_widget.item(i)
            if item_existente.data(Qt.UserRole) == str(p.resolve()):
                return

        valid_exts = EXTENSOES_IMAGEM | {EXTENSAO_PDF}

        if p.is_dir():
            prefixo = "📁 "
        elif p.is_file():
            if p.suffix.lower() not in valid_exts:
                self.log(f"Aviso: Arquivo ignorado (extensão inválida): {p.name}")
                return
            prefixo = "📄 "
        else:
            return

        item = QListWidgetItem(f"{prefixo}{p.resolve()}")
        item.setData(Qt.UserRole, str(p.resolve()))
        self.list_widget.addItem(item)
        self.log(f"Adicionado: {p}")

    def adicionar_pasta(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Selecionar Pasta")
        if dir_path:
            self.adicionar(dir_path)

    def adicionar_arquivos(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Selecionar Arquivos", "", "Imagens e PDFs (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.gif *.pdf);;Todos os arquivos (*.*)"
        )
        for f in files:
            self.adicionar(f)

    def remover_selecionado(self):
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))

    def limpar_lista(self):
        self.list_widget.clear()

    def escolher_pasta_saida(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Selecionar Pasta de Saída")
        if dir_path:
            self.txt_saida.setText(dir_path)

    def abrir_pasta_saida(self):
        pasta = self.txt_saida.text()
        if Path(pasta).is_dir():
            os.startfile(pasta)
        else:
            QMessageBox.warning(self, "Aviso", "Pasta de saída não existe.")

    def copiar_texto(self):
        texto = self.texto_edit.toPlainText()
        if texto:
            QApplication.clipboard().setText(texto)
            self.log("Texto copiado para a área de transferência.")

    def colar(self):
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()

        if mime.hasUrls():
            for url in mime.urls():
                caminho = url.toLocalFile()
                if caminho:
                    self.adicionar(caminho)
        elif mime.hasImage():
            image = clipboard.image()
            if not image.isNull():
                pasta_colados = Path(self.txt_saida.text()) / "colados"
                pasta_colados.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                arq_path = pasta_colados / f"print-{timestamp}.png"
                if image.save(str(arq_path), "PNG"):
                    self.adicionar(str(arq_path))
                    self.log(f"Imagem colada salva em: {arq_path}")
                else:
                    self.log("Erro ao salvar imagem colada.")
            else:
                self.log("Nada para colar")
        else:
            self.log("Nada para colar")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            caminho = url.toLocalFile()
            if caminho:
                self.adicionar(caminho)

    def iniciar_extracao(self):
        itens = []
        for i in range(self.list_widget.count()):
            itens.append(self.list_widget.item(i).data(Qt.UserRole))

        if not itens:
            QMessageBox.warning(self, "Aviso", "A lista está vazia. Adicione pastas ou arquivos para extrair.")
            return

        pasta_saida = self.txt_saida.text()
        if not pasta_saida:
            QMessageBox.warning(self, "Aviso", "Defina a pasta de saída.")
            return

        self.definir_controles_habilitados(False)
        self.progress_bar.setValue(0)
        self.texto_edit.clear()

        self.worker = Trabalhador(itens, pasta_saida, usar_ia=self.chk_ia.isChecked())
        self.worker.progresso.connect(self.atualizar_progresso)
        self.worker.log.connect(self.log)
        self.worker.texto.connect(self.exibir_texto)
        self.worker.terminou.connect(self.extracao_terminada)
        self.worker.start()

    def definir_controles_habilitados(self, habilitado):
        self.btn_add_pasta.setEnabled(habilitado)
        self.btn_add_arq.setEnabled(habilitado)
        self.btn_colar.setEnabled(habilitado)
        self.btn_remover.setEnabled(habilitado)
        self.btn_limpar.setEnabled(habilitado)
        self.btn_escolher.setEnabled(habilitado)
        self.btn_extrair.setEnabled(habilitado)
        self.txt_saida.setEnabled(habilitado)
        self.chk_ia.setEnabled(habilitado)

    def atualizar_progresso(self, atual, total):
        porcentagem = int((atual / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(porcentagem)

    def exibir_texto(self, texto):
        self.texto_edit.setPlainText(texto)

    def extracao_terminada(self, ok_count, err_count):
        self.definir_controles_habilitados(True)
        self.btn_abrir_pasta.setEnabled(True)
        self.progress_bar.setValue(100)
        saida = self.txt_saida.text()
        resumo = f"Pronto! {ok_count} lido(s), {err_count} com erro. Salvo em: {saida}"
        QMessageBox.information(self, "Extração Concluída", resumo)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    janela = JanelaPrincipal()
    janela.show()
    sys.exit(app.exec())
