#!/usr/bin/env python3
import sys
import subprocess
import json
import os
import dbus

from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QScrollArea,
    QSystemTrayIcon,
    QMenu,
    QFrame,
    QLabel,
    QPushButton,
    QSlider,
)
from PySide6.QtGui import QAction, QPainter, QColor, QIcon, QPixmap, QPen
from PySide6.QtCore import Qt, QRect, QTimer, QUrl
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtMultimedia import QSoundEffect


def resource_path(relative_path):
    base_path = os.path.dirname(os.path.abspath(__file__))

    if not os.path.exists(os.path.join(base_path, relative_path)):
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


class FlatpakSoundEffect:
    def __init__(self):
        self.effect = QSoundEffect()
        self.effect.setVolume(1.0)

    def setSource(self, qurl_obj):
        self.effect.setSource(qurl_obj)

    def play(self):
        if self.effect.isLoaded():
            self.effect.play()


XDG_CONFIG = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
CONFIG_DIR = os.path.join(XDG_CONFIG, "control_ps5")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def ensure_config():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w") as f:
            json.dump({"controllers": {}}, f, indent=4)


def load_config():
    ensure_config()
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"controllers": {}}


def save_config(config):
    ensure_config()
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)


class DualSenseMonitor:
    def __init__(self):
        try:
            self.bus = dbus.SystemBus()
            self.upower_proxy = self.bus.get_object(
                "org.freedesktop.UPower", "/org/freedesktop/UPower"
            )
            self.upower_interface = dbus.Interface(
                self.upower_proxy, "org.freedesktop.UPower"
            )
        except Exception as e:
            print(f"Error al inicializar D-Bus UPower: {e}")
            self.upower_interface = None

    def get_devices(self):
        if not self.upower_interface:
            return []
        try:
            devices = self.upower_interface.EnumerateDevices()
            return [str(dev) for dev in devices if "ps_controller" in dev]
        except Exception as e:
            print(f"Error al listar dispositivos por D-Bus: {e}")
            return []

    def get_device_info(self, device_path):
        try:
            device_obj = self.bus.get_object("org.freedesktop.UPower", device_path)
            properties_interface = dbus.Interface(
                device_obj, "org.freedesktop.DBus.Properties"
            )

            percentage = int(
                properties_interface.Get("org.freedesktop.UPower.Device", "Percentage")
            )
            state_code = int(
                properties_interface.Get("org.freedesktop.UPower.Device", "State")
            )
            model = str(
                properties_interface.Get("org.freedesktop.UPower.Device", "Model")
            )

            state_map = {
                1: "Cargando",
                2: "Descargando",
                3: "Vacío",
                4: "Carga completa",
                5: "Pendiente",
            }
            state = state_map.get(state_code, "Desconocido")

            if not model or model == "unknown":
                model = "DualSense"

            return {
                "device": device_path,
                "percentage": percentage,
                "state": state,
                "model": model,
            }
        except Exception as e:
            print(f"Error al obtener info del dispositivo vía D-Bus: {e}")
            return None


