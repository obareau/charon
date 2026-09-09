"""Charon — interface de bureau pour envoyer du SysEx vers un Volca FM."""
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QSettings, QTimer
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
/* Palette DX7 (1983) : chassis brun sombre, membrane beige, LCD vert-jaune,
   accent orange. Rien d'ornemental — ce sont les quatre matieres de la machine. */

QMainWindow, QWidget { background: #2B2724; color: #CFC6B6;
    font-family: "IBM Plex Mono", "Menlo", "Consolas", "DejaVu Sans Mono", monospace;
    font-size: 12px; }

/* Le bandeau superieur : serigraphie claire sur le chassis */
QLabel#title { font-size: 19px; font-weight: 700; color: #EFE7D6;
    letter-spacing: .34em; }
QLabel#subtitle { color: #9A8F7E; font-size: 11px; letter-spacing: .04em; }
QLabel[class="section"] { color: #C08A4A; font-size: 10px; font-weight: 700;
    letter-spacing: .16em; }

/* Touches a membrane : beige, legerement bombees */
QPushButton { background: #C6BCA8; border: 1px solid #8E8471;
    border-bottom: 2px solid #7C7260; border-radius: 3px;
    padding: 7px 15px; color: #2B2724; font-size: 11px;
    font-weight: 600; letter-spacing: .06em; }
