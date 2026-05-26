import queue
import re
import sys
import threading
import time
from collections import deque

import pyqtgraph as pg
import serial
from PyQt6.QtCore import QEvent, QTimer, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from serial.tools import list_ports


BAUD_RATE_OPTIONS = [115200, 230400, 460800, 500000, 1000000]
DEFAULT_BAUD_RATE = 1000000
CHANNEL_COUNT = 8
MAX_HISTORY = 1000

# Arduino prints lines like:
#   === Frame #123 ===
#   S01: 0.40405
#   S02: 4.59846
#   ...
SENSOR_LINE_RE = re.compile(rb"S(\d+):\s*(-?\d+(?:\.\d+)?)")
FRAME_MARKER = b"=== Frame"

CHANNEL_COLORS = [
    "#4fc3f7",
    "#81c784",
    "#ffb74d",
    "#e57373",
    "#ba68c8",
    "#4dd0e1",
    "#aed581",
    "#ffd54f",
]

data_queue = queue.Queue()
status_queue = queue.Queue()
frame_counter = {"count": 0}
sensor_histories = {f"sensor{i}": deque(maxlen=MAX_HISTORY) for i in range(CHANNEL_COUNT)}
current_values = {f"sensor{i}": 0.0 for i in range(CHANNEL_COUNT)}




class SerialReader:
    def __init__(self, port, baud_rate):
        self.port = port
        self.baud_rate = baud_rate
        self.ser = None
        self.running = False
        self.thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.ser and self.ser.is_open:
            self.ser.close()
        if self.thread:
            self.thread.join(timeout=1)

    def _read_loop(self):
        buffer = bytearray()
        current_frame = [None] * CHANNEL_COUNT
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baud_rate,
                timeout=1,
            )
            status_queue.put(("connected", self.port, self.baud_rate))
            print(f"Port connected: {self.port}")
            time.sleep(0.1)

            while self.running:
                if not self.ser or not self.ser.is_open:
                    break

                waiting = self.ser.in_waiting
                if waiting <= 0:
                    time.sleep(0.002)
                    continue

                data = self.ser.read(waiting)
                buffer.extend(data)

                # Parse Arduino text output line-by-line
                while b"\n" in buffer:
                    newline_idx = buffer.index(b"\n")
                    line = bytes(buffer[:newline_idx]).strip()
                    del buffer[: newline_idx + 1]

                    if not line:
                        continue

                    # New frame marker → reset accumulator
                    if line.startswith(FRAME_MARKER):
                        current_frame = [None] * CHANNEL_COUNT
                        continue

                    m = SENSOR_LINE_RE.match(line)
                    if not m:
                        continue

                    try:
                        idx = int(m.group(1)) - 1  # S01 → 0
                        val = float(m.group(2))
                    except ValueError:
                        continue

                    if 0 <= idx < CHANNEL_COUNT:
                        current_frame[idx] = val
                        if all(v is not None for v in current_frame):
                            data_queue.put(list(current_frame))
                            frame_counter["count"] += 1
                            current_frame = [None] * CHANNEL_COUNT
        except serial.SerialException as exc:
            status_queue.put(("error", str(exc)))
            print(f"Serial port error: {exc}")
        except Exception as exc:
            status_queue.put(("error", str(exc)))
            print(f"Read thread error: {exc}")
        finally:
            if self.ser and self.ser.is_open:
                self.ser.close()
            status_queue.put(("disconnected", self.port))
            print(f"Port disconnected: {self.port}")


