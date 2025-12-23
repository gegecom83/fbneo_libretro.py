import sys
import os
import subprocess
import json
import time
from pathlib import Path
import xml.etree.ElementTree as ET
import warnings

# Suppress pkg_resources deprecation warning from pygame dependencies
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pkg_resources")

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QLineEdit, QPushButton, QLabel, QFileDialog, QMessageBox,
    QDialog, QFormLayout, QComboBox, QGroupBox, QScrollArea, QSizePolicy,
    QTabWidget, QSplitter, QCheckBox, QMenu
)
from PyQt6.QtCore import QTimer, Qt, QEvent
from PyQt6.QtGui import QIcon, QPixmap

import pygame

TAB_CONFIGS = [
    {"name": "Arcade", "rom_titles_file": "rom_titles_arcade.txt"},
    {"name": "CBS ColecoVision", "rom_titles_file": "rom_titles_coleco.txt"},
    {"name": "Fairchild ChannelF", "rom_titles_file": "rom_titles_channelf.txt"},
    {"name": "MSX 1", "rom_titles_file": "rom_titles_msx.txt"},
    {"name": "Nec PC-Engine", "rom_titles_file": "rom_titles_pce.txt"},
    {"name": "Nec SuperGrafX", "rom_titles_file": "rom_titles_sgx.txt"},
    {"name": "Nec TurboGrafx-16", "rom_titles_file": "rom_titles_tg16.txt"},
    {"name": "Nintendo Entertainment System", "rom_titles_file": "rom_titles_nes.txt"},
    {"name": "Nintendo Family Disk System", "rom_titles_file": "rom_titles_fds.txt"},
    {"name": "Super Nintendo Entertainment System", "rom_titles_file": "rom_titles_snes.txt"},
    {"name": "Sega GameGear", "rom_titles_file": "rom_titles_gamegear.txt"},
    {"name": "Sega Master System", "rom_titles_file": "rom_titles_sms.txt"},
    {"name": "Sega Megadrive", "rom_titles_file": "rom_titles_megadrive.txt"},
    {"name": "Sega SG-1000", "rom_titles_file": "rom_titles_sg1000.txt"},
    {"name": "SNK Neo-Geo Pocket", "rom_titles_file": "rom_titles_ngp.txt"},
    {"name": "SNK Neo-Geo CD", "rom_titles_file": "rom_titles_neocd.txt"},
    {"name": "ZX Spectrum", "rom_titles_file": "rom_titles_spectrum.txt"}
]

CONFIG_FILE = Path("config.json")
DEFAULT_CONFIG = {
    "RETROARCH": "",
    "RETROARCH_CORE": "",
    "roms_dirs": {config["name"]: "" for config in TAB_CONFIGS},
    "xml_dat_files": {config["name"]: "" for config in TAB_CONFIGS},
    "title_image_dirs": {config["name"]: "" for config in TAB_CONFIGS},
    "preview_image_dirs": {config["name"]: "" for config in TAB_CONFIGS},
    "joystick_config": {
        "hat_scroll_cooldown": 0.08,
        "hat_fastest_steps": 10,
        "hat_fastest_delay": 0.02,
        "button_up": 2,
        "button_down": 3,
        "button_select": 0,
        "button_favorites": 7,
        "button_prev_tab": 4,
        "button_next_tab": 5
    },
    "display_only_rom_list": False,
    "hide_clones": False,
    "favorites": []
}

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        jc = cfg.get("joystick_config", {})
        jc.setdefault("hat_fastest_steps", 10)
        jc.setdefault("hat_fastest_delay", 0.02)
        cfg["joystick_config"] = jc
        for k in ["xml_dat_files", "title_image_dirs", "preview_image_dirs"]:
            if k not in cfg:
                cfg[k] = {config["name"]: "" for config in TAB_CONFIGS}
        if "display_only_rom_list" not in cfg:
            cfg["display_only_rom_list"] = False
        if "hide_clones" not in cfg:
            cfg["hide_clones"] = False
        if "favorites" not in cfg:
            cfg["favorites"] = []
        return cfg
    else:
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4)

def load_rom_titles(filename: str):
    rom_titles = {}
    if not os.path.exists(filename):
        return rom_titles
    with open(filename, "r", encoding="utf-8") as file:
        for line in file:
            parts = line.strip().split(maxsplit=1)
            if len(parts) >= 2:
                key = parts[0].lower()
                title = parts[1].strip('"')
                if not title or title.lower() in {"untitled", "unknown", "no title"}:
                    continue
                rom_titles[key] = title
    return rom_titles

def parse_dat_metadata(xml_path):
    """
    Parse the XML/DAT file and return a meta dictionary excluding <game isbios="yes"> entries.
    Each entry maps rom name -> (title, year, manufacturer, is_clone).
    """
    meta = {}
    if not xml_path or not os.path.exists(xml_path):
        return meta
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        for entry in root.findall(".//game") + root.findall(".//machine"):
            if entry.attrib.get("isbios", "no") == "yes":
                continue
            name = entry.attrib.get("name") or entry.attrib.get("romname") or ""
            title_node = entry.find("description")
            year_node = entry.find("year")
            manuf_node = entry.find("manufacturer")
            title = title_node.text.strip() if title_node is not None and title_node.text else name
            year = year_node.text.strip() if year_node is not None and year_node.text else ""
            manuf = manuf_node.text.strip() if manuf_node is not None and manuf_node.text else ""
            is_clone = "cloneof" in entry.attrib
            if name:
                meta[name.lower()] = (title, year, manuf, is_clone)
    except Exception as e:
        print(f"Failed to parse {xml_path}: {e}")
    return meta

