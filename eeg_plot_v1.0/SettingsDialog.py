"""
Yuehao

"""

# SettingsDialog.py

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit,
                             QCheckBox, QDialogButtonBox, QLabel, QGroupBox)
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtCore import Qt


class SettingsDialog(QDialog):
    def __init__(self, current_settings, parent=None):
        super().__init__(parent)

        self.setWindowTitle("参数配置")
        self.setMinimumWidth(350)
        self.setObjectName("SettingsDialog")

        # 保存传入的当前设置
        self.settings = current_settings.copy()

        # 1. 创建主布局和表单布局
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        #form_layout = QFormLayout()

        # --- 滤波器设置部分 ---
        filter_group = QGroupBox("滤波器设置")
        filter_group.setObjectName("SettingsGroup")
        form_layout_filter = QFormLayout(filter_group)
        form_layout_filter.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        form_layout_filter.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        # 高通滤波器截止频率
        self.hp_cutoff_input = QLineEdit(str(self.settings.get('highpass_cutoff', 0.5)))
        self.hp_cutoff_input.setValidator(QDoubleValidator(0, 10.0, 2, self))
        form_layout_filter.addRow("高通截止频率 (Hz):", self.hp_cutoff_input)

        # 50Hz陷波器开关
        self.notch_filter_checkbox = QCheckBox()
        self.notch_filter_checkbox.setChecked(self.settings.get('notch_filter_enabled', True))
        form_layout_filter.addRow("启用50Hz陷波器:", self.notch_filter_checkbox)

        # 低通滤波截止频率
        self.lp_cutoff_input = QLineEdit(str(self.settings.get('lowpass_cutoff', 100.0)))
        self.lp_cutoff_input.setValidator(QDoubleValidator(20.0, 120.0, 1, self))
        form_layout_filter.addRow("低通截止频率 (Hz):", self.lp_cutoff_input)

        # --- 绘图设置部分 ---
        plot_group = QGroupBox("绘图设置")
        plot_group.setObjectName("SettingsGroup")
        form_layout_plot = QFormLayout(plot_group)
        form_layout_plot.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        form_layout_plot.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        # 绘图时间窗口
        self.plot_duration_input = QLineEdit(str(self.settings.get('plot_duration_s', 5)))
        self.plot_duration_input.setValidator(QDoubleValidator(1.0, 20.0, 1, self))
        form_layout_plot.addRow("绘图时间窗口 (s):", self.plot_duration_input)

        # --- 按钮部分 ---
        # 使用标准的对话框按钮盒，它会自动处理“确定”和“取消”
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        # 将表单布局和按钮盒添加到主布局
        main_layout.addWidget(filter_group)
        main_layout.addWidget(plot_group)
        main_layout.addWidget(self.button_box)

    def get_settings(self):
        """当用户点击“确定”后，调用此方法来获取新的设置"""
        self.settings['highpass_cutoff'] = float(self.hp_cutoff_input.text())
        self.settings['lowpass_cutoff'] = float(self.lp_cutoff_input.text())
        self.settings['notch_filter_enabled'] = self.notch_filter_checkbox.isChecked()
        self.settings['plot_duration_s'] = float(self.plot_duration_input.text())
        return self.settings