class SensorMonitor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Huda Serial Monitor")
        self.resize(1400, 800)
        self.serial_reader = None
        self.channel_rows = {}
        self.selected_channels = set(range(CHANNEL_COUNT))
        self.curves = []
        self.mono_font = self._make_mono_font(9)

        pg.setConfigOptions(antialias=True)
        self._build_ui()
        self.refresh_ports()

        self.gui_timer = QTimer(self)
        self.gui_timer.timeout.connect(self.update_gui)
        self.gui_timer.start(16)

        self.fps_timer = QTimer(self)
        self.fps_timer.timeout.connect(self.update_fps)
        self.fps_timer.start(1000)

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.control_bar = QFrame()
        self.control_bar.setObjectName("controlBar")
        self.control_bar.setFixedHeight(40)
        control_layout = QHBoxLayout(self.control_bar)
        control_layout.setContentsMargins(12, 0, 12, 0)
        control_layout.setSpacing(8)

        control_layout.addWidget(self._make_label("Port:"))
        self.port_combo = QComboBox()
        self.port_combo.setObjectName("controlCombo")
        self.port_combo.setFixedHeight(26)
        self.port_combo.setMinimumWidth(150)
        self.port_combo.currentTextChanged.connect(self.on_port_or_baud_changed)
        control_layout.addWidget(self.port_combo)

        control_layout.addWidget(self._make_label("Baud:"))
        self.baud_combo = QComboBox()
        self.baud_combo.setObjectName("controlCombo")
        self.baud_combo.setFixedHeight(26)
        self.baud_combo.setMinimumWidth(105)
        self.baud_combo.addItems([str(rate) for rate in BAUD_RATE_OPTIONS])
        self.baud_combo.setCurrentText(str(DEFAULT_BAUD_RATE))
        self.baud_combo.currentTextChanged.connect(self.on_port_or_baud_changed)
        control_layout.addWidget(self.baud_combo)

        self.connect_button = QPushButton("Connect")
        self.connect_button.setObjectName("flatButton")
        self.connect_button.setFixedHeight(28)
        self.connect_button.clicked.connect(self.toggle_connection)
        control_layout.addWidget(self.connect_button)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setObjectName("flatButton")
        self.refresh_button.setFixedHeight(28)
        self.refresh_button.clicked.connect(self.refresh_ports)
        control_layout.addWidget(self.refresh_button)

        self.status_label = QLabel("● Disconnected")
        self.status_label.setObjectName("statusDisconnected")
        control_layout.addWidget(self.status_label)

        separator = QFrame()
        separator.setObjectName("verticalSeparator")
        separator.setFixedWidth(1)
        control_layout.addWidget(separator)

        control_layout.addWidget(self._make_label("Channel:"))
        self.channel_combo = QComboBox()
        self.channel_combo.setObjectName("controlCombo")
        self.channel_combo.setFixedHeight(26)
        self.channel_combo.setMinimumWidth(190)
        self.channel_combo.addItems(
            ["All Channels"] + [f"sensor{index}" for index in range(CHANNEL_COUNT)]
        )
        self.channel_combo.currentIndexChanged.connect(self.on_channel_combo_changed)
        control_layout.addWidget(self.channel_combo)

        control_layout.addStretch(1)

        self.fps_label = QLabel("FPS: 0")
        self.fps_label.setObjectName("fpsLabel")
        control_layout.addWidget(self.fps_label)

        root_layout.addWidget(self.control_bar)

        content = QWidget()
        content.setObjectName("content")
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        plot_shell = QWidget()
        plot_shell.setObjectName("plotShell")
        plot_layout = QVBoxLayout(plot_shell)
        plot_layout.setContentsMargins(14, 12, 14, 12)
        plot_layout.setSpacing(0)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setObjectName("mainPlot")
        self.plot_widget.setBackground("#1e1f22")
        self.plot_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        plot_layout.addWidget(self.plot_widget)
        self._configure_plot()
        content_layout.addWidget(plot_shell, stretch=1)

        self.values_panel = QFrame()
        self.values_panel.setObjectName("valuesPanel")
        self.values_panel.setFixedWidth(240)
        values_layout = QVBoxLayout(self.values_panel)
        values_layout.setContentsMargins(0, 0, 0, 0)
        values_layout.setSpacing(0)

        title = QLabel("CURRENT VALUES")
        title.setObjectName("valuesTitle")
        title.setFixedHeight(46)
        values_layout.addWidget(title)

        rows = QWidget()
        rows.setObjectName("valuesRows")
        rows_layout = QVBoxLayout(rows)
        rows_layout.setContentsMargins(16, 4, 16, 0)
        rows_layout.setSpacing(0)
        for index in range(CHANNEL_COUNT):
            sensor_id = f"sensor{index}"
            row = QWidget()
            row.setObjectName("valueRow")
            row.setProperty("channelIndex", index)
            row.setProperty("channelVisible", True)
            row.setFixedHeight(22)
            row.installEventFilter(self)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)

            name_label = QLabel(sensor_id)
            name_label.setObjectName("sensorName")
            name_label.setProperty("channelIndex", index)
            name_label.setProperty("channelVisible", True)
            name_label.setFont(self._make_mono_font(10))
            name_label.installEventFilter(self)
            value_label = QLabel(f"{0.0:>13.6f}")
            value_label.setObjectName("sensorValue")
            value_label.setProperty("channelIndex", index)
            value_label.setProperty("channelVisible", True)
            value_label.setFont(self._make_mono_font(10))
            value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            value_label.installEventFilter(self)

            row_layout.addWidget(name_label)
            row_layout.addStretch(1)
            row_layout.addWidget(value_label)
            rows_layout.addWidget(row)
            self.channel_rows[sensor_id] = {
                "row": row,
                "name": name_label,
                "value": value_label,
            }

        rows_layout.addStretch(1)
        values_layout.addWidget(rows, stretch=1)
        content_layout.addWidget(self.values_panel)

        root_layout.addWidget(content, stretch=1)
        self.setCentralWidget(root)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            channel_index = watched.property("channelIndex")
            if channel_index is not None:
                self.toggle_channel_visibility(int(channel_index))
                return True
        return super().eventFilter(watched, event)

    def _configure_plot(self):
        plot_item = self.plot_widget.getPlotItem()
        plot_item.setMenuEnabled(False)
        plot_item.hideButtons()
        plot_item.setLabel(
            "bottom",
            "Time (samples)",
            color="#868a91",
            **{"font-size": "9pt"},
        )
        plot_item.setLabel(
            "left",
            "Value",
            color="#868a91",
            **{"font-size": "9pt"},
        )
        plot_item.showGrid(x=True, y=True, alpha=0.3)
        plot_item.getViewBox().setBorder(None)
        plot_item.getViewBox().enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)
        plot_item.getViewBox().enableAutoRange(axis=pg.ViewBox.XAxis, enable=True)

        for axis_name in ("bottom", "left"):
            axis = plot_item.getAxis(axis_name)
            axis.setPen(pg.mkPen("#393b40"))
            axis.setTextPen(pg.mkPen("#868a91"))
            axis.setTickFont(self.mono_font)
            axis.label.setFont(self._make_mono_font(9))

        self.legend = plot_item.addLegend(offset=(-12, 12), labelTextColor="#dfe1e5")
        self.legend.setBrush(pg.mkBrush(30, 31, 34, 217))
        self.legend.setPen(pg.mkPen("#393b40", width=1))

        for index in range(CHANNEL_COUNT):
            color = CHANNEL_COLORS[index % len(CHANNEL_COLORS)]
            curve = self.plot_widget.plot(
                [],
                [],
                pen=pg.mkPen(color, width=1),
                name=f"sensor{index}",
            )
            self.curves.append(curve)

    def _make_label(self, text):
        label = QLabel(text)
        label.setObjectName("controlLabel")
        return label

    def _make_mono_font(self, size):
        font = QFont("JetBrains Mono", size)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFamilies(["JetBrains Mono", "Consolas", "Courier New"])
        return font

    def refresh_ports(self):
        current = self.port_combo.currentText()
        ports = [port.device for port in list_ports.comports()]
        self.port_combo.blockSignals(True)
        self.port_combo.clear()
        self.port_combo.addItems(ports if ports else ["No Ports Available"])
        if current in ports:
            self.port_combo.setCurrentText(current)
        elif ports:
            self.port_combo.setCurrentText(ports[0])
        self.port_combo.blockSignals(False)

    def on_port_or_baud_changed(self):
        if self.serial_reader and self.serial_reader.running:
            self.disconnect_serial()
            print("Port or baud rate switched, please click Connect")

    def toggle_connection(self):
        if self.serial_reader and self.serial_reader.running:
            self.disconnect_serial()
            return

        selected_port = self.port_combo.currentText()
        if not selected_port or selected_port == "No Ports Available":
            self.set_status("Select a port", connected=False)
            return

        try:
            baud_rate = int(self.baud_combo.currentText())
        except ValueError:
            self.set_status("Invalid baud rate", connected=False)
            return

        self.set_status("Connecting...", connected=False)
        self.connect_button.setEnabled(False)
        self.serial_reader = SerialReader(selected_port, baud_rate)
        self.serial_reader.start()

    def disconnect_serial(self):
        if self.serial_reader:
            self.serial_reader.stop()
            self.serial_reader = None
        self.connect_button.setEnabled(True)
        self.connect_button.setText("Connect")
        self.set_status("Disconnected", connected=False)

    def update_status_events(self):
        while not status_queue.empty():
            event = status_queue.get_nowait()
            event_type = event[0]
            if event_type == "connected":
                _, port, baud_rate = event
                self.connect_button.setEnabled(True)
                self.connect_button.setText("Disconnect")
                self.set_status(f"Connected: {port} @ {baud_rate}", connected=True)
            elif event_type == "error":
                _, message = event
                self.connect_button.setEnabled(True)
                self.connect_button.setText("Connect")
                self.set_status(f"Disconnected ({message})", connected=False)
                self.serial_reader = None
            elif event_type == "disconnected":
                if not (self.serial_reader and self.serial_reader.running):
                    self.connect_button.setEnabled(True)
                    self.connect_button.setText("Connect")
                    self.set_status("Disconnected", connected=False)

    def set_status(self, text, connected):
        self.status_label.setText(f"● {text}")
        self.status_label.setObjectName("statusConnected" if connected else "statusDisconnected")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def update_fps(self):
        fps = frame_counter["count"]
        frame_counter["count"] = 0
        self.fps_label.setText(f"FPS: {fps}")

    def update_gui(self):
        self.update_status_events()
        data_changed = False

        while not data_queue.empty():
            values = data_queue.get_nowait()
            for index, value in enumerate(values[:CHANNEL_COUNT]):
                sensor_id = f"sensor{index}"
                sensor_histories[sensor_id].append(value)
                current_values[sensor_id] = value
            data_changed = True

        if data_changed:
            self.update_value_panel()
            self.update_curves()

    def update_value_panel(self):
        for index in range(CHANNEL_COUNT):
            sensor_id = f"sensor{index}"
            value = current_values[sensor_id]
            self.channel_rows[sensor_id]["value"].setText(f"{value:>13.6f}")

    def update_curves(self):
        for index, curve in enumerate(self.curves):
            sensor_id = f"sensor{index}"
            history = sensor_histories[sensor_id]
            curve.setData(range(len(history)), list(history))
        self.update_curve_visibility()

    def update_curve_visibility(self):
        for index, curve in enumerate(self.curves):
            curve.setVisible(index in self.selected_channels)
        self.update_channel_row_states()

    def on_channel_combo_changed(self):
        selected = self.channel_combo.currentText()
        if selected == "All Channels":
            self.selected_channels = set(range(CHANNEL_COUNT))
        elif selected.startswith("sensor"):
            try:
                self.selected_channels = {int(selected.replace("sensor", ""))}
            except ValueError:
                self.selected_channels = set(range(CHANNEL_COUNT))
        self.update_curve_visibility()

    def toggle_channel_visibility(self, channel_index):
        if channel_index in self.selected_channels:
            self.selected_channels.remove(channel_index)
        else:
            self.selected_channels.add(channel_index)

        self.channel_combo.blockSignals(True)
        if len(self.selected_channels) == CHANNEL_COUNT:
            self.channel_combo.setCurrentText("All Channels")
        elif len(self.selected_channels) == 1:
            only_channel = next(iter(self.selected_channels))
            self.channel_combo.setCurrentText(f"sensor{only_channel}")
        else:
            self.channel_combo.setCurrentText("All Channels")
        self.channel_combo.blockSignals(False)

        self.update_curve_visibility()

    def update_channel_row_states(self):
        for index in range(CHANNEL_COUNT):
            sensor_id = f"sensor{index}"
            visible = index in self.selected_channels
            for widget in self.channel_rows[sensor_id].values():
                widget.setProperty("channelVisible", visible)
                widget.style().unpolish(widget)
                widget.style().polish(widget)

    def closeEvent(self, event):
        if self.serial_reader:
            self.serial_reader.stop()
        event.accept()