ROM_HIDE_LIST = {"neocdz", "rom_to_hide2"}

def find_file_case_insensitive(directory, filename):
    if not directory or not os.path.isdir(directory):
        return None
    for f in os.listdir(directory):
        if f.lower() == filename.lower():
            return os.path.join(directory, f)
    return None

def get_rom_list_cached(rom_titles_file, roms_dir, system_name, xml_dat_file, cache_dict):
    cache_key = (roms_dir, system_name, xml_dat_file)
    cache = cache_dict.get(cache_key)
    if cache is not None:
        return cache
    rom_titles = load_rom_titles(rom_titles_file)
    meta = parse_dat_metadata(xml_dat_file) if xml_dat_file else {}
    if not roms_dir or not os.path.exists(roms_dir):
        cache_dict[cache_key] = []
        return []
    roms = []
    if system_name == "SNK Neo-Geo CD":
        for root, _, files in os.walk(roms_dir):
            for f in files:
                if f.lower().endswith('.cue'):
                    rel_path = os.path.relpath(os.path.join(root, f), roms_dir)
                    roms.append(rel_path)
    else:
        roms = [
            f for f in os.listdir(roms_dir)
            if os.path.isfile(os.path.join(roms_dir, f)) and f.lower().endswith(('.zip', '.7z', '.cue'))
        ]
    rom_list = []
    for rom in roms:
        stem = Path(rom).stem
        if stem.lower() in ROM_HIDE_LIST:
            continue
        if system_name == "SNK Neo-Geo CD":
            if stem.lower() in meta:
                title, year, manuf, is_clone = meta[stem.lower()]
            else:
                title = rom_titles.get(stem.lower(), stem)
                year, manuf, is_clone = "", "", False
            rom_list.append((rom, title, year, manuf, is_clone))
        else:
            if meta and stem.lower() not in meta:
                continue
            if stem.lower() in meta:
                title, year, manuf, is_clone = meta[stem.lower()]
            else:
                title = rom_titles.get(stem.lower(), stem)
                year, manuf, is_clone = "", "", False
            rom_list.append((rom, title, year, manuf, is_clone))
    rom_list_sorted = sorted(rom_list, key=lambda x: x[1].lower())
    cache_dict[cache_key] = rom_list_sorted
    return rom_list_sorted

def filter_rom_list(rom_list, search="", year_filter="", manuf_filter="", hide_clones=False):
    filtered = []
    for rom, title, year, manuf, is_clone in rom_list:
        if hide_clones and is_clone:
            continue
        if year_filter and year_filter not in year:
            continue
        if manuf_filter and manuf_filter.lower() not in manuf.lower():
            continue
        if not search or search in title.lower():
            filtered.append((rom, title, year, manuf, is_clone))
    return filtered

def run_rom(rom, roms_dir, retroarch, core, system_name, win):
    rom_path = os.path.join(roms_dir, rom)
    if not os.path.exists(rom_path):
        QMessageBox.critical(win, "Error", f"ROM file not found: {rom_path}")
        return
    if not os.path.exists(retroarch) or not os.access(retroarch, os.X_OK):
        QMessageBox.critical(win, "Error", f"Invalid RetroArch executable: {retroarch}")
        return
    if not os.path.exists(core):
        QMessageBox.critical(win, "Error", f"Invalid RetroArch core: {core}")
        return
    if not (core.lower().endswith(".dll") or core.lower().endswith(".so") or core.lower().endswith(".dylib")):
        QMessageBox.critical(
            win,
            "Error",
            f"Core file must end with .dll (Windows), .so (Linux), or .dylib (macOS): {core}"
        )
        return
    cmd = [retroarch, "-L", core]
    if system_name == "SNK Neo-Geo CD" or rom.lower().endswith(".cue"):
        cmd.extend(["--subsystem", "neocd"])
    cmd.append(rom_path)
    try:
        subprocess.Popen(cmd)
    except Exception as e:
        QMessageBox.critical(win, "Error", f"Failed to launch ROM: {e}")

