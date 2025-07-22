"""
Yuehao

"""

import sys
import numpy as np
from collections import deque
from queue import Queue
import pyqtgraph as pg
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QGridLayout,
                             QVBoxLayout, QCheckBox, QHBoxLayout, QFrame, QLabel,
                             QPushButton, QSizePolicy, QLineEdit, QProgressBar)
from PyQt6.QtCore import QTimer, Qt, QEvent
from PyQt6.QtGui import QIcon
import threading
import time
from scipy import signal

import backend
from SettingsDialog import SettingsDialog

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

        self.app_settings = {
            'highpass_cutoff': backend.HIGHPASS_CUTOFF,
            'notch_filter_enabled': True,
            'plot_duration_s': PLOT_DURATION_S
        }

        # --- Initialize data storage ---
        self.recording_event = threading.Event()
        self.storage_queue = Queue()
        self.command_queue = Queue()
        self.marker_lines = []
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
        self.setGeometry(100, 100, 1800, 900)

        # =============================================================================
        # --- UI布局重构开始 (实现顶部通道栏 + 左侧控制面板) ---
        # =============================================================================

        # 1. 主布局 (垂直): 用于容纳“顶部通道栏”和“下方主区域”
        main_layout = QVBoxLayout()

        # 2. 创建顶部的通道选择栏
        top_channels_bar = QWidget()
        top_channels_bar.setObjectName("ControlPanel")  # 让它也应用样式
        top_channels_bar.setMaximumHeight(50)  # 给一个紧凑的高度
        top_channels_layout = QHBoxLayout(top_channels_bar)
        top_channels_layout.setContentsMargins(10, 5, 10, 5)

        channels_label = QLabel("<b>Channels:</b>")
        top_channels_layout.addWidget(channels_label)

        self.channel_buttons = []
        for i in range(NUM_CHANNELS):
            # 创建 QPushButton
            button = QPushButton(f"CH{i + 1}")
            # 设置为可切换状态
            button.setCheckable(True)
            # 默认设置为选中状态
            button.setChecked(True)
            # 设置一个固定的尺寸，让它们看起来像工具栏按钮
            button.setFixedSize(60, 25)

            button.setObjectName(f"channelButton_{i + 1}")

            # 将按钮的 toggled 信号连接到处理函数
            # lambda a, i=i: ... 是为了在调用时能准确传递按钮的索引 i
            button.toggled.connect(lambda checked, index=i: self.update_channel_visibility(index, checked))

            top_channels_layout.addWidget(button)
            self.channel_buttons.append(button)

        top_channels_layout.addStretch(1)  # 把复选框推到左边

        # 3. 创建下方的主内容区 (它内部是一个水平布局)
        bottom_area_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_area_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)  # 内部无边距

        # --- 3.1 创建左侧的控制面板 (除了通道选择之外的所有东西) ---
        left_control_panel = QWidget()
        left_control_panel.setObjectName("ControlPanel")
        left_control_panel.setFixedWidth(180)  # 可以稍微宽一点
        left_layout = QVBoxLayout(left_control_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(5)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 添加记录控制部分
        left_layout.addWidget(QLabel("<b>状态:</b>"))
        self.status_label = QLabel("未开始")
        left_layout.addWidget(self.status_label)

        self.record_button = QPushButton("开始记录")
        self.record_button.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold;")
        self.record_button.clicked.connect(self.toggle_recording)
        left_layout.addWidget(self.record_button)

        self.stop_button = QPushButton("停止记录")
        self.stop_button.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold;")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_recording)
        left_layout.addWidget(self.stop_button)

        # 添加事件标记部分
        left_layout.addWidget(QLabel("<b>事件标记:</b>"))
        self.event_label_input = QLineEdit("DefaultEvent")
        self.event_label_input.setPlaceholderText("输入事件标签...")
        left_layout.addWidget(self.event_label_input)
        self.mark_event_button = QPushButton("标记事件 (Space)")
        self.mark_event_button.setStyleSheet("background-color: #3498db; color: white;")
        self.mark_event_button.setEnabled(False)
        self.mark_event_button.clicked.connect(self.mark_event)
        left_layout.addWidget(self.mark_event_button)

        left_layout.addStretch(1)  # 弹性空间

        # 添加脑电节律分析部分
        rhythm_title = QLabel("<b>Brainwave Rhythms (Avg)</b>")
        rhythm_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(rhythm_title)
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        left_layout.addWidget(separator)

        self.rhythm_bands = {
            'Delta (1-4 Hz)': (1, 4, '#7f8c8d'),
            'Theta (4-8 Hz)': (4, 8, '#9b59b6'),
            'Alpha (8-13 Hz)': (8, 13, '#3498db'),
            'Beta (13-30 Hz)': (13, 30, '#2ecc71'),
            'Gamma (30-100 Hz)': (30, 100, '#f1c40f')
        }
        self.rhythm_progress_bars = {}
        rhythm_bars_layout = QGridLayout()
        row = 0
        for name, (f_low, f_high, color) in self.rhythm_bands.items():
            bar_label = QLabel(name)
            progress_bar = QProgressBar()
            progress_bar.setRange(0, 100)
            progress_bar.setTextVisible(True)
            progress_bar.setFormat(f"%p%")
            progress_bar.setStyleSheet(f"""
                QProgressBar {{ border: 1px solid grey; border-radius: 5px; text-align: center; }}
                QProgressBar::chunk {{ background-color: {color}; width: 10px; }}
            """)
            rhythm_bars_layout.addWidget(bar_label, row, 0)
            rhythm_bars_layout.addWidget(progress_bar, row, 1)
            self.rhythm_progress_bars[name] = progress_bar
            row += 1
        left_layout.addLayout(rhythm_bars_layout)

        # --- 3.2 创建右侧的绘图区域 ---
        plot_area_widget = QWidget()
        plot_layout = QGridLayout(plot_area_widget)
        plot_layout.setColumnStretch(0, 3)
        plot_layout.setColumnStretch(1, 1)

        # 将左侧控制面板和右侧绘图区添加到下方主区域的水平布局中
        bottom_layout.addWidget(left_control_panel)
        bottom_layout.addWidget(plot_area_widget)

        # 4. 将顶部通道栏和下方主区域添加到主布局中
        main_layout.addWidget(top_channels_bar)
        main_layout.addWidget(bottom_area_widget)

        # 设置主窗口的中央部件
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        # =============================================================================
        # --- UI布局重构结束 ---
        # =============================================================================

        self.create_menu_bar()

        # --- 创建图表并添加到绘图区域 ---
        self.time_plots = []
        self.freq_plots = []
        self.plot_widgets_per_channel = []
        self.time_curves = []
        self.freq_curves = []

        self.time_axis = np.linspace(-PLOT_DURATION_S, 0, PLOT_SAMPLES)
        self.freq_axis = np.fft.rfftfreq(NFFT, d=1.0 / SAMPLES_PER_SECOND)
        freq_mask = self.freq_axis <= MAX_FREQ_TO_SHOW

        for i in range(NUM_CHANNELS):
            current_color = self.channel_colors[i % len(self.channel_colors)]
            plot_time = pg.PlotWidget(title=f"Channel {i + 1} - Time Domain")
            plot_time.setLabel('left', 'Amplitude (uV)')
            plot_time.setLabel('bottom', 'Time (s)')
            plot_time.showGrid(x=True, y=True, alpha=0.3)
            pen_time = pg.mkPen(color=current_color, width=2)
            curve_time = plot_time.plot(pen=pen_time)
            self.time_plots.append(plot_time)
            self.time_curves.append(curve_time)

            plot_freq = pg.PlotWidget(title=f"CH{i + 1} - Frequency Domain")
            plot_freq.setLabel('left', 'Magnitude')
            plot_freq.setLabel('bottom', 'Frequency (Hz)')
            plot_freq.showGrid(x=True, y=True, alpha=0.3)
            plot_freq.setXRange(0, MAX_FREQ_TO_SHOW)
            pen_freq = pg.mkPen(color=current_color)
            curve_freq = plot_freq.plot(pen=pen_freq)
            self.freq_plots.append(plot_freq)
            self.freq_curves.append(curve_freq)

            plot_layout.addWidget(plot_time, i, 0)
            plot_layout.addWidget(plot_freq, i, 1)
            self.plot_widgets_per_channel.append((plot_time, plot_freq))

        # --- 设置定时器 ---
        self.timer = QTimer()
        self.timer.setInterval(PLOT_UPDATE_INTERVAL_MS)
        self.timer.timeout.connect(self.update_plots)

    def create_menu_bar(self):
        menu_bar = self.menuBar()  # 获取主窗口的菜单栏

        # 创建“文件”菜单 (可选，为未来扩展做准备)
        file_menu = menu_bar.addMenu("&文件")
        quit_action = file_menu.addAction("退出")
        quit_action.triggered.connect(self.close)

        # 创建“设置”菜单
        settings_menu = menu_bar.addMenu("&设置")
        params_action = settings_menu.addAction("参数配置...")
        params_action.triggered.connect(self.open_settings_dialog)

    def open_settings_dialog(self):
        # 创建设置对话框实例，将当前的设置传递给它
        dialog = SettingsDialog(self.app_settings, self)

        # 以模态方式执行对话框，这意味着在关闭对话框之前，无法与主窗口交互
        # exec() 返回一个布尔值，如果用户点击“确定”则为True
        if dialog.exec():
            # 如果用户点击了“确定”，就获取新的设置
            new_settings = dialog.get_settings()
            print("Settings updated:", new_settings)
            # 在这里，我们将应用新的设置
            self.apply_new_settings(new_settings)
        else:
            print("Settings dialog cancelled.")

    def apply_new_settings(self, new_settings):

        global PLOT_DURATION_S, PLOT_SAMPLES, NFFT
        # 保存新的设置
        self.app_settings = new_settings
        print("Applying new settings:", self.app_settings)

        # --- 1. 更新绘图参数 ---
        # 检查绘图时长是否发生了变化
        new_duration = self.app_settings['plot_duration_s']
        # 使用 np.isclose 来比较浮点数，避免精度问题
        if not np.isclose(new_duration, PLOT_DURATION_S):
            print(f"Plot duration changed to {new_duration}s. Resetting plots.")

            PLOT_DURATION_S = new_duration
            PLOT_SAMPLES = int(SAMPLES_PER_SECOND * PLOT_DURATION_S)
            NFFT = PLOT_SAMPLES

            self.time_axis = np.linspace(-PLOT_DURATION_S, 0, PLOT_SAMPLES)

            print(f"Recreating data deques with new maxlen={PLOT_SAMPLES}")
            for i in range(len(self.filtered_data_queues)):
                self.filtered_data_queues[i] = deque(maxlen=PLOT_SAMPLES)

            # 清除图表上现有的曲线，以便从头开始绘制
            for curve in self.time_curves:
                curve.clear()
            for curve in self.freq_curves:
                curve.clear()

            # 更新时域图的X轴范围
            for plot in self.time_plots:
                plot.setXRange(-PLOT_DURATION_S, 0)

        # --- 2. 更新滤波器参数 ---
        # 创建一个命令字典
        command = {
            'type': 'UPDATE_SETTINGS',
            'data': {
                'highpass_cutoff': self.app_settings['highpass_cutoff'],
                'notch_filter_enabled': self.app_settings['notch_filter_enabled']
            }
        }
        # 将命令放入队列
        self.command_queue.put(command)
        print("Filter settings update command sent to backend.")



    def keyPressEvent(self, event: QEvent):
        """当键盘按键被按下时，此方法被调用"""
        # 检查按下的键是不是空格键
        if event.key() == Qt.Key.Key_Space:
            # 检查“标记事件”按钮当前是否可用
            if self.mark_event_button.isEnabled():
                # 如果可用，就调用它的 mark_event 方法
                self.mark_event()
                # event.accept() 表示我们已经处理了这个事件，它不会再被传递
                event.accept()
            else:
                # 如果按钮不可用，我们也接受事件，防止空格键触发其他行为（比如激活某个按钮）
                event.accept()
        else:
            # 如果是其他按键，我们调用父类的同名方法，以保证其他快捷键（如Tab切换）正常工作
            super().keyPressEvent(event)

    def mark_event(self):
        """当“标记事件”按钮被点击时调用"""
        # 获取当前的精确时间
        event_time = time.time()

        event_label = self.event_label_input.text()

        if not event_label:
            event_label = "UnnamedEvent"

        # 创建我们约定的标记元组
        marker_data = ('MARKER', event_time, event_label)
        # 放入队列
        self.storage_queue.put(marker_data)
        print(f"UI: Event '{event_label}' marker sent at {event_time}")

        lines_for_this_event = []

        for i in range(NUM_CHANNELS):
            if self.channel_checkboxes[i].isChecked():
                # 为这个通道创建一个全新的 InfiniteLine 实例
                marker_line = pg.InfiniteLine(pos=0, angle=90, movable=True,
                                              pen=pg.mkPen('r', width=2, style=Qt.PenStyle.DashLine))
                # 将这个新创建的线添加到对应的图表中
                self.time_plots[i].addItem(marker_line)
                # 将这个新创建的线的引用添加到列表中
                lines_for_this_event.append(marker_line)

        if lines_for_this_event:
            self.marker_lines.append(lines_for_this_event)

            # 4. 设置一个定时器，在3秒后移除这次事件创建的这一组线
            QTimer.singleShot(3000, lambda: self.remove_marker_lines_group(lines_for_this_event))

    def remove_marker_lines_group(self, lines_group_to_remove):
        """从所有图表中移除指定的标记线"""
        if lines_group_to_remove in self.marker_lines:
            # 遍历这组线中的每一条线
            for line in lines_group_to_remove:
                try:
                    line.setVisible(False)
                except Exception as e:
                    print(f"Error removing line: {e}")

            self.marker_lines.remove(lines_group_to_remove)

    def toggle_recording(self):
        if not self.recording_event.is_set():
            # 这是“开始记录”或“继续记录”的逻辑
            self.recording_event.set()  # 设置Event为True
            self.record_button.setText("暂停记录")
            self.record_button.setStyleSheet("background-color: #f39c12; color: white; font-weight: bold;")
            self.stop_button.setEnabled(True)
            self.mark_event_button.setEnabled(True)
            self.status_label.setText("状态: 正在记录...")
            self.status_label.setStyleSheet("color: green;")
        else:
            # 这是“暂停记录”的逻辑
            self.recording_event.clear()  # 设置Event为False
            self.record_button.setText("继续记录")
            self.record_button.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold;")
            self.mark_event_button.setEnabled(False)
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
        self.mark_event_button.setEnabled(False)
        self.status_label.setText("状态: 记录已停止")
        self.status_label.setStyleSheet("color: red;")

    def update_channel_visibility(self, channel_index, is_visible):
        """当复选框状态改变时，此函数被调用"""
        print(f"Channel {channel_index + 1} visibility set to: {is_visible}")

        # 获取该通道对应的时域和频域图表
        time_plot_widget, freq_plot_widget = self.plot_widgets_per_channel[channel_index]

        # 根据传入的状态设置它们的可见性
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
            self.recording_event,
            self.command_queue
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
        """定时器调用的更新函数 (最终修正版)"""
        # 准备用于计算平均功率的变量
        psd_list_for_avg = []

        # 预先获取一次 freqs，因为它对于所有通道都是一样的
        # 确保 NFFT 是最新的
        freqs, _ = signal.welch(np.zeros(NFFT), fs=SAMPLES_PER_SECOND, nperseg=NFFT)

        # --- 第一部分：更新每个通道的图表，并收集用于平均的PSD ---
        for i in range(NUM_CHANNELS):
            if not self.channel_buttons[i].isChecked():
                continue

            current_data = self.filtered_data_queues[i]
            num_samples = len(current_data)

            # 只要有数据就更新时域图
            if num_samples > 0:
                data_copy = np.array(current_data)
                time_data_subset = self.time_axis[-num_samples:]
                self.time_curves[i].setData(x=time_data_subset, y=data_copy)

            # 只有数据足够时才更新频域图并收集PSD
            if num_samples >= NFFT:
                data_copy = np.array(current_data)  # 确保我们有数组
                _, psd = signal.welch(data_copy - np.mean(data_copy), fs=SAMPLES_PER_SECOND, nperseg=NFFT)

                freq_mask = freqs <= MAX_FREQ_TO_SHOW
                self.freq_curves[i].setData(x=freqs[freq_mask], y=psd[freq_mask])

                psd_list_for_avg.append(psd)

        # --- 第二部分：如果收集到了PSD数据，则计算平均值并更新能量条 ---
        if psd_list_for_avg:
            # 计算平均PSD
            avg_psd = np.mean(psd_list_for_avg, axis=0)

            # --- 关键修复：使用 freqs 而不是 self.freq_axis ---
            total_power_freq_range = (freqs >= 1) & (freqs <= 100)

            # np.trapz(y, x) 使用梯形法则进行积分，比 np.sum 更精确
            total_power = np.trapezoid(avg_psd[total_power_freq_range], freqs[total_power_freq_range])

            if total_power > 1e-12:  # 提高一点阈值
                for name, (f_low, f_high, color) in self.rhythm_bands.items():
                    band_mask = (freqs >= f_low) & (freqs < f_high)
                    band_power = np.trapezoid(avg_psd[band_mask], freqs[band_mask])

                    relative_power = (band_power / total_power) * 100
                    self.rhythm_progress_bars[name].setValue(int(relative_power))


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
                font-family: "Segoe UI", Arial, sans-serif;
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
            QFrame[frameShape="4"] {
                border: 1px solid #D0D0D0;
            }

            /* --- 复选框(QCheckBox)的详细样式 (保留，以备将来使用) --- */
            QCheckBox {
                spacing: 5px;
                background-color: transparent;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
            }
            QCheckBox::indicator:unchecked {
                background-color: #FFFFFF;
                border: 2px solid #A9A9A9;
            }
            QCheckBox::indicator:unchecked:hover {
                border: 2px solid #3498db;
            }
            QCheckBox::indicator:checked {
                background-color: #3498db;
                border: 2px solid #3498db;
                image: url(C:/Windows/System32/shell32.dll:105);
            }

            /* ============================================================= */
            /* --- 新增：通道选择按钮的精确样式 --- */
            /* ============================================================= */

            /* 使用属性选择器来选中所有对象名以'channelButton_'开头的按钮 */
            QPushButton[objectName^="channelButton_"] {
                background-color: #E0E0E0; /* 默认/未选中时的背景色 */
                border: 1px solid #B0B0B0;
                border-radius: 4px;
                font-weight: bold;
                padding: 2px; /* 增加一点内边距 */
            }

            QPushButton[objectName^="channelButton_"]:hover {
                background-color: #F0F0F0; /* 鼠标悬停 */
                border-color: #3498db; /* 边框变蓝 */
            }

            QPushButton[objectName^="channelButton_"]:checked {
                background-color: #3498db; /* 选中时的背景色 (蓝色) */
                color: white;              /* 选中时文字变白色 */
                border: 1px solid #2980b9; /* 边框变深蓝 */
            }

            /* 
             * --- 显示“对号”的方案选择 ---
             * 你可以取消下面一个方案的注释来启用它。
             * 推荐方案A，因为它最简单可靠。
            */

            /* 方案A: 在选中按钮的文字前添加一个✔字符 (无需图片) */
            QPushButton[objectName^="channelButton_"]:checked:!text-isEmpty {
                padding-left: 5px; /* 为图标留出空间 */
            }
            QPushButton[objectName^="channelButton_"]:checked::before {
                 content: "✔";
                 padding-right: 3px;
            }


            /*
            // 方案B: 使用外部图标文件 (更专业)
            // 1. 找到一个名为 'check.png' 的白色对号图标文件
            // 2. 把它放到和你的.py脚本相同的目录下
            // 3. 取消下面这几行代码的注释

            QPushButton[objectName^="channelButton_"]:checked {
                qproperty-icon: url(check.png); 
                qproperty-iconSize: 12px;
                padding-left: 5px;
            }
            */

        """
    app.setStyleSheet(light_theme_stylesheet)

    main_window = MainWindow()
    main_window.show()

    QTimer.singleShot(100, main_window.start_monitoring)

    print("Starting Qt event loop...")
    sys.exit(app.exec())