QPushButton:hover { background: #D4CBB8; }
QPushButton:pressed { background: #ADA391; border-bottom-width: 1px; margin-top: 1px; }
QPushButton:disabled { background: #4A443D; color: #7A7264;
    border-color: #3D372F; border-bottom-color: #3D372F; }

/* L'action principale porte l'orange Yamaha */
QPushButton#send { background: #C2551F; border: 1px solid #8E3C12;
    border-bottom: 2px solid #6E2E0C; color: #FFF1E2; font-weight: 700; }
QPushButton#send:hover { background: #D66327; }
QPushButton#send:pressed { background: #A5460F; }
QPushButton#send:disabled { background: #4A443D; color: #7A7264;
    border-color: #3D372F; border-bottom-color: #3D372F; }

/* Champs encastres dans le chassis */
QComboBox, QSpinBox { background: #211E1B; border: 1px solid #554D43;
    border-radius: 2px; padding: 6px 9px; color: #E4DAC6; }
QComboBox:hover, QSpinBox:hover { border-color: #C08A4A; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView { background: #211E1B; border: 1px solid #554D43;
    selection-background-color: #4E3418; selection-color: #F6E8D5; color: #E4DAC6; }

/* Onglets : intercalaires du panneau */
QTabWidget::pane { border: 1px solid #554D43; border-radius: 3px; top: -1px;
    background: #322D28; }
QTabBar::tab { background: #241F1C; color: #9A8F7E; border: 1px solid #554D43;
    border-bottom: none; padding: 8px 20px; margin-right: 3px;
    border-top-left-radius: 3px; border-top-right-radius: 3px;
    font-size: 11px; letter-spacing: .08em; }
QTabBar::tab:selected { background: #322D28; color: #EFE7D6;
    border-top: 2px solid #C2551F; }

/* Listes et table : fond de panneau, filet orange a la selection */
QTableWidget, QListWidget { background: #211E1B; border: 1px solid #554D43;
    border-radius: 2px; gridline-color: #3A342E;
    selection-background-color: #4E3418; selection-color: #F6E8D5; }
QTableWidget::item:selected, QListWidget::item:selected {
    border-left: 2px solid #C2551F; }
QListWidget::item { padding: 4px 7px; }
QHeaderView::section { background: #3A342E; color: #C08A4A; border: none;
    border-bottom: 1px solid #554D43; padding: 7px; font-size: 10px;
    font-weight: 700; letter-spacing: .12em; }

/* L'ecran : LCD vert-jaune a caracteres sombres, comme sur la machine */
QPlainTextEdit { background: #A9BE55; border: 2px solid #1C1916;
    border-radius: 2px; color: #23300F; padding: 7px;
    font-weight: 600; selection-background-color: #23300F;
    selection-color: #A9BE55; }
"""

OK, WARN, BAD = "#9BC24A", "#E3A72C", "#FF6B4A"


# Un port de bouclage n'est pas une machine : y envoyer un dump ne va nulle part.
# Le dire dans la liste évite le quart d'heure passé à chercher pourquoi le
# Volca ne réagit pas.
LOOPBACK_HINTS = ("midi through", "iac driver", "loopmidi", "loopbe")


def port_label(name: str) -> str:
    if any(h in name.lower() for h in LOOPBACK_HINTS):
        return f"{name}   ⟲ bouclage — ne va vers aucune machine"
    return name


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
        self._known_ports: list[str] = []
        self._build()
        self.refresh_ports(announce=False)

        # Détection à chaud : brancher le Volca doit suffire, sans penser à
        # cliquer « Rafraîchir ». L'énumération est peu coûteuse et la liste
        # n'est reconstruite que si elle a réellement changé.
        self._watch = QTimer(self)
        self._watch.timeout.connect(lambda: self.refresh_ports(announce=True))
        self._watch.start(2000)

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
        self.count = QLabel("")
        self.count.setObjectName("subtitle")
        row.addWidget(self.count)
        b = QPushButton("Rafraîchir")
        b.clicked.connect(lambda: self.refresh_ports(announce=True))
        row.addWidget(b)
        v.addLayout(row)
        self.ports.currentIndexChanged.connect(self.remember_port)

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

    def refresh_ports(self, announce: bool = True):
        """Relit la liste des interfaces MIDI et retrouve celle choisie la dernière fois."""
        try:
            ports = midi.output_ports()
        except Exception as exc:                    # noqa: BLE001
            self.say(f"⚠ impossible de lister les ports : {exc}")
            ports = []

        if ports == self._known_ports:
            return                                   # rien n'a bougé
        appeared = [p for p in ports if p not in self._known_ports]
        vanished = [p for p in self._known_ports if p not in ports]
        self._known_ports = ports

        wanted = self.ports.currentData() or self._saved_port()
        self.ports.blockSignals(True)
        self.ports.clear()
        if ports:
            for name in ports:
                self.ports.addItem(port_label(name), name)
            idx = self.ports.findData(wanted)
            self.ports.setCurrentIndex(idx if idx >= 0 else 0)
        else:
            self.ports.addItem("aucune interface MIDI détectée", None)
        self.ports.blockSignals(False)

        self.count.setText(f"{len(ports)} interface(s)" if ports else "")
        if announce:
            for p in appeared:
                self.say(f"＋ interface branchée : {p}")
            for p in vanished:
                self.say(f"－ interface débranchée : {p}")
        self.update_send_button()

    # Le choix survit à la fermeture : en studio on rebranche toujours la même
    # interface, la redemander à chaque lancement est une corvée inutile.
    def _saved_port(self):
        return QSettings("robotariis", "charon").value("port")

    def remember_port(self):
        name = self.ports.currentData()
        if name:
            QSettings("robotariis", "charon").setValue("port", name)

    def port_index(self) -> int | None:
        """Index rtmidi de l'interface choisie, résolu par son nom.

        Résolu au moment de l'envoi, jamais mémorisé : un branchement entre le
        choix et le clic décalerait les index, et le dump partirait vers la
        mauvaise machine.
        """
        name = self.ports.currentData()
        if not name:
            return None
        try:
            return midi.output_ports().index(name)
        except ValueError:
            return None

    def has_port(self) -> bool:
        return self.ports.currentData() is not None

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

        port = self.port_index()
        if port is None:
            self.say("✗ l'interface choisie a disparu — rebranche-la ou choisis-en une autre.")
            return
        self.say(f"→ envoi de {len(payloads)} message(s) vers « {self.ports.currentData()} »…")
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
                 f"vers « {self.ports.currentData()} »…")

        port = self.port_index()
        if port is None:
            self.say("✗ l'interface choisie a disparu — rebranche-la ou choisis-en une autre.")
            return
        self.b_send.setEnabled(False)
        self.sender_thread = Sender(port, [payload], 0)
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
