"""
Yuehao
(WiFi Version - Refactored UI)
"""

import sys
import numpy as np
from collections import deque
from queue import Queue
import pyqtgraph as pg
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QGridLayout,
                             QVBoxLayout, QCheckBox, QHBoxLayout, QFrame, QLabel,
                             QPushButton, QSizePolicy, QLineEdit, QProgressBar,
                             QGroupBox, QFileDialog, QInputDialog, QMenu, QStackedWidget,
                             QFormLayout, QComboBox, QToolButton, QScrollArea)
from PyQt6.QtCore import QTimer, Qt, QEvent, QParallelAnimationGroup, QPropertyAnimation, QAbstractAnimation
from PyQt6.QtGui import QIcon, QDoubleValidator
import threading
import time
from scipy import signal
import os
import sys

import backend

class CollapsibleBox(QWidget):
    """
    一个可折叠的自定义控件，外观类似一个可点击的 QGroupBox。
    """

    def __init__(self, title="", parent=None):
        super(CollapsibleBox, self).__init__(parent)

        self.toggle_button = QToolButton(text=title, checkable=True, checked=False)
        self.toggle_button.setObjectName("collapsibleTitle")
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle_button.pressed.connect(self.on_pressed)

        # content_area 现在是一个简单的容器，我们将用布局来管理它里面的 content_widget
        self.content_area = QFrame()
        self.content_area.setObjectName("collapsibleContent")
        self.content_area.setMaximumHeight(0)
        self.content_area.setMinimumHeight(0)
        self.content_area.setFrameShape(QFrame.Shape.NoFrame)
        # 布局将在 setContentWidget 中创建

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.toggle_button)
        main_layout.addWidget(self.content_area)

        self.animation = QPropertyAnimation(self.content_area, b"maximumHeight")

    def on_pressed(self):
        checked = self.toggle_button.isChecked()
        self.toggle_button.setArrowType(Qt.ArrowType.DownArrow if not checked else Qt.ArrowType.RightArrow)
        self.animation.setDirection(
            QAbstractAnimation.Direction.Forward if not checked else QAbstractAnimation.Direction.Backward
        )
        self.animation.start()

    def setContentWidget(self, widget):
        # 使用一个布局来管理 content_area 里的 widget
        content_layout = QVBoxLayout()
        content_layout.addWidget(widget)
        self.content_area.setLayout(content_layout)

        # 设置动画参数
        content_height = widget.sizeHint().height()
        self.animation.setDuration(200)
        self.animation.setStartValue(0)
        self.animation.setEndValue(content_height)