class FavoritesDialog(QDialog):
    def __init__(self, cfg, parent=None, current_system_callback=None):
        super().__init__(parent)
        self.setWindowTitle("Favorite ROMs")
        self.cfg = cfg
        self.current_system_callback = current_system_callback
        self.layout = QVBoxLayout(self)

        self.favorites_list = QListWidget()
        self.favorites_list.setMinimumWidth(420)
        self.favorites_list.itemDoubleClicked.connect(self.launch_selected_favorite)
        self.favorites_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.favorites_list.customContextMenuRequested.connect(self.show_context_menu)
        self.favorites_list.installEventFilter(self)
        self.layout.addWidget(self.favorites_list)

        self.update_favorites_list()
        self.setMinimumSize(460, 420)

        self.joystick = pygame.joystick.Joystick(0) if pygame.joystick.get_count() > 0 else None
        if self.joystick:
            self.joystick.init()
        self.last_hat = (0, 0)
        self.last_hat_held = {"left": False, "right": False, "up": False, "down": False}
        self.last_hat_held_time = {"left": 0, "right": 0, "up": 0, "down": 0}
        self.last_button_states = {}
        self.last_button_times = {}
        self.debounce_delay = self.cfg["joystick_config"].get("button_debounce_delay", 200)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_joystick)
        self.timer.start(200)
        self.polling_interval = 50

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.favorites_list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.favorites_list.setFocus()

    def update_favorites_list(self):
        self.favorites_list.clear()
        for fav in self.cfg["favorites"]:
            if len(fav) == 4:
                system_name, rom, title, year = fav
                manuf = ""
            else:
                system_name, rom, title, year, manuf = fav[:5]
            display = f"{title} [{system_name}]"
            if year or manuf:
                display += f" [{year}]" if year else ""
                display += f" ({manuf})" if manuf else ""
            self.favorites_list.addItem(display)

    def launch_selected_favorite(self, *args):
        idx = self.favorites_list.currentRow()
        if idx < 0 or not self.cfg["favorites"]:
            QMessageBox.critical(self, "Warning", "Select a favorite ROM.")
            return
        fav = self.cfg["favorites"][idx]
        if len(fav) == 4:
            system_name, rom, title, _ = fav
        else:
            system_name, rom, title, _, _ = fav[:5]
        roms_dir = self.cfg["roms_dirs"].get(system_name, "")
        run_rom(rom, roms_dir, self.cfg["RETROARCH"], self.cfg["RETROARCH_CORE"], system_name, self)

    def show_context_menu(self, position):
        idx = self.favorites_list.currentRow()
        if idx < 0 or not self.cfg["favorites"]:
            return
        menu = QMenu()
        remove_from_favorites = menu.addAction("Remove from Favorites")
        action = menu.exec(self.favorites_list.mapToGlobal(position))
        if action == remove_from_favorites:
            self.remove_selected_favorite(idx)

    def remove_selected_favorite(self, idx):
        if idx < 0 or not self.cfg["favorites"]:
            QMessageBox.critical(self, "Warning", "Select a favorite ROM to remove.")
            return
        fav = self.cfg["favorites"][idx]
        if len(fav) == 4:
            title = fav[2]
        else:
            title = fav[2]
        self.cfg["favorites"].pop(idx)
        save_config(self.cfg)
        self.update_favorites_list()
        QMessageBox.information(self, "Favorites", f"Removed '{title}' from favorites.")

    def poll_joystick(self):
        if not self.isActiveWindow():
            return
        pygame.event.pump()
        jc = self.cfg["joystick_config"]
        scroll_cooldown = jc.get("hat_scroll_cooldown", 0.08) * 1000
        now = time.time() * 1000
        list_widget = self.favorites_list
        idx = list_widget.currentRow()
        size = list_widget.count()

        def scroll_list(direction, steps, held_key, held_time_key):
            if direction:
                time_elapsed = now - self.last_hat_held_time.get(held_key, 0)
                if not self.last_hat_held.get(held_key, False) or time_elapsed >= scroll_cooldown:
                    new_idx = max(0, idx - steps) if held_key == "up" else min(size - 1, idx + steps)
                    list_widget.setCurrentRow(new_idx)
                    self.last_hat_held_time[held_key] = now
                    self.last_hat_held[held_key] = True
            else:
                self.last_hat_held[held_key] = False

        if self.joystick and self.joystick.get_numhats() > 0:
            hat = self.joystick.get_hat(0)
            hat_up = hat[1] == 1
            hat_down = hat[1] == -1

            scroll_list(hat_up, 1, "up", "up")
            scroll_list(hat_down, 1, "down", "down")

            self.last_hat = hat

        def check_button(btn_key, action):
            idx = jc.get(btn_key, -1)
            if idx < 0 or idx >= self.joystick.get_numbuttons():
                return
            pressed = self.joystick.get_button(idx)
            last_state = self.last_button_states.get(btn_key, False)
            last_time = self.last_button_times.get(btn_key, 0)
            if pressed and not last_state:
                if now - last_time >= self.debounce_delay:
                    action()
                    self.last_button_times[btn_key] = now
            elif not pressed and last_state:
                self.last_button_times[btn_key] = now
            self.last_button_states[btn_key] = pressed

        if self.joystick:
            check_button("button_up", lambda: self.favorites_list.setCurrentRow(max(0, self.favorites_list.currentRow() - 1)))
            check_button("button_down", lambda: self.favorites_list.setCurrentRow(min(self.favorites_list.count() - 1, self.favorites_list.currentRow() + 1)))
            check_button("button_select", self.launch_selected_favorite)
            check_button("button_favorites", self.close)

        self.timer.start(self.polling_interval)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress and obj == self.favorites_list:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.launch_selected_favorite()
                return True
        return super().eventFilter(obj, event)

