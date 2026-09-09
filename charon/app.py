"""Charon — interface de bureau pour envoyer du SysEx vers un Volca FM."""
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QTableWidget, QTableWidgetItem, QSpinBox,
    QPlainTextEdit, QFileDialog, QHeaderView, QAbstractItemView, QMessageBox,
    QTabWidget,
)

from . import midi
from .sysex import Message, read_file, set_channel
from .workshop import Workshop

STYLE = """
QMainWindow, QWidget { background: #0E0F0D; color: #D6D3CB;
    font-family: "IBM Plex Mono", "DejaVu Sans Mono", monospace; font-size: 12px; }
QLabel#title { font-size: 17px; font-weight: 700; color: #E8E6DF; letter-spacing: .04em; }
QLabel#subtitle { color: #7C8073; font-size: 11px; }
QLabel.section { color: #7C8073; font-size: 10px; font-weight: 700;
    text-transform: uppercase; letter-spacing: .12em; }
QPushButton { background: #161814; border: 1px solid #2A2E24; border-radius: 3px;
    padding: 7px 14px; color: #D6D3CB; }
QPushButton:hover { border-color: #4A5040; background: #1C1F19; }
QPushButton:disabled { color: #4A4E45; border-color: #1F221C; }
QPushButton#send { background: #2D3A1E; border-color: #4E6B2A; color: #C8E89A; font-weight: 700; }
QPushButton#send:hover { background: #3A4A28; }
QPushButton#send:disabled { background: #161814; color: #4A4E45; border-color: #1F221C; }
QComboBox, QSpinBox { background: #0A0B09; border: 1px solid #2A2E24; border-radius: 3px;
    padding: 6px 8px; color: #D6D3CB; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView { background: #161814; border: 1px solid #2A2E24;
    selection-background-color: #2D3A1E; color: #D6D3CB; }
QTableWidget { background: #0A0B09; border: 1px solid #2A2E24; border-radius: 3px;
    gridline-color: #1F221C; selection-background-color: #2D3A1E; }
QHeaderView::section { background: #161814; color: #7C8073; border: none;
    border-bottom: 1px solid #2A2E24; padding: 6px; font-size: 10px;
    text-transform: uppercase; letter-spacing: .1em; }
QTabWidget::pane { border: 1px solid #2A2E24; border-radius: 3px; top: -1px; }
QTabBar::tab { background: #121410; color: #7C8073; border: 1px solid #2A2E24;
    padding: 7px 18px; margin-right: 2px; border-top-left-radius: 3px;
    border-top-right-radius: 3px; }
QTabBar::tab:selected { background: #1C1F19; color: #D6D3CB; border-bottom-color: #1C1F19; }
QListWidget { background: #0A0B09; border: 1px solid #2A2E24; border-radius: 3px;
    selection-background-color: #2D3A1E; selection-color: #E8E6DF; }
QListWidget::item { padding: 3px 6px; }
QPlainTextEdit { background: #0A0B09; border: 1px solid #2A2E24; border-radius: 3px;
    color: #9AA08D; padding: 6px; }
"""

OK, WARN, BAD = "#A3E635", "#E6A700", "#D94F3D"


class Sender(QThread):
    """L'envoi vit dans un fil séparé : un dump fait ~1,3 s à 31250 bauds,
    et l'interface doit rester vivante pendant ce temps."""
    progress = Signal(int, int)
    done = Signal(int)
    failed = Signal(str)

    def __init__(self, port, payloads, delay):
        super().__init__()
        self.port, self.payloads, self.delay = port, payloads, delay

    def run(self):
        try:
            n = midi.send(self.port, self.payloads, self.delay,
                          progress=lambda i, t: self.progress.emit(i, t))
            self.done.emit(n)
        except Exception as exc:                    # noqa: BLE001
            self.failed.emit(str(exc))


