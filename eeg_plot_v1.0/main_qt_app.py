"""
Yuehao

"""

import sys
import numpy as np
from collections import deque
from queue import Queue
import pyqtgraph as pg
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QGridLayout,
                             QVBoxLayout, QCheckBox, QHBoxLayout, QFrame, QLabel, QPushButton, QSizePolicy,)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QIcon
import threading

import backend

# --- config ---
NUM_CHANNELS = backend.NUM_CHANNELS
SAMPLES_PER_SECOND = backend.SAMPLES_PER_SECOND
PLOT_DURATION_S = 5
PLOT_SAMPLES = int(SAMPLES_PER_SECOND * PLOT_DURATION_S)
PLOT_UPDATE_INTERVAL_MS = 40                                       # 刷新率 (ms), 40ms -> 25Hz
NFFT = PLOT_SAMPLES
MAX_FREQ_TO_SHOW = 100


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # --- Initialize data storage ---
        self.recording_event = threading.Event()  # 默认是 False
        self.storage_queue = Queue()
        self.filtered_data_queues = [deque(maxlen=PLOT_SAMPLES) for _ in range(NUM_CHANNELS)]

        # --- defination of color list ---
        self.channel_colors = [
            (217, 83, 25), (0, 115, 189), (119, 172, 48), (237, 177, 32),
            (126, 47, 142), (102, 102, 102), (204, 0, 0), (0, 0, 0)
        ]

        # --- set UI ---
        self.setWindowTitle("CQUPT EEGLAB")
        app_icon = QIcon("logo.png")
        self.setWindowIcon(app_icon)
        self.setGeometry(100, 100, 1800, 900)  # 稍微加宽窗口以容纳控制面板

        # 1. set main layout
        main_layout = QHBoxLayout()

        # 2. set left control panel
        control_panel = QWidget()
        control_panel.setObjectName("ControlPanel")
        control_panel.setFixedWidth(150)  # 固定宽度
        control_layout = QVBoxLayout(control_panel)
        #control_layout.setAlignment(Qt.AlignmentFlag.AlignTop)  # 控件顶部对齐
        control_layout.setContentsMargins(10, 10, 10, 10)  # 设置内边距
        control_layout.setSpacing(5)  # 设置控件之间的垂直间距

        # --- add a label ---
        title_label = QLabel("Channels")
        control_layout.addWidget(title_label)
        font = title_label.font()
        font.setBold(True)
        title_label.setFont(font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)



        # 将标题和分隔线添加到布局中
        separator = QFrame()  # 创建一个分隔线
        separator.setFrameShape(QFrame.Shape.HLine)  # 设置为水平线
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        control_layout.addWidget(separator)

        # 控件顶部对齐
        control_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 添加复选框到控制面板
        self.channel_checkboxes = []
        for i in range(NUM_CHANNELS):
            checkbox = QCheckBox(f"Channel {i + 1}")
            checkbox.setChecked(True)  # 默认全部选中
            # 将复选框的状态变化连接到我们的处理函数
            checkbox.stateChanged.connect(self.update_channel_visibility)
            control_layout.addWidget(checkbox)
            self.channel_checkboxes.append(checkbox)

        # 3. 添加复选框
        control_layout.addStretch(1)

        # 状态标签
        self.status_label = QLabel("状态: 未开始")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        control_layout.addWidget(self.status_label)

        # 创建按钮
        self.record_button = QPushButton("开始记录")
        self.record_button.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold;")
        self.record_button.clicked.connect(self.toggle_recording)

        self.stop_button = QPushButton("停止记录")
        self.stop_button.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold;")
        self.stop_button.setEnabled(False)  # 初始不可用
        self.stop_button.clicked.connect(self.stop_recording)

        control_layout.addWidget(self.record_button)
        control_layout.addWidget(self.stop_button)

        # 3. 创建右侧的绘图区域 (使用网格布局)
        plot_area_widget = QWidget()
        plot_layout = QGridLayout(plot_area_widget)
        plot_layout.setColumnStretch(0, 3)  # 时域:频域 = 3:1
        plot_layout.setColumnStretch(1, 1)

        # 4. 将控制面板和绘图区域添加到主布局中
        main_layout.addWidget(control_panel)
        main_layout.addWidget(plot_area_widget)

        # 设置主窗口的中央部件
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        # --- 创建图表并添加到绘图区域 ---
        self.time_plots = []
        self.freq_plots = []
        # 我们需要一个列表来保存图表的容器，以便隐藏它们
        self.plot_widgets_per_channel = []

        self.time_curves = []
        self.freq_curves = []

        self.time_axis = np.linspace(-PLOT_DURATION_S, 0, PLOT_SAMPLES)
        self.freq_axis = np.fft.rfftfreq(NFFT, d=1.0 / SAMPLES_PER_SECOND)
        freq_mask = self.freq_axis <= MAX_FREQ_TO_SHOW

        for i in range(NUM_CHANNELS):
            current_color = self.channel_colors[i % len(self.channel_colors)]

            # 创建时域图
            plot_time = pg.PlotWidget(title=f"Channel {i + 1} - Time Domain")
            plot_time.setLabel('left', 'Amplitude (uV)')
            plot_time.setLabel('bottom', 'Time (s)')
            plot_time.showGrid(x=True, y=True, alpha=0.3)
            pen_time = pg.mkPen(color=current_color, width=2)
            curve_time = plot_time.plot(pen=pen_time)  # 初始时没有数据
            self.time_plots.append(plot_time)
            self.time_curves.append(curve_time)

            # 创建频域图
            plot_freq = pg.PlotWidget(title=f"CH{i + 1} - Frequency Domain")
            plot_freq.setLabel('left', 'Magnitude')
            plot_freq.setLabel('bottom', 'Frequency (Hz)')
            plot_freq.showGrid(x=True, y=True, alpha=0.3)
            plot_freq.setXRange(0, MAX_FREQ_TO_SHOW)
            pen_freq = pg.mkPen(color=current_color)
            curve_freq = plot_freq.plot(pen=pen_freq)  # 初始时没有数据
            self.freq_plots.append(plot_freq)
            self.freq_curves.append(curve_freq)

            # 将时域和频域图表添加到网格布局中
            plot_layout.addWidget(plot_time, i, 0)
            plot_layout.addWidget(plot_freq, i, 1)

            # 保存对这两个图表 widget 的引用，以便之后可以隐藏它们
            self.plot_widgets_per_channel.append((plot_time, plot_freq))

        # --- 设置定时器 ---
        self.timer = QTimer()
        self.timer.setInterval(PLOT_UPDATE_INTERVAL_MS)
        self.timer.timeout.connect(self.update_plots)

    def toggle_recording(self):
        if not self.recording_event.is_set():
            # 这是“开始记录”或“继续记录”的逻辑
            self.recording_event.set()  # 设置Event为True
            self.record_button.setText("暂停记录")
            self.record_button.setStyleSheet("background-color: #f39c12; color: white; font-weight: bold;")
            self.stop_button.setEnabled(True)
            self.status_label.setText("状态: 正在记录...")
            self.status_label.setStyleSheet("color: green;")
        else:
            # 这是“暂停记录”的逻辑
            self.recording_event.clear()  # 设置Event为False
            self.record_button.setText("继续记录")
            self.record_button.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold;")
            self.status_label.setText("状态: 记录暂停")
            self.status_label.setStyleSheet("color: orange;")

    def stop_recording(self):
        # 停止逻辑
        self.recording_event.clear()
        self.storage_queue.put('STOP_RECORDING')  # 发送停止命令

        # 恢复UI到初始状态
        self.record_button.setText("开始记录")
        self.record_button.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold;")
        self.stop_button.setEnabled(False)
        self.status_label.setText("状态: 记录已停止")
        self.status_label.setStyleSheet("color: red;")

    def update_channel_visibility(self):
        """当复选框状态改变时，此函数被调用"""
        for i in range(NUM_CHANNELS):
            is_visible = self.channel_checkboxes[i].isChecked()
            # 获取该通道对应的时域和频域图表
            time_plot_widget, freq_plot_widget = self.plot_widgets_per_channel[i]
            # 设置它们的可见性
            time_plot_widget.setVisible(is_visible)
            freq_plot_widget.setVisible(is_visible)

    def start_monitoring(self):
        """启动后台线程并开始UI更新 """
        raw_data_queue = Queue()
        #storage_queue = Queue()

        print("Starting backend threads from Qt App...")
        backend.start_backend_threads(
            raw_data_queue,
            self.filtered_data_queues,
            self.storage_queue,
            self.recording_event
        )

        self.timer.start()
        print("UI update timer started.")

    def closeEvent(self, event):
        """当用户关闭窗口时，确保后台线程能干净地退出"""
        print("Closing application...")
        if self.storage_queue:
            self.storage_queue.put(None)  # 发送最终的程序退出信号
        event.accept()

    def update_plots(self):
        """定时器调用的更新函数 """
        for i in range(NUM_CHANNELS):
            # 只有当通道是可见的时候，才更新它的数据
            if not self.channel_checkboxes[i].isChecked():
                continue

            current_data = self.filtered_data_queues[i]
            num_samples = len(current_data)

            if num_samples == 0:
                continue

            # 更新时域图
            time_data_subset = self.time_axis[-num_samples:]
            self.time_curves[i].setData(x=time_data_subset, y=current_data)

            # 更新频域图
            if num_samples >= NFFT:
                fft_input_data = np.array(current_data)
                fft_data = np.fft.rfft(fft_input_data - np.mean(fft_input_data), n=NFFT)
                freq_magnitude = (2.0 / NFFT) * np.abs(fft_data)

                freq_mask = self.freq_axis <= MAX_FREQ_TO_SHOW
                self.freq_curves[i].setData(x=self.freq_axis[freq_mask], y=freq_magnitude[freq_mask])