def resource_path(relative_path):
    """ 获取资源的绝对路径，适用于开发环境和打包后的环境 """
    try:
        # PyInstaller 创建一个临时文件夹并将路径存储在 _MEIPASS 中
        base_path = sys._MEIPASS
    except Exception:
        # 如果在开发环境中运行，_MEIPASS 不存在
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# --- config ---
NUM_CHANNELS = backend.NUM_CHANNELS
SAMPLES_PER_SECOND = backend.SAMPLES_PER_SECOND
PLOT_DURATION_S = 5
PLOT_SAMPLES = int(SAMPLES_PER_SECOND * PLOT_DURATION_S)
PLOT_UPDATE_INTERVAL_MS = 100                                      # 刷新率 (ms), 40ms -> 25Hz
NFFT = PLOT_SAMPLES
MAX_FREQ_TO_SHOW = 100


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # --- 模式跟踪 ---
        self.is_offline_mode = False
        self.is_overlay_mode = False
        self.OVERLAY_CHANNEL_OFFSET = 100
        self.SAMPLES_PER_SECOND = backend.SAMPLES_PER_SECOND
        self.PLOT_DURATION_S = 5
        self.PLOT_SAMPLES = int(self.SAMPLES_PER_SECOND * self.PLOT_DURATION_S)
        self.PLOT_UPDATE_INTERVAL_MS = 100
        self.NFFT = self.PLOT_SAMPLES
        self.MAX_FREQ_TO_SHOW = 100
        self.channel_names = [f"CH{i + 1}" for i in range(NUM_CHANNELS)]
        self.app_settings = {
            'highpass_cutoff': backend.HIGHPASS_CUTOFF,
            'lowpass_cutoff': 100.0,
            'notch_filter_enabled': True,
            'plot_duration_s': self.PLOT_DURATION_S
        }

        # --- 队列初始化 ---
        self.recording_event = threading.Event()
        self.storage_queue = Queue()
        # self.command_queue_ble = Queue() # <--- 移除
        self.command_queue_filter = Queue()  # <--- 保留这个
        self.marker_lines = []
        self.filtered_data_queues = [deque(maxlen=self.PLOT_SAMPLES) for _ in range(NUM_CHANNELS)]
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
        # --- UI布局 顶部通道栏 + 左侧控制面板 ---
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
            button = QPushButton(self.channel_names[i])
            button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            button.customContextMenuRequested.connect(lambda pos, index=i: self.show_channel_rename_menu(index, pos))
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

        self.toggle_view_button = QPushButton("叠加模式")
        self.toggle_view_button.setCheckable(True)  # 让它像一个开关
        self.toggle_view_button.toggled.connect(self.toggle_view_mode)
        top_channels_layout.addWidget(self.toggle_view_button)

        # 3. 创建下方的主内容区
        bottom_area_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_area_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)  # 内部无边距

        # --- 3.1 创建左侧的控制面板 ---
        # 创建一个 QScrollArea 来容纳左侧面板
        left_panel_scroll_area = QScrollArea()
        left_panel_scroll_area.setObjectName("ControlPanel")  # 让滚动区域也应用背景色
        left_panel_scroll_area.setFixedWidth(240)  # 稍微加宽一点以容纳滚动条
        left_panel_scroll_area.setWidgetResizable(True)  # 关键：允许内部控件随滚动区自动调整大小
        left_panel_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        left_panel_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)  # 禁用水平滚动条

        # left_control_panel 现在是滚动区域的 *内容*
        left_control_panel = QWidget()
        left_control_panel.setObjectName("ControlPanelContent")  # 给它一个不同的名字以便QSS控制

        left_layout = QVBoxLayout(left_control_panel)
        left_layout.setContentsMargins(10, 10, 15, 10)
        left_layout.setSpacing(10)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # ---- 将 left_control_panel 设置为 QScrollArea 的内容控件 ----
        left_panel_scroll_area.setWidget(left_control_panel)

        # --- 记录控制部分 ---
        record_group = QGroupBox()  # 作为纯粹的容器
        record_group.setTitle("")  # 标题由 CollapsibleBox 提供
        record_group_layout = QGridLayout(record_group)
        record_group_layout.setHorizontalSpacing(10)
        record_group_layout.setVerticalSpacing(5)
        self.status_label = QLabel("未开始")
        self.status_label.setObjectName("StatusLabel_Idle")
        self.record_button = QPushButton("开始记录")
        self.record_button.setObjectName("RecordButton_Start")
        self.record_button.setMinimumHeight(30)
        self.record_button.clicked.connect(self.toggle_recording)
        self.stop_button = QPushButton("停止记录")
        self.stop_button.setObjectName("RecordButton_Stop")
        self.stop_button.setMinimumHeight(30)
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_recording)
        record_group_layout.addWidget(QLabel("状态:"), 0, 0)
        record_group_layout.addWidget(self.status_label, 0, 1)
        record_group_layout.addWidget(self.record_button, 1, 0)
        record_group_layout.addWidget(self.stop_button, 1, 1)

        collapsible_record = CollapsibleBox("记录控制")
        collapsible_record.setContentWidget(record_group)
        left_layout.addWidget(collapsible_record)

        # --- 事件标记部分 ---
        marker_group = QGroupBox()
        marker_group.setTitle("")
        marker_group_layout = QVBoxLayout(marker_group)
        self.event_label_input = QLineEdit("DefaultEvent")
        self.event_label_input.setPlaceholderText("输入事件标签...")
        self.mark_event_button = QPushButton("标记事件 (Space)")
        self.mark_event_button.setObjectName("MarkEventButton")
        self.mark_event_button.setMinimumHeight(30)
        self.mark_event_button.setEnabled(False)
        self.mark_event_button.clicked.connect(self.mark_event)
        marker_group_layout.addWidget(self.event_label_input)
        marker_group_layout.addWidget(self.mark_event_button)

        collapsible_marker = CollapsibleBox("事件标记")
        collapsible_marker.setContentWidget(marker_group)
        left_layout.addWidget(collapsible_marker)

        # --- 脑电节律分析部分 ---
        rhythm_group = QGroupBox()
        rhythm_group.setTitle("")
        rhythm_bars_layout = QGridLayout(rhythm_group)
        rhythm_bars_layout.setVerticalSpacing(8)
        self.rhythm_bands = {
            'Delta (1-4 Hz)': (1, 4, '#7f8c8d'),
            'Theta (4-8 Hz)': (4, 8, '#9b59b6'),
            'Alpha (8-13 Hz)': (8, 13, '#3498db'),
            'Beta (13-30 Hz)': (13, 30, '#2ecc71'),
            'Gamma (30-100 Hz)': (30, 100, '#f1c40f')
        }
        self.rhythm_progress_bars = {}
        row = 0
        for name, (f_low, f_high, color) in self.rhythm_bands.items():
            bar_label = QLabel(name.split(' ')[0])
            progress_bar = QProgressBar()
            progress_bar.setRange(0, 100)
            progress_bar.setTextVisible(True)
            progress_bar.setFormat(f"")
            progress_bar.setStyleSheet(f"""
                                            QProgressBar {{ border: none; border-radius: 4px; background-color: #D0D0D0; height: 12px; }}
                                            QProgressBar::chunk {{ background-color: {color}; border-radius: 4px; }}
                                        """)
            rhythm_bars_layout.addWidget(bar_label, row, 0)
            rhythm_bars_layout.addWidget(progress_bar, row, 1)
            rhythm_bars_layout.setColumnStretch(1, 1)
            self.rhythm_progress_bars[name] = progress_bar
            row += 1

        collapsible_rhythm = CollapsibleBox("脑电节律分析 (Avg)")
        collapsible_rhythm.setContentWidget(rhythm_group)
        left_layout.addWidget(collapsible_rhythm)

        # --- 显示与滤波设置 (内联版) ---
        settings_widget = QWidget()
        settings_layout = QFormLayout(settings_widget)
        settings_layout.setContentsMargins(10, 10, 10, 10)
        settings_layout.setSpacing(10)

        self.plot_duration_input = QLineEdit(str(self.app_settings.get('plot_duration_s', 5)))
        self.plot_duration_input.setValidator(QDoubleValidator(1.0, 20.0, 1, self))
        self.plot_duration_input.editingFinished.connect(self.on_settings_changed)
        settings_layout.addRow("绘图时长 (s):", self.plot_duration_input)

        self.hp_cutoff_input = QLineEdit(str(self.app_settings.get('highpass_cutoff', 0.5)))
        self.hp_cutoff_input.setValidator(QDoubleValidator(0, 10.0, 2, self))
        self.hp_cutoff_input.editingFinished.connect(self.on_settings_changed)
        settings_layout.addRow("高通 (Hz):", self.hp_cutoff_input)

        self.lp_cutoff_input = QLineEdit(str(self.app_settings.get('lowpass_cutoff', 100.0)))
        self.lp_cutoff_input.setValidator(QDoubleValidator(20.0, 120.0, 1, self))
        self.lp_cutoff_input.editingFinished.connect(self.on_settings_changed)
        settings_layout.addRow("低通 (Hz):", self.lp_cutoff_input)

        self.notch_filter_checkbox = QCheckBox()
        self.notch_filter_checkbox.setChecked(self.app_settings.get('notch_filter_enabled', True))
        self.notch_filter_checkbox.stateChanged.connect(self.on_settings_changed)
        settings_layout.addRow("50Hz陷波:", self.notch_filter_checkbox)

        collapsible_settings = CollapsibleBox("参数配置")
        collapsible_settings.setContentWidget(settings_widget)
        left_layout.addWidget(collapsible_settings)

        # --- 设备控制部分 ---
        control_group = QGroupBox()
        control_group.setTitle("")
        control_layout = QFormLayout(control_group)
        self.samplerate_combo = QComboBox()
        self.samplerate_values = {"250 SPS": 0x06, "500 SPS": 0x05, "1 kSPS": 0x04}
        self.samplerate_combo.addItems(self.samplerate_values.keys())
        self.samplerate_combo.setCurrentText("250 SPS")
        self.samplerate_combo.currentIndexChanged.connect(self.on_samplerate_changed)
        control_layout.addRow("采样率:", self.samplerate_combo)
        self.channel_mode_combo = QComboBox()
        self.channel_mode_values = {"正常输入": 0x00, "输入短路": 0x01, "测试信号": 0x05}
        self.channel_mode_combo.addItems(self.channel_mode_values.keys())
        self.channel_mode_combo.currentIndexChanged.connect(self.on_channel_mode_changed)
        control_layout.addRow("所有通道模式:", self.channel_mode_combo)
        self.global_mode_combo = QComboBox()
        self.global_mode_values = {"外部正常输入": 0x00, "内部测试信号": 0x01}
        self.global_mode_combo.addItems(self.global_mode_values.keys())
        self.global_mode_combo.currentIndexChanged.connect(self.on_global_mode_changed)
        control_layout.addRow("全局模式:", self.global_mode_combo)

        collapsible_control = CollapsibleBox("设备控制")
        collapsible_control.setContentWidget(control_group)
        left_layout.addWidget(collapsible_control)

        # 最后的弹性空间
        left_layout.addStretch(1)

        # --- 3.2 创建右侧的绘图区域 ---
        self.plot_stack = QStackedWidget()
        # 视图 0: 多图网格
        self.multi_plot_widget = QWidget()
        plot_layout = QGridLayout(self.multi_plot_widget)
        plot_layout.setColumnStretch(0, 3)
        plot_layout.setColumnStretch(1, 1)

        # 视图 1: 叠加图
        self.overlay_plot_widget = pg.PlotWidget(title="Overlay View")
        self.overlay_plot_widget.setLabel('left', 'Channels')
        self.overlay_plot_widget.setLabel('bottom', 'Time (s)')
        self.overlay_plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.overlay_plot_widget.getAxis('left').setTicks([])

        self.plot_stack.addWidget(self.multi_plot_widget)
        self.plot_stack.addWidget(self.overlay_plot_widget)

        # 将左侧控制面板和右侧绘图区添加到下方主区域的水平布局中
        bottom_layout.addWidget(left_panel_scroll_area)
        bottom_layout.addWidget(self.plot_stack)

        # 4. 将顶部通道栏和下方主区域添加到主布局中
        main_layout.addWidget(top_channels_bar)
        main_layout.addWidget(bottom_area_widget)

        # 设置主窗口的中央部件
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        # =============================================================================
        # --- UI布局结束 ---
        # =============================================================================

        self.create_menu_bar()

        # --- 创建图表并添加到绘图区域 ---
        self.time_plots = []
        self.freq_plots = []
        self.plot_widgets_per_channel = []
        self.time_curves = []
        self.freq_curves = []

        self.overlay_curves = []
        self.overlay_ch_labels = []

        self.time_axis = np.linspace(-PLOT_DURATION_S, 0, self.PLOT_SAMPLES)
        self.freq_axis = np.fft.rfftfreq(NFFT, d=1.0 / self.SAMPLES_PER_SECOND)
        freq_mask = self.freq_axis <= MAX_FREQ_TO_SHOW

        title_style = {'color': '#444', 'font-size': '10pt'}

        for i in range(NUM_CHANNELS):
            # current_color = self.channel_colors[i % len(self.channel_colors)]
            current_color = self.channel_colors[i]

            plot_time = pg.PlotWidget()
            plot_time.setTitle(f"{self.channel_names[i]} - Time Domain", **title_style)
            # plot_time = pg.PlotWidget(title=f"{self.channel_names[i]} - Time Domain")
            plot_time.setLabel('left', 'Amplitude (uV)')
            plot_time.setLabel('bottom', 'Time (s)')
            plot_time.showGrid(x=True, y=True, alpha=0.3)
            plot_time.getAxis('left').setWidth(40)
            pen_time = pg.mkPen(color=current_color, width=2)
            curve_time = plot_time.plot(pen=pen_time)
            self.time_plots.append(plot_time)
            self.time_curves.append(curve_time)

            plot_freq = pg.PlotWidget()
            plot_freq.setTitle(f"{self.channel_names[i]} - Frequency Domain", **title_style)
            # plot_freq = pg.PlotWidget(title=f"{self.channel_names[i]} - Frequency Domain")
            plot_freq.setLabel('left', 'Magnitude')
            plot_freq.setLabel('bottom', 'Frequency (Hz)')
            plot_freq.showGrid(x=True, y=True, alpha=0.3)
            plot_freq.setXRange(0, MAX_FREQ_TO_SHOW)
            plot_freq.getAxis('left').setWidth(40)
            pen_freq = pg.mkPen(color=current_color)
            curve_freq = plot_freq.plot(pen=pen_freq)
            self.freq_plots.append(plot_freq)
            self.freq_curves.append(curve_freq)

            plot_layout.addWidget(plot_time, i, 0)
            plot_layout.addWidget(plot_freq, i, 1)

            # /* overlay curve */
            # 1. 创建曲线
            pen_overlay = pg.mkPen(color=current_color, width=1)
            overlay_curve = self.overlay_plot_widget.plot(pen=pen_overlay)
            self.overlay_curves.append(overlay_curve)
            # 2. 创建通道名称标签
            ch_label = pg.TextItem(self.channel_names[i], color=current_color, anchor=(0, 0.5))
            # 计算标签的初始位置
            label_y_pos = -i * self.OVERLAY_CHANNEL_OFFSET
            ch_label.setPos(-PLOT_DURATION_S, label_y_pos)  # 放在最左侧
            self.overlay_plot_widget.addItem(ch_label)
            self.overlay_ch_labels.append(ch_label)
            # 设置叠加图的Y轴范围
            self.overlay_plot_widget.setYRange(
                -(NUM_CHANNELS) * self.OVERLAY_CHANNEL_OFFSET,
                1 * self.OVERLAY_CHANNEL_OFFSET
            )

            self.plot_widgets_per_channel.append((plot_time, plot_freq))

        # for i in range(NUM_CHANNELS):
        #     plot_layout.setRowStretch(i, 1)

        plot_layout.setVerticalSpacing(2)
        plot_layout.setHorizontalSpacing(5)

        self.rearrange_plots()

        # --- 设置定时器 ---
        self.timer = QTimer()
        self.timer.setInterval(PLOT_UPDATE_INTERVAL_MS)
        self.timer.timeout.connect(self.update_plots)

    def create_menu_bar(self):
        menu_bar = self.menuBar()  # 获取主窗口的菜单栏

        # 创建“文件”菜单
        file_menu = menu_bar.addMenu("&文件")

        open_action = file_menu.addAction("打开 .mat 文件...")
        open_action.triggered.connect(self.open_mat_file)
        self.return_to_live_action = file_menu.addAction("返回实时监控")
        self.return_to_live_action.triggered.connect(self.return_to_live_mode)
        self.return_to_live_action.setEnabled(False)  # 初始时不可用
        file_menu.addSeparator()

        quit_action = file_menu.addAction("退出")
        quit_action.triggered.connect(self.close)

        # 创建“设置”菜单
        # settings_menu = menu_bar.addMenu("&设置")
        # params_action = settings_menu.addAction("参数配置...")
        # params_action.triggered.connect(self.open_settings_dialog)

    # def open_settings_dialog(self):
    #     # 创建设置对话框实例，将当前的设置传递给它
    #     dialog = SettingsDialog(self.app_settings, self)
    #
    #     # 以模态方式执行对话框，这意味着在关闭对话框之前，无法与主窗口交互
    #     # exec() 返回一个布尔值，如果用户点击“确定”则为True
    #     if dialog.exec():
    #         # 如果用户点击了“确定”，就获取新的设置
    #         new_settings = dialog.get_settings()
    #         print("Settings updated:", new_settings)
    #         # 在这里，我们将应用新的设置
    #         self.apply_new_settings(new_settings)
    #     else:
    #         print("Settings dialog cancelled.")

    def show_channel_rename_menu(self, channel_index, position):
        """当在通道按钮上右键点击时，显示一个菜单"""
        menu = QMenu()
        rename_action = menu.addAction("重命名通道...")

        # 使用 self.channel_buttons[channel_index] 来获取正确的按钮
        action = menu.exec(self.channel_buttons[channel_index].mapToGlobal(position))

        if action == rename_action:
            self.rename_channel(channel_index)

    def rename_channel(self, channel_index):
        """弹出一个对话框来重命名指定的通道"""
        current_name = self.channel_names[channel_index]

        # 弹出输入对话框
        new_name, ok = QInputDialog.getText(
            self,
            "重命名通道",
            f"为通道 {channel_index + 1} 输入新名称:",
            QLineEdit.EchoMode.Normal,
            current_name
        )

        # 如果用户点击了"OK"并且输入了非空的新名称
        if ok and new_name:
            # 检查名称是否已存在
            if new_name in self.channel_names:
                # 弹出一个警告框
                print(f"Warning: Channel name '{new_name}' already exists.")
                return

            print(f"Renaming channel {channel_index + 1} from '{current_name}' to '{new_name}'")

            # 1. 更新数据结构
            self.channel_names[channel_index] = new_name

            # 2. 更新UI
            self.channel_buttons[channel_index].setText(new_name)
            time_plot, freq_plot = self.plot_widgets_per_channel[channel_index]
            time_plot.setTitle(f"{new_name} - Time Domain")
            freq_plot.setTitle(f"{new_name} - Frequency Domain")

            self.overlay_ch_labels[channel_index].setText(new_name)

    def toggle_view_mode(self, checked):
        self.is_overlay_mode = checked
        if checked:
            self.plot_stack.setCurrentWidget(self.overlay_plot_widget)
            self.toggle_view_button.setText("多图模式")
        else:
            self.plot_stack.setCurrentWidget(self.multi_plot_widget)
            self.toggle_view_button.setText("叠加模式")

    def apply_new_settings(self, new_settings, force_recreate_plots=False):
        # 保存新的设置
        self.app_settings = new_settings
        print("Applying new settings:", self.app_settings)

        new_duration = self.app_settings['plot_duration_s']

        # 准备要发送给后端的命令数据
        command_data = {
            'samples_per_second': self.SAMPLES_PER_SECOND,
            'highpass_cutoff': self.app_settings['highpass_cutoff'],
            'lowpass_cutoff': self.app_settings['lowpass_cutoff'],
            'notch_filter_enabled': self.app_settings['notch_filter_enabled']
        }

        # --- 统一的逻辑块，处理所有需要重绘的情况 ---
        if force_recreate_plots or not np.isclose(new_duration, self.PLOT_DURATION_S):
            print(f"Recreating plot configurations. SPS: {self.SAMPLES_PER_SECOND}, Duration: {new_duration}s.")

            # 更新UI实例的参数
            self.PLOT_DURATION_S = new_duration
            self.PLOT_SAMPLES = int(self.SAMPLES_PER_SECOND * self.PLOT_DURATION_S)
            self.NFFT = self.PLOT_SAMPLES
            self.time_axis = np.linspace(-self.PLOT_DURATION_S, 0, self.PLOT_SAMPLES)

            # 创建新的数据队列
            print(f"Recreating data deques with new maxlen={self.PLOT_SAMPLES}")
            self.filtered_data_queues = [deque(maxlen=self.PLOT_SAMPLES) for _ in range(NUM_CHANNELS)]

            # 将新队列的引用添加到命令中，以便通知后端
            command_data['new_queues'] = self.filtered_data_queues

            # 清空所有图表上的现有曲线
            for curve in self.time_curves: curve.clear()
            for curve in self.freq_curves: curve.clear()
            for curve in self.overlay_curves: curve.clear()

            # 更新X轴范围以匹配新的时长
            for plot in self.time_plots:
                plot.setXRange(-self.PLOT_DURATION_S, 0)
            self.overlay_plot_widget.setXRange(-self.PLOT_DURATION_S, 0)

        # 构建并发送最终的命令
        command = {
            'type': 'UPDATE_SETTINGS',
            'data': command_data
        }
        self.command_queue_filter.put(command)
        print("Filter settings update command sent to backend.")

    def on_settings_changed(self):
        """
        当内联的设置控件发生变化时调用此方法。
        """
        try:
            # 1. 从UI控件收集所有设置值
            new_settings = {
                'plot_duration_s': float(self.plot_duration_input.text()),
                'highpass_cutoff': float(self.hp_cutoff_input.text()),
                'lowpass_cutoff': float(self.lp_cutoff_input.text()),
                'notch_filter_enabled': self.notch_filter_checkbox.isChecked()
            }

            # 2. 检查设置是否真的发生了变化，避免不必要地重绘
            if new_settings != self.app_settings:
                print("Inline settings changed...")
                # 3. 调用现有的 apply_new_settings 方法来应用更改
                self.apply_new_settings(new_settings)

        except ValueError:
            # 如果用户输入了无效的数字（虽然有Validator，但以防万一），则忽略
            print("Warning: Invalid value in settings input. Ignoring change.")
            pass

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
        """当“标记事件”按钮被点击时调用 (修复版)"""
        event_time = time.time()
        event_label = self.event_label_input.text() or "UnnamedEvent"

        marker_data = ('MARKER', event_time, event_label)
        self.storage_queue.put(marker_data)
        print(f"UI: Event '{event_label}' marker sent at {event_time}")

        # --- lines_for_this_event 现在是一个元组，包含两组线 ---
        # (多图模式的线列表, 叠加图模式的线列表)
        lines_for_this_event = ([], [])
        pen = pg.mkPen('r', width=2, style=Qt.PenStyle.DashLine)

        # 为多图模式添加标记线
        for i in range(NUM_CHANNELS):
            if self.channel_buttons[i].isChecked():
                marker_line_multi = pg.InfiniteLine(pos=0, angle=90, movable=True, pen=pen)
                self.time_plots[i].addItem(marker_line_multi)
                lines_for_this_event[0].append(marker_line_multi)

        # --- 关键新增部分：为叠加图模式添加一条标记线 ---
        # 叠加图只需要一条线就够了
        if any(btn.isChecked() for btn in self.channel_buttons):
            marker_line_overlay = pg.InfiniteLine(pos=0, angle=90, movable=True, pen=pen)
            self.overlay_plot_widget.addItem(marker_line_overlay)
            lines_for_this_event[1].append(marker_line_overlay)

        # 只有在确实创建了线的情况下才进行后续操作
        if lines_for_this_event[0] or lines_for_this_event[1]:
            self.marker_lines.append(lines_for_this_event)
            QTimer.singleShot(3000, lambda: self.remove_marker_lines_group(lines_for_this_event))


    def remove_marker_lines_group(self, lines_group_to_remove):
        """从所有图表中移除指定的标记线组 (修复版)"""
        if lines_group_to_remove in self.marker_lines:
            # lines_group_to_remove 是一个元组: (multi_plot_lines, overlay_plot_lines)
            multi_lines, overlay_lines = lines_group_to_remove

            # 移除多图模式的线
            for line in multi_lines:
                try:
                    # removeItem 比 setVisible(False) 更干净，直接从场景中移除
                    if line.scene():
                        line.scene().removeItem(line)
                except Exception as e:
                    print(f"Error removing multi-plot line: {e}")

            # 移除叠加图模式的线
            for line in overlay_lines:
                try:
                    if line.scene():
                        line.scene().removeItem(line)
                except Exception as e:
                    print(f"Error removing overlay-plot line: {e}")

            self.marker_lines.remove(lines_group_to_remove)


    def toggle_recording(self):
        if not self.recording_event.is_set():
            # 这是“开始记录”或“继续记录”的逻辑
            self.recording_event.set()  # 设置Event为True
            self.record_button.setText("暂停记录")
            self.record_button.setStyleSheet("background-color: #f39c12; color: white; font-weight: bold;")
            self.stop_button.setEnabled(True)
            self.mark_event_button.setEnabled(True)
            self.status_label.setText("正在记录...")
            self.status_label.setObjectName("StatusLabel_Recording")
            # self.status_label.setStyleSheet("color: green;")
        else:
            # 这是“暂停记录”的逻辑
            self.recording_event.clear()  # 设置Event为False
            self.record_button.setText("继续记录")
            self.record_button.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold;")
            self.mark_event_button.setEnabled(False)
            self.status_label.setText("记录暂停")
            self.status_label.setObjectName("StatusLabel_Paused")
            # self.status_label.setStyleSheet("color: orange;")

        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def stop_recording(self):
        # 停止逻辑
        self.recording_event.clear()
        stop_command = ('STOP_RECORDING', self.channel_names)
        self.storage_queue.put(stop_command)  # 发送停止命令

        # 恢复UI到初始状态
        self.record_button.setText("开始记录")
        self.record_button.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold;")
        self.stop_button.setEnabled(False)
        self.mark_event_button.setEnabled(False)
        self.status_label.setText("记录已停止")
        self.status_label.setObjectName("StatusLabel_Stopped")
        # self.status_label.setStyleSheet("color: red;")

        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def rearrange_plots(self):
        """
        清空并根据当前可见的通道重新排列绘图网格。
        """
        # 获取 multi_plot_widget 上的布局
        plot_layout = self.multi_plot_widget.layout()

        # 1. 安全地从布局中移除所有控件，但不要删除它们
        #    这是动态修改布局的标准做法
        while plot_layout.count():
            item = plot_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # 只是从布局中移除，控件本身仍然存在
                widget.setParent(None)

        # 2. 遍历所有通道，只将可见的图表重新添加到布局中
        visible_row_index = 0
        for i in range(NUM_CHANNELS):
            # 检查对应的通道按钮是否被选中
            if self.channel_buttons[i].isChecked():
                # 获取该通道的时域和频域图表
                time_plot_widget, freq_plot_widget = self.plot_widgets_per_channel[i]

                # 将它们添加到新的行中
                plot_layout.addWidget(time_plot_widget, visible_row_index, 0)
                plot_layout.addWidget(freq_plot_widget, visible_row_index, 1)

                # 只有在添加了控件后，才增加行索引
                visible_row_index += 1

        # 3. （可选但推荐）重置行拉伸因子
        #    清除旧的拉伸设置
        for i in range(plot_layout.rowCount()):
            plot_layout.setRowStretch(i, 0)
        #    为新的可见行设置均等拉伸
        for i in range(visible_row_index):
            plot_layout.setRowStretch(i, 1)

    def update_channel_visibility(self, channel_index, is_visible):
        """当通道按钮状态改变时，此函数被调用 (重构版)"""
        print(f"Channel {channel_index + 1} visibility set to: {is_visible}")

        # 1. 更新叠加图中的可见性 (这部分逻辑不变，因为它不涉及布局重排)
        overlay_curve = self.overlay_curves[channel_index]
        overlay_label = self.overlay_ch_labels[channel_index]
        overlay_curve.setVisible(is_visible)
        overlay_label.setVisible(is_visible)

        # 2. 调用新的方法来重排多图网格
        self.rearrange_plots()

        # 3. 如果在离线模式，重新计算节律分析
        if self.is_offline_mode:
            self.recalculate_offline_psd_and_rhythms()

    def recalculate_offline_psd_and_rhythms(self):
        """
        在离线模式下，根据当前可见的通道重新计算平均PSD和脑电节律。
        """
        psd_list_for_avg = []

        # 遍历所有通道，只收集当前可见通道的频域数据
        for i in range(NUM_CHANNELS):
            if self.channel_buttons[i].isChecked():
                # 从频域曲线中直接获取数据
                curve = self.freq_curves[i]
                if curve.yData is not None and len(curve.yData) > 0:
                    psd_list_for_avg.append(curve.yData)

        # 如果有可见的通道，则进行计算
        if psd_list_for_avg:
            avg_psd = np.mean(psd_list_for_avg, axis=0)

            # 获取频域轴 (从任意一个频域曲线)
            freqs = self.freq_curves[0].xData
            if freqs is None: return  # 如果还没有数据，则返回

            total_power_freq_range = (freqs >= 1) & (freqs <= 100)
            total_power = np.trapezoid(avg_psd[total_power_freq_range], freqs[total_power_freq_range])

            if total_power > 1e-12:
                for name, (f_low, f_high, color) in self.rhythm_bands.items():
                    band_mask = (freqs >= f_low) & (freqs < f_high)
                    band_power = np.trapezoid(avg_psd[band_mask], freqs[band_mask])
                    relative_power = (band_power / total_power) * 100
                    self.rhythm_progress_bars[name].setValue(int(relative_power))
        else:
            # 如果所有通道都被隐藏了，则清空能量条
            for name in self.rhythm_bands:
                self.rhythm_progress_bars[name].setValue(0)

    def start_monitoring(self):
        """启动后台线程并开始UI更新 (WiFi 版本)"""
        print("Starting backend threads from Qt App...")
        backend.start_backend_threads(
            self.raw_data_queue, # 注意：需要先创建 self.raw_data_queue
            self.filtered_data_queues,
            self.storage_queue,
            self.recording_event,
            self.command_queue_filter # 只传递这个命令队列
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
        """定时器调用的更新函数 (重构版 - 修复显示bug)"""
        if self.is_offline_mode:
            return

        # =============================================================================
        # --- 第1部分: 核心数据处理与节律分析 (对两种模式都通用) ---
        # =============================================================================
        psd_list_for_avg = []
        psd_results = {}
        freqs = None

        # 遍历所有可见通道计算PSD
        for i in range(NUM_CHANNELS):
            if not self.channel_buttons[i].isChecked():
                continue

            current_data = self.filtered_data_queues[i]
            if len(current_data) >= self.NFFT:
                data_copy = np.array(current_data)
                current_freqs, psd = signal.welch(data_copy - np.mean(data_copy), fs=self.SAMPLES_PER_SECOND, nperseg=self.NFFT)
                if freqs is None:
                    freqs = current_freqs
                psd_list_for_avg.append(psd)
                psd_results[i] = psd

        # 如果收集到PSD数据，则更新能量条
        if psd_list_for_avg and freqs is not None:
            avg_psd = np.mean(psd_list_for_avg, axis=0)
            total_power_freq_range = (freqs >= 1) & (freqs <= 100)
            total_power = np.trapezoid(avg_psd[total_power_freq_range], freqs[total_power_freq_range])

            if total_power > 1e-12:
                for name, (f_low, f_high, color) in self.rhythm_bands.items():
                    band_mask = (freqs >= f_low) & (freqs < f_high)
                    band_power = np.trapezoid(avg_psd[band_mask], freqs[band_mask])
                    relative_power = (band_power / total_power) * 100
                    self.rhythm_progress_bars[name].setValue(int(relative_power))
        # --- 如果没有可见通道，清空能量条 ---
        elif not psd_list_for_avg:
             for name in self.rhythm_bands:
                self.rhythm_progress_bars[name].setValue(0)


        # =============================================================================
        # --- 第2部分: 根据当前视图模式更新UI图表 ---
        # =============================================================================
        if self.is_overlay_mode:
            for i in range(NUM_CHANNELS):
                if self.channel_buttons[i].isChecked():
                    self.overlay_ch_labels[i].setVisible(True)
                    current_data = self.filtered_data_queues[i]
                    num_samples = len(current_data)
                    if num_samples > 0:
                        offset_data = np.array(current_data) - i * self.OVERLAY_CHANNEL_OFFSET
                        time_data_subset = self.time_axis[-num_samples:]
                        self.overlay_curves[i].setData(x=time_data_subset, y=offset_data)
                else:
                    # --- 关键修复：隐藏时清空曲线 ---
                    self.overlay_curves[i].clear()
                    self.overlay_ch_labels[i].setVisible(False)
        else:
            # --- 更新多图 ---
            for i in range(NUM_CHANNELS):
                if self.channel_buttons[i].isChecked():
                    # 更新时域图
                    current_data = self.filtered_data_queues[i]
                    num_samples = len(current_data)
                    if num_samples > 0:
                        time_data_subset = self.time_axis[-num_samples:]
                        self.time_curves[i].setData(x=time_data_subset, y=list(current_data))
                    else:
                        self.time_curves[i].clear() # 如果队列为空也清空

                    # 更新频域图
                    if i in psd_results and freqs is not None:
                        freq_mask = freqs <= self.MAX_FREQ_TO_SHOW
                        self.freq_curves[i].setData(x=freqs[freq_mask], y=psd_results[i][freq_mask])
                    else:
                        self.freq_curves[i].clear() # 如果没有PSD结果也清空
                else:
                    # --- 关键修复：隐藏时清空曲线 ---
                    self.time_curves[i].clear()
                    self.freq_curves[i].clear()


    def open_mat_file(self):
        """当用户点击“打开 .mat 文件...”时调用"""
        # 如果已经在离线模式，先返回实时模式再打开新文件
        if self.is_offline_mode:
            self.return_to_live_mode()

        file_path, _ = QFileDialog.getOpenFileName(
            self, "打开EEG数据文件", "data/", "MAT-files (*.mat)"
        )

        if file_path:
            print(f"Opening file: {file_path}")
            try:
                # 1. 切换到离线模式
                self.is_offline_mode = True
                self.timer.stop()  # 停止实时更新
                self.return_to_live_action.setEnabled(True)  # 启用“返回实时”按钮

                # 2. 更新UI状态
                self.set_ui_for_offline_mode(True)

                # 3. 加载.mat文件
                mat_data = sio.loadmat(file_path, squeeze_me=True)

                # 4. 绘制离线数据
                self.plot_offline_data(mat_data)

            except Exception as e:
                print(f"Error loading or plotting .mat file: {e}")
                self.return_to_live_mode()  # 如果出错，尝试恢复到实时模式

    def plot_offline_data(self, mat_data):
        """将从.mat文件加载的数据绘制到图表上 (支持双视图模式) - 健壮版本"""
        try:
            # --- 1. 安全地提取元数据 ---
            # 安全地获取采样率 (fs)
            fs_raw = mat_data.get('fs', self.SAMPLES_PER_SECOND)
            fs = float(fs_raw.item() if hasattr(fs_raw, 'item') else fs_raw)  # 转换为标准float

            # 安全地获取事件 (events)
            events = mat_data.get('events', np.array([]))
            # 关键修复: 如果只有一个事件，squeeze_me会把它变成一维数组。
            # 我们需要确保它总是二维的，以便循环处理。
            if events.ndim == 1 and events.size > 0:
                events = np.array([events])

            # 安全地获取通道顺序 (channel_order)
            channel_order_raw = mat_data.get('channel_order')
            if channel_order_raw is not None:
                # 关键修复: 如果只有一个通道名, squeeze_me会把它变成一个字符串
                if isinstance(channel_order_raw, str):
                    loaded_channel_names = [channel_order_raw]
                else:  # 否则, 像以前一样处理
                    loaded_channel_names = [str(name).strip() for name in channel_order_raw.flatten()]
            else:
                loaded_channel_names = [f'CH{i + 1}' for i in range(NUM_CHANNELS)]

            self.clear_all_plots()

            # 更新UI和内部数据以匹配加载的通道名称
            self.channel_names = loaded_channel_names + [f"CH{i + 1}" for i in
                                                         range(len(loaded_channel_names), NUM_CHANNELS)]

            # --- 2. 循环绘制每个通道 ---
            for i in range(NUM_CHANNELS):
                ch_name = self.channel_names[i]

                # 更新UI标题和标签
                self.channel_buttons[i].setText(ch_name)
                time_plot, freq_plot = self.plot_widgets_per_channel[i]
                time_plot.setTitle(f"{ch_name} - Time Domain")
                freq_plot.setTitle(f"{ch_name} - Frequency Domain")
                self.overlay_ch_labels[i].setText(ch_name)

                if ch_name in mat_data:
                    ch_data = mat_data[ch_name].flatten()
                    num_samples = len(ch_data)
                    if num_samples == 0: continue

                    time_axis_offline = np.arange(num_samples) / fs

                    # 绘制多图模式
                    self.time_curves[i].setData(x=time_axis_offline, y=ch_data)
                    self.time_plots[i].setXRange(0, time_axis_offline[-1])

                    # 绘制叠加图模式
                    offset_data = ch_data - i * self.OVERLAY_CHANNEL_OFFSET
                    self.overlay_curves[i].setData(x=time_axis_offline, y=offset_data)

                    # 在两种视图上都绘制事件标记
                    if events.size > 0:
                        for event_info in events:
                            if isinstance(event_info, (list, np.ndarray)) and len(event_info) >= 2:
                                event_time_raw, event_label_raw = event_info[0], event_info[1]
                                event_time = float(event_time_raw)
                                event_label = str(event_label_raw)

                                # 在多图上添加标记
                                event_line_multi = pg.InfiniteLine(pos=event_time, angle=90, movable=False,
                                                                   pen=pg.mkPen('g', width=2,
                                                                                style=Qt.PenStyle.DashLine),
                                                                   label=event_label)
                                self.time_plots[i].addItem(event_line_multi)

                                # 在叠加图上也添加标记
                                event_line_overlay = pg.InfiniteLine(pos=event_time, angle=90, movable=False,
                                                                     pen=pg.mkPen('g', width=2,
                                                                                  style=Qt.PenStyle.DashLine),
                                                                     label=event_label)
                                self.overlay_plot_widget.addItem(event_line_overlay)

                    # 绘制频域图
                    freqs, psd = signal.welch(ch_data - np.mean(ch_data), fs=fs, nperseg=min(num_samples, 2048))
                    freq_mask = freqs <= MAX_FREQ_TO_SHOW
                    self.freq_curves[i].setData(x=freqs[freq_mask], y=psd[freq_mask])

            # --- 3. 统一设置叠加图的X轴范围 (更健壮的版本) ---
            first_valid_ch_name = None
            for name in loaded_channel_names:
                if name in mat_data:
                    first_valid_ch_name = name
                    break

            if first_valid_ch_name:
                num_samples_first_ch = mat_data[first_valid_ch_name].size
                max_time = num_samples_first_ch / fs
                self.overlay_plot_widget.setXRange(0, max_time)

                for i in range(NUM_CHANNELS):
                    label_y_pos = -i * self.OVERLAY_CHANNEL_OFFSET
                    self.overlay_ch_labels[i].setPos(0, label_y_pos)
            else:
                print("Warning: Could not find any valid channel data in the .mat file to set plot range.")

            self.recalculate_offline_psd_and_rhythms()

            print("Offline data plotted successfully for both view modes.")
        except Exception as e:
            print(f"An error occurred during offline plotting: {e}")
            # 打印更详细的错误追溯信息，方便调试
            import traceback
            traceback.print_exc()


    def return_to_live_mode(self):
        """恢复到实时监控模式"""
        if not self.is_offline_mode:
            return

        print("Returning to live monitoring mode...")
        # 1. 切换模式标志
        self.is_offline_mode = False
        self.return_to_live_action.setEnabled(False)  # 禁用“返回实时”按钮

        # 2. 清空图表和数据队列
        self.clear_all_plots()
        for q in self.filtered_data_queues:
            q.clear()

        # 3. 恢复UI状态
        self.set_ui_for_offline_mode(False)

        # 4. 恢复实时绘图的X轴范围
        for plot in self.time_plots:
            plot.setXRange(-PLOT_DURATION_S, 0)

        # 5. 重新启动定时器
        self.timer.start()

    def clear_all_plots(self):
        """清空所有图表上的曲线和额外项目 """
        for i in range(NUM_CHANNELS):
            # 清除主曲线
            self.time_curves[i].clear()
            self.freq_curves[i].clear()

            # 移除所有额外添加的item（如事件标记线）
            items_to_remove = [item for item in self.time_plots[i].items() if isinstance(item, pg.InfiniteLine)]
            for item in items_to_remove:
                self.time_plots[i].removeItem(item)

        for curve in self.overlay_curves:
            curve.clear()
        items_to_remove_overlay = [item for item in self.overlay_plot_widget.items() if
                                   isinstance(item, pg.InfiniteLine)]
        for item in items_to_remove_overlay:
            self.overlay_plot_widget.removeItem(item)

        print("All plots cleared.")

    def set_ui_for_offline_mode(self, offline):
        """根据模式启用/禁用UI控件"""
        if offline:
            # 进入离线模式，禁用实时功能
            self.record_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.mark_event_button.setEnabled(False)
            self.status_label.setText("离线浏览模式")
            self.status_label.setObjectName("StatusLabel_Idle")
        else:
            # 返回实时模式，恢复初始状态
            self.record_button.setEnabled(True)
            self.stop_button.setEnabled(False)  # 停止按钮初始是禁用的
            self.mark_event_button.setEnabled(False)  # 标记按钮初始也是禁用的
            self.status_label.setText("未开始")
            self.status_label.setObjectName("StatusLabel_Idle")

        # 统一刷新样式
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def on_samplerate_changed(self):
        rate_text = self.samplerate_combo.currentText()
        rate_value = self.samplerate_values[rate_text]
        self.send_ble_command(0x21, [rate_value])

        new_sps_str = rate_text.split(' ')[0]
        if new_sps_str.lower() == '1k':
            new_sps = 1000
        else:
            new_sps = int(new_sps_str)

        # 检查采样率是否真的改变了
        if new_sps != self.SAMPLES_PER_SECOND:
            print(f"Sample rate changing from {self.SAMPLES_PER_SECOND} to {new_sps}")
            self.SAMPLES_PER_SECOND = new_sps
            # 调用 apply_new_settings 来处理所有连锁更新
            self.apply_new_settings(self.app_settings, force_recreate_plots=True)
    # def on_samplerate_changed(self):
    #     rate_text = self.samplerate_combo.currentText()
    #     rate_value = self.samplerate_values[rate_text]
    #     self.send_ble_command(0x21, [rate_value])
    #
    #     new_sps_str = rate_text.split(' ')[0]  # "250 SPS" -> "250"
    #     if new_sps_str.lower() == '1k':  # 特殊处理 "1 kSPS"
    #         new_sps = 1000
    #     else:
    #         new_sps = int(new_sps_str)
    #     self.SAMPLES_PER_SECOND = new_sps
    #     self.apply_new_settings(self.app_settings)

    def on_channel_mode_changed(self):
        mode_text = self.channel_mode_combo.currentText()
        mode_value = self.channel_mode_values[mode_text]
        self.send_ble_command(0x22, [mode_value])

    def on_global_mode_changed(self):
        mode_text = self.global_mode_combo.currentText()
        mode_value = self.global_mode_values[mode_text]
        self.send_ble_command(0x23, [mode_value])

    def send_ble_command(self, cmd_id, payload_bytes):
        """通用命令发送函数"""
        header = 0xFE
        payload_len = len(payload_bytes)

        # 计算校验和
        checksum = (cmd_id + payload_len + sum(payload_bytes)) & 0xFF

        # 构建数据包, '<'表示小端字节序
        # 格式: Header(B), CMD(B), LEN(B), Payload(*B), Checksum(B)
        # 我们用一个灵活的方式来打包
        packet_list = [header, cmd_id, payload_len] + payload_bytes + [checksum]
        command_packet = bytearray(packet_list)

        # 放入队列，由后台发送
        self.command_queue_ble.put(command_packet)
        print(f"UI: Queued CMD: {command_packet.hex(' ')}")


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
                color: #333333;
                font-family: "Segoe UI", Arial, sans-serif;
            }
            QLineEdit, QCheckBox, QPushButton, QProgressBar {
                font-size: 12px; /* 统一基础字体大小 */
            }

            /* --- 主窗口面板样式 --- */
            #ControlPanel {
                background-color: #EAEAEA;
            }

            /* --- 滚动区域和滚动条美化 (悬浮/纤细风格) --- */
            /* ============================================================= */
            QScrollArea#ControlPanel {
                border: none;
                background-color: #EAEAEA; /* 确保背景色和原来一致 */
            }

            /* 整个滚动条的轨道 (track) */
            QScrollBar:vertical {
                border: none;
                background: transparent; /* 轨道背景完全透明 */
                width: 12px;             /* 为滚动条预留的总空间 */
                margin: 0;
            }

            /* 滚动条的滑块 (handle) */
            QScrollBar::handle:vertical {
                background-color: rgba(0, 0, 0, 0.25); /* 半透明的深灰色 */
                border-radius: 6px;      /* 完全圆角 */
                min-height: 25px;        /* 最小高度 */
            }

            /* 鼠标悬停在滑块上时，变得更不透明 */
            QScrollBar::handle:vertical:hover {
                background-color: rgba(0, 0, 0, 0.45);
            }

            /* 当鼠标按下拖动滑块时，颜色最深 */
            QScrollBar::handle:vertical:pressed {
                background-color: rgba(0, 0, 0, 0.6);
            }

            /* 隐藏上下两个箭头按钮 */
            QScrollBar::sub-line:vertical, QScrollBar::add-line:vertical {
                background: none;
                height: 0;
                subcontrol-position: top;
                subcontrol-origin: margin;
            }

            /* 隐藏滑块上下方的页面滚动区域 */
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }

            /* ============================================================= */
            /* --- 通用组框 (QGroupBox) 样式 --- */
            /* ============================================================= */
            QGroupBox {
                background-color: #FDFDFD;
                border: 1px solid #D0D0D0;
                border-radius: 8px;
                margin-top: 10px;
                padding: 10px 10px 15px 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding-left: 10px;
                padding-right: 10px;
                font-weight: bold;
                color: #2c3e50;
            }

            /* ============================================================= */
            /* --- 设置对话框的特定样式 --- */
            /* ============================================================= */
            #SettingsDialog {
                 background-color: #F0F0F0; /* 对话框背景色 */
            }
            #SettingsDialog QGroupBox {
                padding: 15px; /* 对话框内的组框内边距更大一些 */
            }
            #SettingsDialog QLineEdit {
                 padding: 5px;
                 min-height: 22px;
            }
            #SettingsDialog QPushButton {
                padding: 8px 20px; /* OK/Cancel 按钮更大 */
            }


            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
            }
            /* 未选中状态：白色背景，清晰的深灰色边框 */
            QCheckBox::indicator:unchecked {
                background-color: #FFFFFF;
                border: 2px solid #707070; 
            }
            /* 鼠标悬停在未选中框上：边框变蓝 */
            QCheckBox::indicator:unchecked:hover {
                border: 2px solid #3498db;
            }
            /* 选中状态：蓝色背景，白色对号 */
            QCheckBox::indicator:checked {
                background-color: #3498db;
                border: 2px solid #2980b9;
                /* 使用SVG代码直接绘制一个对号，无需外部文件，跨平台兼容！*/
                image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'><path fill='white' d='M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z'/></svg>");
            }

            /* ============================================================= */
            /* --- 按钮的精细化样式 --- */
            /* ============================================================= */
            QPushButton {
                border-radius: 4px;
                padding: 5px 10px;
                border: 1px solid #B0B0B0;
                background-color: #E0E0E0;
            }
            QPushButton:hover {
                border-color: #3498db;
            }
            QPushButton:pressed {
                background-color: #C0C0C0;
            }

            /* -- 记录按钮的特定颜色 -- */
            #RecordButton_Start { background-color: #2ecc71; color: white; font-weight: bold; }
            #RecordButton_Stop { background-color: #e74c3c; color: white; font-weight: bold; }
            #MarkEventButton { background-color: #3498db; color: white; }

            /* 让禁用的按钮看起来更明显 */
            QPushButton:disabled {
                background-color: #D0D0D0;
                color: #A0A0A0;
            }

            /* --- 状态标签的样式 --- */
            #StatusLabel_Idle { color: #808080; }
            #StatusLabel_Recording { color: #27ae60; font-weight: bold; }
            #StatusLabel_Paused { color: #d35400; font-weight: bold; }
            #StatusLabel_Stopped { color: #c0392b; }

            /* --- 输入框样式 --- */
            QLineEdit {
                background-color: white;
                border: 1px solid #C0C0C0;
                border-radius: 4px;
                padding: 4px;
            }

            /* --- 通道按钮样式 --- */
            QPushButton[objectName^="channelButton_"] {
                background-color: #E0E0E0;
                border: 1px solid #B0B0B0;
                border-radius: 4px;
                font-weight: bold;
                padding: 2px;
            }
            QPushButton[objectName^="channelButton_"]:hover {
                background-color: #F0F0F0;
                border-color: #3498db;
            }
            QPushButton[objectName^="channelButton_"]:checked {
                background-color: #3498db;
                color: white;
                border: 1px solid #2980b9;
            }

            /* --- 可折叠框 (CollapsibleBox) 的样式 (设计感增强版) --- */
            /* ============================================================= */
            QToolButton#collapsibleTitle {
                background-color: transparent; /* 标题按钮本身透明 */
                border: none;
                padding: 5px;
                font-weight: bold;
                text-align: left; /* 文字左对齐 */
            }

            QToolButton#collapsibleTitle:hover {
                background-color: #E0E0E0; /* 悬停时有背景色反馈 */
                border-radius: 4px;
            }

            /* --- 关键：美化Qt绘制的箭头 --- */
            QToolButton#collapsibleTitle::arrow {
                image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%23555555' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'><polyline points='9 18 15 12 9 6'></polyline></svg>");
                width: 16px;
                height: 16px;
            }

            QToolButton#collapsibleTitle::arrow:open {
               image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%23333333' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'><polyline points='6 9 12 15 18 9'></polyline></svg>");
            }

            /* --- 内容区域的样式 --- */
            QFrame#collapsibleContent {
                background-color: #FDFDFD; /* 内容区使用白色背景 */
                border: 1px solid #D0D0D0;
                border-top: none; /* 顶部无边框，与标题栏无缝连接 */
                border-bottom-left-radius: 5px;
                border-bottom-right-radius: 5px;
            }
        """
    app.setStyleSheet(light_theme_stylesheet)

    main_window = MainWindow()
    main_window.show()

    QTimer.singleShot(100, main_window.start_monitoring)

    print("Starting Qt event loop...")
    sys.exit(app.exec())