class Charon(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Charon — passeur SysEx")
        self.resize(920, 620)
        self.setAcceptDrops(True)
        self.messages: list[tuple[str, Message]] = []
        self.sender_thread = None
        self._build()
        self.refresh_ports()

    # ── construction ────────────────────────────────────────────────────
    def _build(self):
        root = QWidget()
        v = QVBoxLayout(root)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(12)

        title = QLabel("CHARON")
        title.setObjectName("title")
        sub = QLabel("passeur SysEx — DX7 / Volca FM, par le port MIDI du système")
        sub.setObjectName("subtitle")
        v.addWidget(title)
        v.addWidget(sub)

        # Port MIDI
        row = QHBoxLayout()
        lab = QLabel("Sortie MIDI")
        lab.setProperty("class", "section")
        row.addWidget(lab)
        self.ports = QComboBox()
        self.ports.setMinimumWidth(340)
        row.addWidget(self.ports, 1)
        b = QPushButton("Rafraîchir")
        b.clicked.connect(self.refresh_ports)
        row.addWidget(b)
        v.addLayout(row)

        # Onglets : envoi de fichiers d'un côté, atelier de banks de l'autre
        self.tabs = QTabWidget()
        v.addWidget(self.tabs, 1)

        envoi = QWidget()
        v = QVBoxLayout(envoi)          # la suite se construit dans l'onglet
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(10)

        # Fichiers
        row2 = QHBoxLayout()
        b_open = QPushButton("Ouvrir des .syx…")
        b_open.clicked.connect(self.open_files)
        row2.addWidget(b_open)
        b_clear = QPushButton("Vider")
        b_clear.clicked.connect(self.clear_files)
        row2.addWidget(b_clear)
        row2.addStretch(1)
        self.hint = QLabel("ou dépose des fichiers dans la fenêtre")
        self.hint.setObjectName("subtitle")
        row2.addWidget(self.hint)
        v.addLayout(row2)

        # Table
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Fichier", "#", "Format", "Taille", "Canal", "État"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 6):
            h.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self.update_send_button)
        v.addWidget(self.table, 1)

        # Options + envoi
        row3 = QHBoxLayout()
        l1 = QLabel("Canal")
        l1.setProperty("class", "section")
        row3.addWidget(l1)
        self.channel = QComboBox()
        self.channel.addItem("ne pas toucher", 0)
        for c in range(1, 17):
            self.channel.addItem(str(c), c)
        row3.addWidget(self.channel)

        l2 = QLabel("Délai entre messages")
        l2.setProperty("class", "section")
        row3.addWidget(l2)
        self.delay = QSpinBox()
        self.delay.setRange(0, 5000)
        self.delay.setSingleStep(50)
        self.delay.setValue(200)
        self.delay.setSuffix(" ms")
        row3.addWidget(self.delay)

        row3.addStretch(1)
        self.b_send = QPushButton("Envoyer la sélection")
        self.b_send.setObjectName("send")
        self.b_send.setEnabled(False)
        self.b_send.clicked.connect(self.send_selected)
        row3.addWidget(self.b_send)
        v.addLayout(row3)

        self.tabs.addTab(envoi, "Envoyer des fichiers")

        self.workshop = Workshop()
        self.workshop.log.connect(self.say)
        self.workshop.send_requested.connect(self.send_bank)
        self.tabs.addTab(self.workshop, "Atelier de banks")

        v = root.layout()               # on ressort de l'onglet pour le journal

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(130)
        v.addWidget(self.log)

        self.setCentralWidget(root)

        act = QAction(self)
        act.setShortcut(QKeySequence("Ctrl+O"))
        act.triggered.connect(self.open_files)
        self.addAction(act)

        self.say("Prêt. Branche le Volca, choisis le port, dépose un .syx.")

    # ── utilitaires ─────────────────────────────────────────────────────
    def say(self, text: str):
        self.log.appendPlainText(text)

    def refresh_ports(self):
        current = self.ports.currentText()
        self.ports.clear()
        try:
            ports = midi.output_ports()
        except Exception as exc:                    # noqa: BLE001
            self.say(f"⚠ impossible de lister les ports : {exc}")
            ports = []
        if ports:
            self.ports.addItems(ports)
            idx = self.ports.findText(current)
            if idx >= 0:
                self.ports.setCurrentIndex(idx)
        else:
            self.ports.addItem("aucun port MIDI détecté")
        self.update_send_button()

    def has_port(self) -> bool:
        return self.ports.count() > 0 and not self.ports.currentText().startswith("aucun")

    def update_send_button(self):
        busy = self.sender_thread is not None and self.sender_thread.isRunning()
        self.b_send.setEnabled(
            bool(self.table.selectionModel() and self.table.selectionModel().selectedRows())
            and self.has_port() and not busy)

    # ── fichiers ────────────────────────────────────────────────────────
    def open_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Choisir des fichiers SysEx", str(Path.home()),
            "SysEx (*.syx *.SYX);;Tous les fichiers (*)")
        self.add_paths(paths)

    def add_paths(self, paths):
        for p in paths:
            try:
                msgs = read_file(p)
            except OSError as exc:
                self.say(f"⚠ {Path(p).name} : {exc}")
                continue
            if not msgs:
                self.say(f"⚠ {Path(p).name} : aucun message SysEx trouvé (F0…F7)")
                continue
            for m in msgs:
                self.messages.append((Path(p).name, m))
            self.say(f"＋ {Path(p).name} — {len(msgs)} message(s)")
        self.rebuild_table()

    def clear_files(self):
        self.messages.clear()
        self.rebuild_table()
        self.say("Liste vidée.")

    def rebuild_table(self):
        self.table.setRowCount(len(self.messages))
        for r, (fname, m) in enumerate(self.messages):
            cells = [fname, str(m.index + 1), m.format_name, f"{m.size} o",
                     str(m.channel) if m.channel else "—", m.status()]
            for c, text in enumerate(cells):
                it = QTableWidgetItem(text)
                if c == 5:
                    ok = m.checksum_ok
                    it.setForeground(Qt.GlobalColor.transparent)
                    from PySide6.QtGui import QColor
                    it.setForeground(QColor(OK if ok else (WARN if ok is None else BAD)))
                self.table.setItem(r, c, it)
        self.table.selectAll()
        self.update_send_button()

    # ── glisser-déposer ─────────────────────────────────────────────────
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.add_paths(paths)

    # ── envoi ───────────────────────────────────────────────────────────
    def send_selected(self):
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        if not rows:
            return
        chosen = [self.messages[r][1] for r in rows]

        bad = [m for m in chosen if m.checksum_ok is False or not m.well_formed]
        if bad:
            r = QMessageBox.warning(
                self, "Messages douteux",
                f"{len(bad)} message(s) ont une somme de contrôle fausse ou sont malformés.\n\n"
                "La machine les refusera probablement, ou chargera un patch corrompu.\n"
                "Envoyer quand même ?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if r != QMessageBox.Yes:
                self.say("Envoi annulé.")
                return

        ch = self.channel.currentData()
        payloads = [set_channel(m.raw, ch) if ch else m.raw for m in chosen]
        if ch:
            self.say(f"Canal forcé à {ch} sur {len(payloads)} message(s).")

        port = self.ports.currentIndex()
        self.say(f"→ envoi de {len(payloads)} message(s) vers « {self.ports.currentText()} »…")
        self.b_send.setEnabled(False)

        self.sender_thread = Sender(port, payloads, self.delay.value())
        self.sender_thread.progress.connect(
            lambda i, t: self.say(f"   {i + 1}/{t} — {len(payloads[i])} o"))
        self.sender_thread.done.connect(self.on_sent)
        self.sender_thread.failed.connect(self.on_failed)
        self.sender_thread.finished.connect(self.update_send_button)
        self.sender_thread.start()

    def send_bank(self, data: bytes):
        """Envoi d'une bank composée dans l'atelier — un seul message, 4104 o."""
        if not self.has_port():
            QMessageBox.warning(self, "Pas de sortie MIDI",
                                "Aucun port MIDI de sortie. Branche la machine, "
                                "puis « Rafraîchir ».")
            return
        if self.sender_thread is not None and self.sender_thread.isRunning():
            self.say("Un envoi est déjà en cours.")
            return

        ch = self.channel.currentData()
        payload = set_channel(data, ch) if ch else data
        m = Message(payload)
        self.say(f"→ atelier : bank de {m.size} o ({m.status()}, canal {m.channel}) "
                 f"vers « {self.ports.currentText()} »…")

        self.b_send.setEnabled(False)
        self.sender_thread = Sender(self.ports.currentIndex(), [payload], 0)
        self.sender_thread.done.connect(self.on_sent)
        self.sender_thread.failed.connect(self.on_failed)
        self.sender_thread.finished.connect(self.update_send_button)
        self.sender_thread.start()

    def on_sent(self, n: int):
        self.say(f"✓ {n} message(s) transmis.")

    def on_failed(self, msg: str):
        self.say(f"✗ {msg}")
        QMessageBox.critical(self, "Échec de l'envoi", msg)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Charon")
    app.setStyleSheet(STYLE)
    w = Charon()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