if __name__ == '__main__':
    import os

    if not os.path.exists('data'):
        os.makedirs('data')

    # 1. 设置 pyqtgraph 的绘图区域颜色
    pg.setConfigOption('background', 'w')
    pg.setConfigOption('foreground', 'k')

    app = QApplication(sys.argv)

    # 2. 使用Qt样式表(QSS)来设置整个应用的浅色主题
    light_theme_stylesheet = """
        /* --- 全局样式 --- */
        QWidget {
            background-color: #F0F0F0; 
            color: #000000;
            font-family: "Segoe UI", Arial, sans-serif; /* 使用更现代的字体 */
        }

        /* --- 控制面板样式 --- */
        #ControlPanel {
            background-color: #EAEAEA;
            border-radius: 5px;
        }

        #TitleLabel {
            font-weight: bold;
            font-size: 14pt;
            color: #2c3e50;
            background-color: transparent;
        }

        QLabel {
             background-color: transparent;
        }

        /* --- 分隔线样式 --- */
        QFrame[frameShape="4"] { /* 4是HLine的枚举值 */
            border: 1px solid #D0D0D0;
        }

        /* --- 复选框(QCheckBox)的详细样式 --- */
        QCheckBox {
            spacing: 5px; /* 复选框和文字之间的间距 */
            background-color: transparent;
        }

        /* ::indicator 是指复选框的那个小方块 */
        QCheckBox::indicator {
            width: 18px;  /* 方块宽度 */
            height: 18px; /* 方块高度 */
            border-radius: 4px; /* 轻微的圆角 */
        }

        /* 未选中状态下的方块样式 */
        QCheckBox::indicator:unchecked {
            background-color: #FFFFFF; /* 白色背景 */
            border: 2px solid #A9A9A9; /* 深灰色边框 */
        }

        /* 鼠标悬停在未选中方块上时的样式 */
        QCheckBox::indicator:unchecked:hover {
            border: 2px solid #3498db; /* 边框变为蓝色以示反馈 */
        }

        /* 已选中状态下的方块样式 */
        QCheckBox::indicator:checked {
            background-color: #3498db; /* 背景变为醒目的蓝色 */
            border: 2px solid #3498db; /* 边框也变为蓝色 */
            /* 关键：设置勾选标记的图片 */
            image: url(C:/Windows/System32/shell32.dll:105); /* 使用一个Windows系统自带的白色勾号图标 */
        }
    """
    app.setStyleSheet(light_theme_stylesheet)

    main_window = MainWindow()
    main_window.show()

    QTimer.singleShot(100, main_window.start_monitoring)

    print("Starting Qt event loop...")
    sys.exit(app.exec())