def apply_dark_styles(app):
    app.setFont(QFont("Segoe UI", 9))
    app.setStyleSheet(
        """
        QWidget {
            background: #1e1f22;
            color: #dfe1e5;
            font-family: "Segoe UI";
            font-size: 9pt;
        }
        QFrame#controlBar {
            background: #2b2d30;
            border-bottom: 1px solid #393b40;
        }
        QLabel#controlLabel {
            background: transparent;
            color: #868a91;
        }
        QComboBox#controlCombo {
            background: #1e1f22;
            border: 1px solid #393b40;
            border-radius: 2px;
            color: #dfe1e5;
            min-height: 26px;
            padding: 4px 8px;
        }
        QComboBox#controlCombo:hover {
            border: 1px solid #4fc3f7;
        }
        QComboBox#controlCombo::drop-down {
            border: 0;
            width: 18px;
        }
        QComboBox#controlCombo QLineEdit {
            background: transparent;
            border: 0;
            color: #dfe1e5;
            padding: 0;
            selection-background-color: #393b40;
        }
        QComboBox QAbstractItemView {
            background: #2b2d30;
            border: 1px solid #393b40;
            color: #dfe1e5;
            selection-background-color: #393b40;
            selection-color: #dfe1e5;
            outline: 0;
        }
        QPushButton#flatButton {
            background: #393b40;
            border: 0;
            border-radius: 2px;
            color: #dfe1e5;
            padding: 6px 14px;
        }
        QPushButton#flatButton:hover {
            background: #4a4d52;
        }
        QPushButton#flatButton:pressed {
            background: #5a5d62;
        }
        QPushButton#flatButton:disabled {
            background: #303236;
            color: #868a91;
        }
        QLabel#statusConnected {
            background: transparent;
            color: #50fa7b;
            font-size: 9pt;
        }
        QLabel#statusDisconnected {
            background: transparent;
            color: #868a91;
            font-size: 9pt;
        }
        QLabel#fpsLabel {
            background: transparent;
            color: #868a91;
            font-family: "JetBrains Mono", "Consolas";
            font-size: 9pt;
        }
        QFrame#verticalSeparator {
            background: #393b40;
            border: 0;
            min-width: 1px;
            max-width: 1px;
        }
        QWidget#content,
        QWidget#plotShell {
            background: #1e1f22;
        }
        QFrame#valuesPanel {
            background: #2b2d30;
            border-left: 1px solid #393b40;
        }
        QLabel#valuesTitle {
            background: #2b2d30;
            color: #868a91;
            font-size: 10pt;
            letter-spacing: 1px;
            padding-left: 16px;
        }
        QWidget#valuesRows,
        QWidget#valueRow {
            background: #2b2d30;
        }
        QWidget#valueRow:hover {
            background: #33363a;
        }
        QWidget#valueRow[channelVisible="false"] {
            background: #25272a;
        }
        QLabel#sensorName {
            background: #2b2d30;
            color: #868a91;
            font-family: "JetBrains Mono", "Consolas";
            font-size: 10pt;
        }
        QLabel#sensorName[channelVisible="false"] {
            background: #25272a;
            color: #5f636a;
        }
        QLabel#sensorValue {
            background: #2b2d30;
            color: #cdd6f4;
            font-family: "JetBrains Mono", "Consolas";
            font-size: 10pt;
        }
        QLabel#sensorValue[channelVisible="false"] {
            background: #25272a;
            color: #686f82;
        }
        """
    )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_dark_styles(app)
    window = SensorMonitor()
    window.show()
    sys.exit(app.exec())