class ControllerCard(QFrame):
    def __init__(self, controller, config, save_callback):
        super().__init__()
        self.controller = controller
        self.config = config
        self.save_callback = save_callback

        self.setMinimumWidth(500)
        self.setFrameShape(QFrame.Shape.StyledPanel)

        self.setStyleSheet("""
            QFrame { background: white; border-radius: 18px; border: 1px solid #dcdcdc; padding: 18px; }
            QLabel { color: #202020; font-size: 14px; }
            QPushButton { background: #2d89ef; color: white; border: none; border-radius: 10px; padding: 12px; font-size: 14px; font-weight: bold; }
            QPushButton:hover { background: #1b6fd8; }
            QSlider::groove:horizontal { border: none; height: 6px; background: #d7d7d7; border-radius: 3px; }
            QSlider::sub-page:horizontal { background: #2d89ef; border-radius: 3px; }
            QSlider::handle:horizontal { background: #ffffff; border: 2px solid #2d89ef; width: 12px; height: 12px; margin: -3px 0; border-radius: 6px; }
            QSlider::handle:horizontal:hover { background: #f2f8ff; }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        self.svg = QSvgWidget(resource_path("assets/player.svg"))
        self.svg.setFixedSize(128, 128)
        layout.addWidget(self.svg, alignment=Qt.AlignmentFlag.AlignCenter)

        self.title = QLabel()
        self.title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(self.title)

        self.info = QLabel()
        layout.addWidget(self.info)

        layout.addWidget(QLabel("🔋 Avisar cuando la batería baje de este porcentaje"))
        self.min_slider = QSlider(Qt.Orientation.Horizontal)
        self.min_slider.setRange(1, 100)
        layout.addWidget(self.min_slider)

        self.min_label = QLabel()
        layout.addWidget(self.min_label)

        layout.addWidget(QLabel("⚡ Avisar cuando la carga alcance este porcentaje"))
        self.max_slider = QSlider(Qt.Orientation.Horizontal)
        self.max_slider.setRange(1, 100)
        layout.addWidget(self.max_slider)

        self.max_label = QLabel()
        layout.addWidget(self.max_label)

        saved = config.get(controller["device"], {})
        self.min_slider.setValue(saved.get("min", 20))
        self.max_slider.setValue(saved.get("max", 80))

        self.min_slider.valueChanged.connect(self.update_labels)
        self.max_slider.valueChanged.connect(self.update_labels)
        self.update_labels()

        btn = QPushButton("Guardar configuración")
        btn.clicked.connect(self.save_settings)
        layout.addWidget(btn)

        self.setLayout(layout)
        self.update_info(controller)

    def update_labels(self):
        self.min_label.setText(f"Mínimo actual: {self.min_slider.value()}%")
        self.max_label.setText(f"Máximo actual: {self.max_slider.value()}%")

    def update_info(self, controller):
        self.controller = controller
        self.title.setText(controller["model"])
        self.info.setText(
            f"Batería: {controller['percentage']}%\nEstado: {controller['state']}"
        )

    def save_settings(self):
        self.save_callback(
            self.controller["device"], self.min_slider.value(), self.max_slider.value()
        )


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Control PS Monitor")
        self.resize(800, 800)

        self.setStyleSheet("""
            QWidget { background: #f2f2f2; color: #202020; font-size: 14px; }
            QScrollArea { border: none; }
        """)

        self.monitor = DualSenseMonitor()
        self.cards = {}
        self.notified = {}
        self.connected_devices = set()
        self.config = load_config()

        self.layout = QVBoxLayout()
        self.scroll = QScrollArea()
        self.container = QWidget()
        self.container_layout = QVBoxLayout()

        self.container.setLayout(self.container_layout)
        self.scroll.setWidget(self.container)
        self.scroll.setWidgetResizable(True)

        self.layout.addWidget(self.scroll)
        self.setLayout(self.layout)

        self.setup_tray()
        self.load_sounds()

        self.tray.activated.connect(self.on_tray_activated)

        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(3000)
        self.refresh()

    def load_sounds(self):
        self.sound_min = FlatpakSoundEffect()
        self.sound_min.setSource(
            QUrl.fromLocalFile(resource_path("assets/50.wav"))
        )

        self.sound_max = FlatpakSoundEffect()
        self.sound_max.setSource(
            QUrl.fromLocalFile(resource_path("assets/100.wav"))
        )

        self.sound_connect = FlatpakSoundEffect()
        self.sound_connect.setSource(
            QUrl.fromLocalFile(resource_path("assets/connect.wav"))
        )

        self.sound_disconnect = FlatpakSoundEffect()
        self.sound_disconnect.setSource(
            QUrl.fromLocalFile(resource_path("assets/disconnect.wav"))
        )

    def setup_tray(self):
        self.tray = QSystemTrayIcon()
        self.tray.setIcon(self.create_battery_icon(100))

        menu = QMenu()
        show_action = QAction("Mostrar / Ocultar", self)
        show_action.triggered.connect(self.toggle_window)

        quit_action = QAction("Cerrar completamente", self)
        quit_action.triggered.connect(self.exit_app)

        menu.addAction(show_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.show()

    def toggle_window(self):
        if self.isVisible():
            self.hide()
        else:
            self.showNormal()
            self.activateWindow()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_window()

    def exit_app(self):
        self.tray.hide()
        QApplication.quit()

    def create_battery_icon(self, percentage):
        pixmap = QPixmap(58, 62)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if percentage >= 80:
            color = QColor(0, 180, 0)
        elif percentage >= 30:
            color = QColor(220, 180, 0)
        else:
            color = QColor(220, 0, 0)

        painter.setPen(QPen(Qt.GlobalColor.white, 2))
        painter.drawRect(10, 15, 40, 25)
        painter.drawRect(50, 22, 5, 10)

        fill_width = int((percentage / 100) * 38)
        painter.fillRect(QRect(11, 16, fill_width, 23), color)
        painter.end()

        return QIcon(pixmap)

    def save_controller_settings(self, device, min_value, max_value):
        if "controllers" not in self.config:
            self.config["controllers"] = {}
        self.config["controllers"][device] = {"min": min_value, "max": max_value}
        save_config(self.config)

    def refresh(self):
        devices = self.monitor.get_devices()
        current_devices = set(devices)

        new_devices = current_devices - self.connected_devices
        for dev in new_devices:
            self.sound_connect.play()
            self.tray.showMessage(
                "Control conectado",
                "PlayStation",
                QSystemTrayIcon.MessageIcon.Information,
            )

        removed_devices = self.connected_devices - current_devices
        for dev in removed_devices:
            self.sound_disconnect.play()
            self.tray.showMessage(
                "Control desconectado",
                "PlayStation",
                QSystemTrayIcon.MessageIcon.Warning,
            )

        self.connected_devices = current_devices
        removed_cards = []

        for device in self.cards:
            if device not in current_devices:
                removed_cards.append(device)

        for device in removed_cards:
            card = self.cards[device]
            self.container_layout.removeWidget(card)
            card.deleteLater()
            del self.cards[device]

        percentages = []

        for device in devices:
            info = self.monitor.get_device_info(device)
            if not info:
                continue

            percentages.append(info["percentage"])

            ctrl_cfg = self.config.get("controllers", {}).get(
                device, {"min": 20, "max": 80}
            )
            if device not in self.notified:
                self.notified[device] = {"min": False, "max": False}

            if (
                info["percentage"] <= ctrl_cfg["min"]
                and not self.notified[device]["min"]
            ):
                self.sound_min.play()
                self.notified[device]["min"] = True
            elif info["percentage"] > ctrl_cfg["min"]:
                self.notified[device]["min"] = False

            if (
                info["percentage"] >= ctrl_cfg["max"]
                and info["state"] == "Cargando"
                and not self.notified[device]["max"]
            ):
                self.sound_max.play()
                self.notified[device]["max"] = True
            elif info["percentage"] < ctrl_cfg["max"]:
                self.notified[device]["max"] = False

            if device not in self.cards:
                card = ControllerCard(
                    info,
                    self.config.get("controllers", {}),
                    self.save_controller_settings,
                )
                self.cards[device] = card
                self.container_layout.addWidget(card)
            else:
                self.cards[device].update_info(info)

        if percentages:
            average = int(sum(percentages) / len(percentages))
            self.tray.setIcon(self.create_battery_icon(average))
            self.tray.setToolTip(
                f"{len(devices)} controles\nBatería promedio: {average}%"
            )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