class SettingsDialog(QDialog):
    def __init__(self, cfg, parent, current_system_callback, update_rom_list_callback):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.cfg = cfg
        self.current_system_callback = current_system_callback
        self.update_rom_list_callback = update_rom_list_callback

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        main_widget = QWidget()
        scroll.setWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        general_group = QGroupBox("General")
        general_layout = QFormLayout()
        self.retroarch_edit = QLineEdit(str(cfg["RETROARCH"]))
        self.retroarch_btn = QPushButton("Choose...")
        self.retroarch_btn.setMaximumWidth(80)
        self.retroarch_btn.clicked.connect(self.choose_retroarch)
        retroarch_row = QHBoxLayout()
        retroarch_row.addWidget(self.retroarch_edit)
        retroarch_row.addWidget(self.retroarch_btn)

        self.core_edit = QLineEdit(str(cfg["RETROARCH_CORE"]))
        self.core_btn = QPushButton("Choose...")
        self.core_btn.setMaximumWidth(80)
        self.core_btn.clicked.connect(self.choose_core)
        core_row = QHBoxLayout()
        core_row.addWidget(self.core_edit)
        core_row.addWidget(self.core_btn)
        core_hint = QLabel("(RetroArch/cores/fbneo_libretro*.dll/*.so)")
        core_hint.setStyleSheet("color: gray; font-size: 10pt; margin-bottom: 6px;")
        core_hint.setContentsMargins(0, 0, 0, 4)

        general_layout.addRow("RetroArch Executable:", retroarch_row)
        general_layout.addRow("RetroArch Core:", core_row)
        general_layout.addRow("", core_hint)
        general_group.setLayout(general_layout)

        joystick_group = QGroupBox("Joystick Buttons")
        joystick_layout = QFormLayout()
        jc = cfg["joystick_config"]
        self.hat_scroll_cooldown = QLineEdit(str(jc.get("hat_scroll_cooldown", 0.08)))
        self.hat_fastest_steps = QLineEdit(str(jc.get("hat_fastest_steps", 10)))
        self.hat_fastest_delay = QLineEdit(str(jc.get("hat_fastest_delay", 0.02)))
        self.button_up = QLineEdit(str(jc.get("button_up", 2)))
        self.button_down = QLineEdit(str(jc.get("button_down", 3)))
        self.button_select = QLineEdit(str(jc.get("button_select", 0)))
        self.button_favorites = QLineEdit(str(jc.get("button_favorites", 7)))
        self.button_prev_tab = QLineEdit(str(jc.get("button_prev_tab", 4)))
        self.button_next_tab = QLineEdit(str(jc.get("button_next_tab", 5)))
        joystick_layout.addRow("Hat Scroll Cooldown (s):", self.hat_scroll_cooldown)
        joystick_layout.addRow("Hat Fastest Steps (hold):", self.hat_fastest_steps)
        joystick_layout.addRow("Hat Fastest Delay (s):", self.hat_fastest_delay)
        joystick_layout.addRow("Button Up Index:", self.button_up)
        joystick_layout.addRow("Button Down Index:", self.button_down)
        joystick_layout.addRow("Button Select Index:", self.button_select)
        joystick_layout.addRow("Button Favorites Index:", self.button_favorites)
        joystick_layout.addRow("Button Prev System Index:", self.button_prev_tab)
        joystick_layout.addRow("Button Next System Index:", self.button_next_tab)
        joystick_group.setLayout(joystick_layout)

        sys_group = QGroupBox("System")
        sys_layout = QFormLayout()
        self.sys_dropdown = QComboBox()
        self.sys_dropdown.addItems([config["name"] for config in TAB_CONFIGS])
        self.sys_dropdown.currentIndexChanged.connect(self.update_sys_fields)
        sys_layout.addRow("System:", self.sys_dropdown)

        self.rom_folder_edit = QLineEdit()
        self.rom_folder_btn = QPushButton("Choose...")
        self.rom_folder_btn.setMaximumWidth(80)
        self.rom_folder_btn.clicked.connect(self.choose_rom_folder)
        rom_folder_row = QHBoxLayout()
        rom_folder_row.addWidget(self.rom_folder_edit)
        rom_folder_row.addWidget(self.rom_folder_btn)
        sys_layout.addRow("ROMs Folder:", rom_folder_row)

        self.xml_file_edit = QLineEdit()
        self.xml_file_btn = QPushButton("Choose...")
        self.xml_file_btn.setMaximumWidth(80)
        self.xml_file_btn.clicked.connect(self.choose_xml_file)
        xml_file_row = QHBoxLayout()
        xml_file_row.addWidget(self.xml_file_edit)
        xml_file_row.addWidget(self.xml_file_btn)
        sys_layout.addRow("XML/DAT File:", xml_file_row)

        self.title_img_edit = QLineEdit()
        self.title_img_btn = QPushButton("Choose...")
        self.title_img_btn.setMaximumWidth(80)
        self.title_img_btn.clicked.connect(self.choose_title_img_folder)
        title_img_row = QHBoxLayout()
        title_img_row.addWidget(self.title_img_edit)
        title_img_row.addWidget(self.title_img_btn)
        sys_layout.addRow("Title Image Folder:", title_img_row)

        self.preview_img_edit = QLineEdit()
        self.preview_img_btn = QPushButton("Choose...")
        self.preview_img_btn.setMaximumWidth(80)
        self.preview_img_btn.clicked.connect(self.choose_preview_img_folder)
        preview_img_row = QHBoxLayout()
        preview_img_row.addWidget(self.preview_img_edit)
        preview_img_row.addWidget(self.preview_img_btn)
        sys_layout.addRow("Preview Image Folder:", preview_img_row)

        self.display_only_rom_list_chk = QCheckBox("Display only the ROM list (hide title/preview tabs)")
        self.display_only_rom_list_chk.setChecked(cfg.get("display_only_rom_list", False))
        sys_layout.addRow(self.display_only_rom_list_chk)

        sys_group.setLayout(sys_layout)

        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.save)

        layout.addWidget(general_group)
        layout.addWidget(joystick_group)
        layout.addWidget(sys_group)
        layout.addWidget(self.save_btn)

        dlg_layout = QVBoxLayout(self)
        dlg_layout.addWidget(scroll)
        self.setLayout(dlg_layout)

        self.update_sys_fields(self.sys_dropdown.currentIndex())
        self.setMinimumSize(460, 500)

    def choose_retroarch(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Select RetroArch Executable", "", "All Files (*)")
        if fname:
            self.retroarch_edit.setText(fname)

    def choose_core(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Select RetroArch Core", "", "All Files (*)")
        if fname:
            self.core_edit.setText(fname)

    def update_sys_fields(self, idx):
        sys_name = self.sys_dropdown.currentText()
        self.rom_folder_edit.setText(str(self.cfg["roms_dirs"].get(sys_name, "")))
        self.xml_file_edit.setText(str(self.cfg["xml_dat_files"].get(sys_name, "")))
        self.title_img_edit.setText(str(self.cfg["title_image_dirs"].get(sys_name, "")))
        self.preview_img_edit.setText(str(self.cfg["preview_image_dirs"].get(sys_name, "")))

    def choose_rom_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select ROMs Folder")
        if folder:
            self.rom_folder_edit.setText(folder)

    def choose_xml_file(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Select XML/DAT File", "", "XML/DAT Files (*.xml *.dat);;All Files (*)")
        if fname:
            self.xml_file_edit.setText(fname)

    def choose_title_img_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Title Image Folder")
        if folder:
            self.title_img_edit.setText(folder)

    def choose_preview_img_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Preview Image Folder")
        if folder:
            self.preview_img_edit.setText(folder)

    def save(self):
        self.cfg["RETROARCH"] = self.retroarch_edit.text()
        self.cfg["RETROARCH_CORE"] = self.core_edit.text()
        jc = self.cfg["joystick_config"]
        try:
            jc["hat_scroll_cooldown"] = float(self.hat_scroll_cooldown.text())
            jc["hat_fastest_steps"] = int(self.hat_fastest_steps.text())
            jc["hat_fastest_delay"] = float(self.hat_fastest_delay.text())
            jc["button_up"] = int(self.button_up.text())
            jc["button_down"] = int(self.button_down.text())
            jc["button_select"] = int(self.button_select.text())
            jc["button_favorites"] = int(self.button_favorites.text())
            jc["button_prev_tab"] = int(self.button_prev_tab.text())
            jc["button_next_tab"] = int(self.button_next_tab.text())
        except Exception:
            pass
        sys_name = self.sys_dropdown.currentText()
        self.cfg["roms_dirs"][sys_name] = self.rom_folder_edit.text()
        self.cfg["xml_dat_files"][sys_name] = self.xml_file_edit.text()
        self.cfg["title_image_dirs"][sys_name] = self.title_img_edit.text()
        self.cfg["preview_image_dirs"][sys_name] = self.preview_img_edit.text()
        self.cfg["display_only_rom_list"] = self.display_only_rom_list_chk.isChecked()
        save_config(self.cfg)
        self.update_rom_list_callback()
        self.accept()

class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About")
        layout = QHBoxLayout(self)

        logo_label = QLabel()
        icon_path = "icon.ico" if sys.platform.startswith("win") else "icon.png"
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path)
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                logo_label.setPixmap(scaled_pixmap)
        logo_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(logo_label)

        text_label = QLabel(
            "The MIT License (MIT)\n"
            "Copyright (c) 2025 FinalBurn Neo [Libretro] v2.1.0\n"
            "https://github.com/gegecom83/fbneo_libretro.py"
        )
        text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(text_label, stretch=1)

        self.setLayout(layout)
        self.setMinimumSize(400, 120)

class AspectRatioLabel(QLabel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pixmap = None
        self._placeholder_text = "image not available"
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText(self._placeholder_text)

    def setPixmap(self, pixmap):
        self._pixmap = pixmap
        if pixmap and not pixmap.isNull():
            self.setText("")
            self._scale_pixmap()
        else:
            self._pixmap = None
            super().setPixmap(QPixmap())
            self.setText(self._placeholder_text)
        self.update()

    def _scale_pixmap(self):
        if not self._pixmap or self._pixmap.isNull():
            return
        available_size = self.size()
        parent = self.parent()
        if parent and isinstance(parent, QTabWidget):
            available_size = parent.size()
        max_width = min(available_size.width(), 640)
        max_height = min(available_size.height(), 480)
        scaled_pixmap = self._pixmap.scaled(
            max_width,
            max_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        super().setPixmap(scaled_pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._pixmap and not self._pixmap.isNull():
            self._scale_pixmap()
        else:
            super().setPixmap(QPixmap())
            self.setText(self._placeholder_text)
        self.update()

    def clear(self):
        self._pixmap = None
        super().setPixmap(QPixmap())
        self.setText(self._placeholder_text)
        self.update()

class MainWindow(QMainWindow):
    SYSTEM_IMAGE_PREFIXES = {
        "CBS ColecoVision": "cv_",
        "Fairchild ChannelF": "chf_",
        "MSX 1": "msx_",
        "Nec PC-Engine": "pce_",
        "Nec SuperGrafX": "sgx_",
        "Nec TurboGrafx-16": "tg_",
        "Nintendo Entertainment System": "nes_",
        "Nintendo Family Disk System": "fds_",
        "Super Nintendo Entertainment System": "snes_",
        "Sega GameGear": "gg_",
        "Sega Master System": "sms_",
        "Sega Megadrive": "md_",
        "Sega SG-1000": "sg1k_",
        "SNK Neo-Geo Pocket": "ngp_",
        "ZX Spectrum": "spec_"
    }

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FinalBurn Neo [Libretro] • Select Game")
        if sys.platform.startswith("win") and os.path.exists("icon.ico"):
            self.setWindowIcon(QIcon("icon.ico"))
        elif sys.platform.startswith("linux") and os.path.exists("icon.png"):
            self.setWindowIcon(QIcon("icon.png"))

        self.cfg = load_config()
        self.is_active = True
        self.favorites_dialog = None

        self.systems_combo = QComboBox()
        self.systems_combo.addItems([c["name"] for c in TAB_CONFIGS])
        self.systems_combo.currentIndexChanged.connect(self.update_rom_list)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search ROMs...")
        self.search_edit.textChanged.connect(self.update_rom_list)

        self.year_edit = QLineEdit()
        self.year_edit.setPlaceholderText("Year")
        self.year_edit.setMaximumWidth(80)
        self.year_edit.textChanged.connect(self.update_rom_list)

        self.manuf_edit = QLineEdit()
        self.manuf_edit.setPlaceholderText("Manufacturer")
        self.manuf_edit.setMaximumWidth(150)
        self.manuf_edit.textChanged.connect(self.update_rom_list)

        self.roms_list = QListWidget()
        self.roms_list.setMinimumWidth(420)
        self.roms_list.itemDoubleClicked.connect(self.launch_selected_rom)
        self.roms_list.installEventFilter(self)
        self.roms_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.roms_list.customContextMenuRequested.connect(self.show_context_menu)

        self.rom_count_label = QLabel()
        self.rom_count_label.setSizePolicy(self.rom_count_label.sizePolicy().horizontalPolicy(), self.rom_count_label.sizePolicy().verticalPolicy())

        self.hide_clones_chk = QCheckBox("Hide Clones")
        self.hide_clones_chk.setChecked(self.cfg.get("hide_clones", False))
        self.hide_clones_chk.toggled.connect(self.toggle_hide_clones)

        self.settings_btn = QPushButton("Settings")
        self.settings_btn.setMaximumWidth(80)
        self.settings_btn.setMinimumHeight(24)
        self.settings_btn.clicked.connect(self.show_settings)

        self.favorites_btn = QPushButton("Favorites")
        self.favorites_btn.setMaximumWidth(80)
        self.favorites_btn.setMinimumHeight(24)
        self.favorites_btn.clicked.connect(self.show_favorites)

        settings_row = QHBoxLayout()
        settings_row.addWidget(self.rom_count_label)
        settings_row.addStretch(1)
        settings_row.addWidget(self.hide_clones_chk)
        settings_row.addWidget(self.favorites_btn)
        settings_row.addWidget(self.settings_btn)

        layout = QVBoxLayout()
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("System:"))
        top_row.addWidget(self.systems_combo)
        top_row.addWidget(QLabel("Search:"))
        top_row.addWidget(self.search_edit)
        top_row.addWidget(QLabel("Year:"))
        top_row.addWidget(self.year_edit)
        top_row.addWidget(QLabel("Manufacturer:"))
        top_row.addWidget(self.manuf_edit)
        layout.addLayout(top_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.roms_list)

        self.img_tabs = QTabWidget()
        self.title_img_label = AspectRatioLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.title_img_label.setMinimumSize(200, 150)
        self.title_img_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.title_img_label.setScaledContents(False)
        self.preview_img_label = AspectRatioLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.preview_img_label.setMinimumSize(200, 150)
        self.preview_img_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_img_label.setScaledContents(False)
        self.img_tabs.addTab(self.title_img_label, "Title")
        self.img_tabs.addTab(self.preview_img_label, "Preview")
        splitter.addWidget(self.img_tabs)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([600, 300])

        layout.addWidget(splitter)
        layout.addLayout(settings_row)
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        self.roms = []
        self.rom_cache = {}
        self.roms_list.currentRowChanged.connect(self.update_image_tabs)
        self.update_rom_list()

        pygame.init()
        pygame.joystick.init()
        self.joystick = pygame.joystick.Joystick(0) if pygame.joystick.get_count() > 0 else None
        if self.joystick:
            self.joystick.init()
        self.last_hat = (0, 0)
        self.last_hat_held = {"left": False, "right": False, "up": False, "down": False}
        self.last_hat_held_time = {"left": 0, "right": 0, "up": 0, "down": 0}
        self.last_key_held = {"left": False, "right": False}
        self.last_key_held_time = {"left": 0, "right": 0}
        self.last_button_states = {}
        self.last_button_times = {}
        self.debounce_delay = 200
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_joystick)
        self.timer.start(20)

        self.is_fullscreen = False
        self.installEventFilter(self)
        self.roms_list.installEventFilter(self)

        self.activateWindow()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.roms_list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.roms_list.setFocus()
        self.adjust_main_window_size()

        self.img_tabs.setVisible(not self.cfg.get("display_only_rom_list", False))

    def adjust_main_window_size(self):
        self.setMinimumSize(400, 320)
        self.resize(self.sizeHint())
        self.setMaximumSize(16777215, 16777215)

    def toggle_hide_clones(self, checked):
        self.cfg["hide_clones"] = checked
        save_config(self.cfg)
        self.update_rom_list()

    def show_about(self):
        dlg = AboutDialog(self)
        dlg.exec()

    def show_favorites(self):
        if self.favorites_dialog is None:
            self.favorites_dialog = FavoritesDialog(self.cfg, self, self.current_system)
            self.favorites_dialog.finished.connect(self.on_favorites_dialog_closed)
            self.favorites_dialog.exec()
        else:
            self.favorites_dialog.close()

    def on_favorites_dialog_closed(self):
        self.favorites_dialog = None

    def show_context_menu(self, position):
        idx = self.roms_list.currentRow()
        if idx < 0 or not self.roms or self.roms_list.item(idx).text() == "No ROMs found.":
            return

        menu = QMenu()
        add_to_favorites = menu.addAction("Add to Favorites")
        action = menu.exec(self.roms_list.mapToGlobal(position))

        if action == add_to_favorites:
            self.add_to_favorites(idx)

    def add_to_favorites(self, idx):
        sys_cfg, _ = self.current_system()
        sys_name = sys_cfg["name"]
        rom, title, year, manuf, is_clone = self.roms[idx]
        favorite = (sys_name, rom, title, year, manuf)
        if favorite not in self.cfg["favorites"]:
            self.cfg["favorites"].append(favorite)
            save_config(self.cfg)
            QMessageBox.information(self, "Favorites", f"Added '{title}' to favorites.")

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.WindowActivate:
            self.is_active = True
        elif event.type() == QEvent.Type.WindowDeactivate:
            self.is_active = False
        if event.type() == QEvent.Type.KeyPress and obj == self.roms_list:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.launch_selected_rom()
                return True
            if event.key() == Qt.Key.Key_F11:
                self.toggle_fullscreen()
                return True
            if event.key() == Qt.Key.Key_Tab and not isinstance(self.focusWidget(), QLineEdit):
                self.show_about()
                return True
            if event.key() == Qt.Key.Key_Left:
                self.last_key_held["left"] = True
                self.last_key_held_time["left"] = time.time() * 1000
                return True
            if event.key() == Qt.Key.Key_Right:
                self.last_key_held["right"] = True
                self.last_key_held_time["right"] = time.time() * 1000
                return True
        elif event.type() == QEvent.Type.KeyRelease and obj == self.roms_list:
            if event.key() == Qt.Key.Key_Left:
                self.last_key_held["left"] = False
                return True
            if event.key() == Qt.Key.Key_Right:
                self.last_key_held["right"] = False
                return True
        return super().eventFilter(obj, event)

    def toggle_fullscreen(self):
        if self.is_fullscreen:
            self.showNormal()
            self.is_fullscreen = False
        else:
            self.showFullScreen()
            self.is_fullscreen = True

    def update_image_tabs(self):
        idx = self.roms_list.currentRow()
        if idx < 0 or not self.roms or self.roms_list.item(idx).text() == "No ROMs found.":
            self.title_img_label.setPixmap(None)
            self.preview_img_label.setPixmap(None)
            return
        rom = self.roms[idx][0]
        sys_cfg = self.current_system()[0]
        sys_name = sys_cfg["name"]
        prefix = self.SYSTEM_IMAGE_PREFIXES.get(sys_name, "")
        base_name = Path(rom).stem.lower()
        title_filename = f"{prefix}{base_name}.png"
        preview_filename = f"{prefix}{base_name}.png"
        title_dir = self.cfg["title_image_dirs"].get(sys_name, "")
        preview_dir = self.cfg["preview_image_dirs"].get(sys_name, "")
        title_path = find_file_case_insensitive(title_dir, title_filename) if title_dir else None
        preview_path = find_file_case_insensitive(preview_dir, preview_filename) if preview_dir else None
        if title_path:
            self.title_img_label.setPixmap(QPixmap(title_path))
        else:
            self.title_img_label.setPixmap(None)
        if preview_path:
            self.preview_img_label.setPixmap(QPixmap(preview_path))
        else:
            self.preview_img_label.setPixmap(None)

    def current_system(self):
        idx = self.systems_combo.currentIndex()
        sys_cfg = TAB_CONFIGS[idx]
        roms_dir = self.cfg["roms_dirs"].get(sys_cfg["name"], "")
        return sys_cfg, roms_dir

    def update_rom_list(self):
        sys_cfg = self.current_system()[0]
        sys_name = sys_cfg["name"]
        roms_dir = self.cfg["roms_dirs"].get(sys_name, "")
        rom_titles_file = sys_cfg["rom_titles_file"]
        search = self.search_edit.text().lower()
        xml_file = self.cfg["xml_dat_files"].get(sys_name, "")
        year_filter = self.year_edit.text().strip()
        manuf_filter = self.manuf_edit.text().strip()
        hide_clones = self.hide_clones_chk.isChecked()
        all_roms = get_rom_list_cached(
            rom_titles_file, roms_dir, sys_name, xml_file, self.rom_cache
        )
        self.roms = filter_rom_list(all_roms, search, year_filter, manuf_filter, hide_clones)
        self.roms_list.clear()
        for _, title, year, manuf, is_clone in self.roms:
            display = title
            if year or manuf:
                display += f" [{year}]" if year else ""
                display += f" ({manuf})" if manuf else ""
            self.roms_list.addItem(display)
        count = len(self.roms)
        self.rom_count_label.setText(f"ROMs found: {count}")
        if not self.roms_list.count():
            self.roms_list.addItem("No ROMs found.")
        self.update_image_tabs()

    def launch_selected_rom(self, *args):
        idx = self.roms_list.currentRow()
        if idx < 0 or not self.roms or self.roms_list.item(idx).text() == "No ROMs found.":
            QMessageBox.critical(self, "Warning", "Select a ROM.")
            return
        rom = self.roms[idx][0]
        sys_cfg = self.current_system()[0]
        sys_name = sys_cfg["name"]
        run_rom(rom, self.cfg["roms_dirs"].get(sys_name, ""), self.cfg["RETROARCH"], self.cfg["RETROARCH_CORE"], sys_name, self)

    def show_settings(self):
        dlg = SettingsDialog(
            self.cfg,
            self,
            self.current_system,
            self.update_rom_list
        )
        if dlg.exec():
            self.img_tabs.setVisible(not self.cfg.get("display_only_rom_list", False))
            self.update_rom_list()

    def poll_joystick(self):
        if not self.isActiveWindow() or not self.is_active:
            return
        pygame.event.pump()
        jc = self.cfg["joystick_config"]
        fastest_steps = jc.get("hat_fastest_steps", 10)
        fastest_delay = jc.get("hat_fastest_delay", 0.02)
        scroll_cooldown = jc.get("hat_scroll_cooldown", 0.08)
        now = time.time() * 1000
        list_widget = self.roms_list
        idx = list_widget.currentRow()
        size = list_widget.count()

        def scroll_list(direction, steps, held_key, held_time_key, is_keyboard=False):
            state_dict = self.last_key_held if is_keyboard else self.last_hat_held
            time_dict = self.last_key_held_time if is_keyboard else self.last_hat_held_time
            if direction:
                if not state_dict.get(held_key, False):
                    list_widget.setCurrentRow(max(0, idx - steps) if held_key == "left" else min(size - 1, idx + steps))
                    state_dict[held_key] = True
                    time_dict[held_key] = now
                elif now - time_dict.get(held_key, 0) > fastest_delay * 1000:
                    list_widget.setCurrentRow(max(0, list_widget.currentRow() - steps) if held_key == "left" else min(size - 1, list_widget.currentRow() + steps))
                    time_dict[held_key] = now - (fastest_delay * 1000 - 50)
                elif now - time_dict.get(held_key, 0) > 200:
                    list_widget.setCurrentRow(max(0, list_widget.currentRow() - steps) if held_key == "left" else min(size - 1, list_widget.currentRow() + steps))
                    time_dict[held_key] = now
            else:
                state_dict[held_key] = False

        if self.joystick and self.joystick.get_numhats() > 0:
            hat = self.joystick.get_hat(0)
            hat_up = hat[1] == 1
            hat_down = hat[1] == -1
            hat_left = hat[0] == -1
            hat_right = hat[0] == 1

            if hat_up:
                if not self.last_hat_held.get("up", False):
                    list_widget.setCurrentRow(max(0, idx - 1))
                    self.last_hat_held_time["up"] = now
                    self.last_hat_held["up"] = True
                elif now - self.last_hat_held_time["up"] >= scroll_cooldown * 1000:
                    list_widget.setCurrentRow(max(0, list_widget.currentRow() - 1))
                    self.last_hat_held_time["up"] = now
            else:
                self.last_hat_held["up"] = False

            if hat_down:
                if not self.last_hat_held.get("down", False):
                    list_widget.setCurrentRow(min(size - 1, idx + 1))
                    self.last_hat_held_time["down"] = now
                    self.last_hat_held["down"] = True
                elif now - self.last_hat_held_time["down"] >= scroll_cooldown * 1000:
                    list_widget.setCurrentRow(min(size - 1, list_widget.currentRow() + 1))
                    self.last_hat_held_time["down"] = now
            else:
                self.last_hat_held["down"] = False

            scroll_list(hat_left, fastest_steps, "left", "left", is_keyboard=False)
            scroll_list(hat_right, fastest_steps, "right", "right", is_keyboard=False)

            self.last_hat = hat

        scroll_list(self.last_key_held.get("left", False), fastest_steps, "left", "left", is_keyboard=True)
        scroll_list(self.last_key_held.get("right", False), fastest_steps, "right", "right", is_keyboard=True)

        def check_button(btn_key, action):
            idx = jc.get(btn_key, -1)
            if idx < 0 or idx >= self.joystick.get_numbuttons():
                return
            pressed = self.joystick.get_button(idx)
            last_time = self.last_button_times.get(btn_key, 0)
            if pressed and not self.last_button_states.get(btn_key, False):
                if now - last_time >= self.debounce_delay:
                    action()
                    self.last_button_times[btn_key] = now
            self.last_button_states[btn_key] = pressed

        if self.joystick:
            check_button("button_up", lambda: self.roms_list.setCurrentRow(max(0, self.roms_list.currentRow() - 1)))
            check_button("button_down", lambda: self.roms_list.setCurrentRow(min(self.roms_list.count() - 1, self.roms_list.currentRow() + 1)))
            check_button("button_select", self.launch_selected_rom)
            check_button("button_favorites", self.show_favorites)
            check_button("button_prev_tab", lambda: self.systems_combo.setCurrentIndex((self.systems_combo.currentIndex() - 1) % self.systems_combo.count()))
            check_button("button_next_tab", lambda: self.systems_combo.setCurrentIndex((self.systems_combo.currentIndex() + 1) % self.systems_combo.count()))
            
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.resize(1100, 640)
    win.show()
    sys.exit(app.exec())
