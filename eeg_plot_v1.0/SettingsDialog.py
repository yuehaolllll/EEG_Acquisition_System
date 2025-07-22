"""
Yuehao

"""

# SettingsDialog.py

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit,
                             QCheckBox, QDialogButtonBox, QLabel)
from PyQt6.QtGui import QDoubleValidator


class SettingsDialog(QDialog):
    def __init__(self, current_settings, parent=None):
        super().__init__(parent)

        self.setWindowTitle("参数配置")
        self.setMinimumWidth(350)

        # 保存传入的当前设置
        self.settings = current_settings.copy()

        # 1. 创建主布局和表单布局
        main_layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        # --- 滤波器设置部分 ---
        filter_label = QLabel("滤波器设置")
        font = filter_label.font()
        font.setBold(True)
        filter_label.setFont(font)
        form_layout.addRow(filter_label)

        # 高通滤波器截止频率
        self.hp_cutoff_input = QLineEdit(str(self.settings.get('highpass_cutoff', 0.5)))
        # 使用验证器，只允许输入浮点数
        self.hp_cutoff_input.setValidator(QDoubleValidator(0.1, 10.0, 2, self))
        form_layout.addRow("高通截止频率 (Hz):", self.hp_cutoff_input)

        # 50Hz陷波器开关
        self.notch_filter_checkbox = QCheckBox()
        self.notch_filter_checkbox.setChecked(self.settings.get('notch_filter_enabled', True))
        form_layout.addRow("启用50Hz陷波器:", self.notch_filter_checkbox)

        # 低通滤波截止频率
        self.lp_cutoff_input = QLineEdit(str(self.settings.get('lowpass_cutoff', 100.0)))
        self.lp_cutoff_input.setValidator(QDoubleValidator(20.0, 120.0, 1, self))  # 限制在20-120Hz之间
        form_layout.addRow("低通截止频率 (Hz):", self.lp_cutoff_input)

        # --- 绘图设置部分 ---
        plot_label = QLabel("绘图设置")
        font = plot_label.font()
        font.setBold(True)
        plot_label.setFont(font)
        form_layout.addRow(plot_label)

        # 绘图时间窗口
        self.plot_duration_input = QLineEdit(str(self.settings.get('plot_duration_s', 5)))
        self.plot_duration_input.setValidator(QDoubleValidator(1.0, 20.0, 1, self))
        form_layout.addRow("绘图时间窗口 (s):", self.plot_duration_input)

        # --- 按钮部分 ---
        # 使用标准的对话框按钮盒，它会自动处理“确定”和“取消”
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)  # 连接“确定”按钮到accept槽
        self.button_box.rejected.connect(self.reject)  # 连接“取消”按钮到reject槽

        # 将表单布局和按钮盒添加到主布局
        main_layout.addLayout(form_layout)
        main_layout.addWidget(self.button_box)

    def get_settings(self):
        """当用户点击“确定”后，调用此方法来获取新的设置"""
        self.settings['highpass_cutoff'] = float(self.hp_cutoff_input.text())
        self.settings['lowpass_cutoff'] = float(self.lp_cutoff_input.text())
        self.settings['notch_filter_enabled'] = self.notch_filter_checkbox.isChecked()
        self.settings['plot_duration_s'] = float(self.plot_duration_input.text())
        return self.settings