"""Atelier de banks — piocher dans deux banks pour en composer une troisième.

Une bank DX7 tient 32 voix de 128 octets. Composer revient à choisir 32 de ces
blocs et à recalculer la somme de contrôle : les voix sont recopiées telles
quelles, jamais réencodées, donc le patch qui arrive dans la machine est
exactement celui qui est parti de la bank d'origine.
"""
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QFileDialog, QAbstractItemView, QMessageBox,
)

from .sysex import (
    Message, read_file, voices, voice_name, build_bank,
    VOICES_PER_BANK, BULK_SIZE,
)


class BankSource(QWidget):
    """Une bank chargée, et ses 32 voix prêtes à être piochées."""

    def __init__(self, label: str):
        super().__init__()
        self.voices: list[bytes] = []
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        head = QHBoxLayout()
        self.title = QLabel(label)
        self.title.setProperty("class", "section")
        head.addWidget(self.title)
        head.addStretch(1)
        v.addLayout(head)

        self.btn = QPushButton("Charger une bank…")
        self.btn.clicked.connect(self.load)
        v.addWidget(self.btn)

        self.file = QLabel("aucune")
        self.file.setObjectName("subtitle")
        self.file.setWordWrap(True)
        v.addWidget(self.file)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        v.addWidget(self.list, 1)

    def load(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir une bank DX7 (bulk 32 voix)", str(Path.home()),
            "SysEx (*.syx *.SYX);;Tous les fichiers (*)")
        if path:
            self.load_path(path)

    def load_path(self, path: str) -> bool:
        try:
            msgs = read_file(path)
        except OSError as exc:
            QMessageBox.warning(self, "Lecture impossible", str(exc))
            return False

        bulks = [m for m in msgs if m.size == BULK_SIZE]
        if not bulks:
            QMessageBox.warning(
                self, "Pas une bank",
                f"{Path(path).name} ne contient aucun bulk 32 voix "
                f"({BULK_SIZE} o).\n\nMessages trouvés : "
                + (", ".join(m.format_name for m in msgs) or "aucun"))
            return False

        m = bulks[0]
        if m.checksum_ok is False:
            r = QMessageBox.warning(
                self, "Somme de contrôle fausse",
                f"{Path(path).name} a une somme de contrôle invalide.\n"
                "Ses voix sont peut-être abîmées. Les charger quand même ?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if r != QMessageBox.Yes:
                return False

        self.voices = voices(m.raw)
        self.file.setText(f"{Path(path).name} — {m.status()}"
                          + (f" · {len(bulks)} banks, la 1re prise" if len(bulks) > 1 else ""))
        self.list.clear()
        for i, vv in enumerate(self.voices):
            self.list.addItem(QListWidgetItem(f"{i + 1:02d} · {voice_name(vv)}"))
        return True

    def selected(self) -> list[tuple[str, bytes]]:
        out = []
        for it in self.list.selectedItems():
            i = self.list.row(it)
            out.append((it.text(), self.voices[i]))
        return out


class Workshop(QWidget):
    """Deux banks à gauche, la bank en construction à droite."""

    log = Signal(str)
    send_requested = Signal(bytes)

    def __init__(self):
        super().__init__()
        self.chosen: list[tuple[str, bytes]] = []
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 8, 0, 0)
        root.setSpacing(10)

        cols = QHBoxLayout()
        cols.setSpacing(10)

        self.a = BankSource("Bank A")
        self.b = BankSource("Bank B")
        cols.addWidget(self.a, 3)
        cols.addWidget(self.b, 3)

        # colonne des flèches
        mid = QVBoxLayout()
        mid.addStretch(1)
        add_a = QPushButton("A →")
        add_a.setToolTip("Ajouter les voix sélectionnées dans la bank A")
        add_a.clicked.connect(lambda: self.take(self.a))
        mid.addWidget(add_a)
        add_b = QPushButton("B →")
        add_b.setToolTip("Ajouter les voix sélectionnées dans la bank B")
        add_b.clicked.connect(lambda: self.take(self.b))
        mid.addWidget(add_b)
        mid.addSpacing(18)
        up = QPushButton("↑")
        up.clicked.connect(lambda: self.move(-1))
        mid.addWidget(up)
        down = QPushButton("↓")
        down.clicked.connect(lambda: self.move(1))
        mid.addWidget(down)
        rm = QPushButton("✕")
        rm.setToolTip("Retirer de la bank en construction")
        rm.clicked.connect(self.remove)
        mid.addWidget(rm)
        mid.addStretch(1)
        cols.addLayout(mid)

        # destination
        dest = QVBoxLayout()
        dest.setSpacing(6)
        head = QHBoxLayout()
        t = QLabel("Bank en construction")
        t.setProperty("class", "section")
        head.addWidget(t)
        head.addStretch(1)
        self.counter = QLabel("0 / 32")
        self.counter.setObjectName("subtitle")
        head.addWidget(self.counter)
        dest.addLayout(head)

        clear = QPushButton("Vider")
        clear.clicked.connect(self.clear)
        dest.addWidget(clear)

        self.hint = QLabel("les emplacements libres seront comblés par une voix muette")
        self.hint.setObjectName("subtitle")
        self.hint.setWordWrap(True)
        dest.addWidget(self.hint)

        self.dest_list = QListWidget()
        self.dest_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        dest.addWidget(self.dest_list, 1)
        cols.addLayout(dest, 3)

        root.addLayout(cols, 1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.b_save = QPushButton("Enregistrer la bank…")
        self.b_save.clicked.connect(self.save)
        actions.addWidget(self.b_save)
        self.b_send = QPushButton("Envoyer vers la machine")
        self.b_send.setObjectName("send")
        self.b_send.clicked.connect(self.send)
        actions.addWidget(self.b_send)
        root.addLayout(actions)

        self.refresh()

    # ── manipulation ────────────────────────────────────────────────────
    def take(self, source: BankSource):
        picked = source.selected()
        if not picked:
            self.log.emit("Rien de sélectionné dans cette bank.")
            return
        libre = VOICES_PER_BANK - len(self.chosen)
        if libre <= 0:
            self.log.emit("La bank est pleine — 32 voix, retire-en avant d'ajouter.")
            return
        if len(picked) > libre:
            self.log.emit(f"{len(picked)} voix choisies, {libre} emplacement(s) libre(s) : "
                          f"les {libre} premières sont prises.")
            picked = picked[:libre]
        self.chosen.extend(picked)
        self.refresh()

    def move(self, delta: int):
        rows = sorted(self.dest_list.row(i) for i in self.dest_list.selectedItems())
        if not rows:
            return
        if delta > 0:
            rows = list(reversed(rows))
        for r in rows:
            t = r + delta
            if not 0 <= t < len(self.chosen):
                continue
            self.chosen[r], self.chosen[t] = self.chosen[t], self.chosen[r]
        self.refresh()
        for r in rows:
            t = r + delta
            if 0 <= t < len(self.chosen):
                self.dest_list.item(t).setSelected(True)

    def remove(self):
        rows = sorted((self.dest_list.row(i) for i in self.dest_list.selectedItems()),
                      reverse=True)
        for r in rows:
            del self.chosen[r]
        self.refresh()

    def clear(self):
        self.chosen.clear()
        self.refresh()

    def refresh(self):
        self.dest_list.clear()
        for i, (label, _) in enumerate(self.chosen):
            self.dest_list.addItem(QListWidgetItem(f"{i + 1:02d} ← {label}"))
        n = len(self.chosen)
        self.counter.setText(f"{n} / {VOICES_PER_BANK}")
        self.b_save.setEnabled(n > 0)
        self.b_send.setEnabled(n > 0)

    # ── sorties ─────────────────────────────────────────────────────────
    def bank(self) -> bytes | None:
        if not self.chosen:
            return None
        try:
            return build_bank([v for _, v in self.chosen])
        except ValueError as exc:
            QMessageBox.critical(self, "Assemblage impossible", str(exc))
            return None

    def save(self):
        data = self.bank()
        if data is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer la bank", str(Path.home() / "bank-custom.syx"),
            "SysEx (*.syx)")
        if not path:
            return
        if not path.lower().endswith(".syx"):
            path += ".syx"
        Path(path).write_bytes(data)
        m = Message(data)
        self.log.emit(f"✓ bank enregistrée : {Path(path).name} — "
                      f"{m.size} o · {m.status()} · {len(self.chosen)} voix choisies"
                      + (f", {VOICES_PER_BANK - len(self.chosen)} muettes"
                         if len(self.chosen) < VOICES_PER_BANK else ""))

    def send(self):
        data = self.bank()
        if data is not None:
            self.send_requested.emit(data)
