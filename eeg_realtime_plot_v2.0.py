"""
Yuehao

a realtime plotting system for EEG

"""
import matplotlib

matplotlib.use('TkAgg')

import socket
import struct
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from collections import deque
import threading
import scipy.io as sio
from scipy.signal import butter, iirnotch, lfilter_zi, lfilter
from queue import Queue
import time
import random



# --- 配置  ---
HOST = '0.0.0.0'    # 监听
PORT = 8080         # 端口号

BATCH_HEADER = b'\xaa\xbb\xcc\xdd'         # 每组数据的开头
BATCH_HEADER_LEN = len(BATCH_HEADER)
FRAME_SIZE = 27                            # 每帧27bit
BATCH_SIZE = 10                            # 每次接收10组
PAYLOAD_SIZE = FRAME_SIZE * BATCH_SIZE     # 每个数据包的总大小
NUM_CHANNELS = 8                           # 通道数
SAMPLES_PER_SECOND = 250                   # 采样率

PLOT_DURATION_S = 5                                            # 绘制时间
PLOT_UPDATE_INTERVAL_MS = 20                                   # 刷新率
PLOT_SAMPLES = int(SAMPLES_PER_SECOND * PLOT_DURATION_S)       # 绘制的样本点数

LSB_TO_UV = ((5.0 / 24.0 / 16777216.0) * 1000000.0)         # 电压转换公式
NFFT = PLOT_SAMPLES
MAX_FREQ_TO_SHOW = 100

SAVE_DURATION_S = 60                                        # 数据保存的时间（每60s保存一个）
SAMPLES_PER_FILE = SAMPLES_PER_SECOND * SAVE_DURATION_S

FILTER_WINDOW_SIZE = 5

# 高通滤波器配置
HIGHPASS_CUTOFF = 0.5  # 高通滤波截止频率 (Hz)，0.5Hz是常用值
FILTER_ORDER = 4       # 滤波器阶数

# 50Hz陷波器配置
NOTCH_FREQ = 50.0  # 要滤除的工频频率
NOTCH_QUALITY_FACTOR = 30.0 # 品质因数Q

# --- 全局数据存储 ---
raw_data_queue = Queue() # 原始数据队列，用于线程间通信
filtered_data_queues = [deque(np.zeros(PLOT_SAMPLES), maxlen=PLOT_SAMPLES) for _ in range(NUM_CHANNELS)] # 滤波后数据，用于绘图
storage_queue = Queue() # 滤波后数据，用于存储

# --- 设计滤波器 ---
# 1. 高通滤波器 b, a 是滤波器的分子和分母系数
b_hp, a_hp = butter(FILTER_ORDER, HIGHPASS_CUTOFF, btype='high', analog=False, fs=SAMPLES_PER_SECOND)
# 为每个通道初始化滤波器状态 zi
zi_states_hp = [lfilter_zi(b_hp, a_hp) for _ in range(NUM_CHANNELS)]

# 2. 设计50Hz陷波器
b_notch, a_notch = iirnotch(NOTCH_FREQ, NOTCH_QUALITY_FACTOR, fs=SAMPLES_PER_SECOND)
zi_states_notch = [lfilter_zi(b_notch, a_notch) for _ in range(NUM_CHANNELS)] # 陷波器状态


# --- 网络接收、数据解析、数据存储线程 ---
def parse_and_put_raw_data(payload_data):

    if len(payload_data) != PAYLOAD_SIZE: return
    parsed_batch = [[] for _ in range(NUM_CHANNELS)]
    parsed_batch_filtered = [[] for _ in range(NUM_CHANNELS)]
    for i in range(BATCH_SIZE):
        frame_start, frame_end = i * FRAME_SIZE, (i + 1) * FRAME_SIZE
        frame_data = payload_data[frame_start:frame_end]
        if len(frame_data) != FRAME_SIZE: continue
        for ch in range(NUM_CHANNELS):
            ch_start, ch_end = 3 + ch * 3, 3 + (ch + 1) * 3
            ch_bytes = frame_data[ch_start:ch_end]
            if ch_bytes[0] & 0x80:
                raw_value = struct.unpack('>i', b'\xff' + ch_bytes)[0]
            else:
                raw_value = struct.unpack('>i', b'\x00' + ch_bytes)[0]
            voltage = raw_value * LSB_TO_UV
            # voltage += 10.0
            # if ch == 0 and random.random() < 0.01:  # 大约1%的几率
            #     print("Injecting artifact into CH1!")
            #     voltage += 500  # 增加一个+500uV的突变
            parsed_batch[ch].append(voltage)
    #         raw_data_queues[ch].append(voltage)
    #         window = list(raw_data_queues[ch])[-FILTER_WINDOW_SIZE:]
    #         filtered_voltage = np.mean(window)
    #         filtered_data_queues[ch].append(filtered_voltage)
    #         parsed_batch_filtered[ch].append(filtered_voltage)
    #         # plotting_queues[ch].append(voltage)
    #         # parsed_batch[ch].append(voltage)
    # if parsed_batch_filtered[0]:
    #     storage_queue.put(parsed_batch_filtered)
    raw_data_queue.put(parsed_batch)


def socket_data_receiver():

    print("Starting data receiver thread...")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT));
        s.listen();
        print(f"Server listening on {HOST}:{PORT}")
        conn, addr = s.accept()
        with conn:
            print(f"Connected by {addr}");
            buffer = b''
            while True:
                try:
                    data = conn.recv(4096)
                    if not data: print("Client disconnected."); break
                    buffer += data
                    while True:
                        header_pos = buffer.find(BATCH_HEADER)
                        if header_pos == -1: break
                        if len(buffer) < header_pos + BATCH_HEADER_LEN + PAYLOAD_SIZE: break
                        payload_start = header_pos + BATCH_HEADER_LEN
                        payload_end = payload_start + PAYLOAD_SIZE
                        payload = buffer[payload_start:payload_end]
                        # parse_and_update_data(payload)
                        parse_and_put_raw_data(payload)
                        buffer = buffer[payload_end:]
                except Exception as e:
                    print(f"An error occurred in receiver thread: {e}");
                    break
    print("Data receiver thread finished.")
    # storage_queue.put(None)
    raw_data_queue.put(None)


def filter_worker():
    """该线程从raw_data_queue获取数据，进行串联滤波，然后分发"""
    global zi_states_hp, zi_states_notch  # 声明要修改全局状态
    print("Starting filter worker thread...")
    while True:
        raw_batch = raw_data_queue.get()
        if raw_batch is None:
            storage_queue.put(None)
            break

        final_filtered_batch = [[] for _ in range(NUM_CHANNELS)]
        for ch in range(NUM_CHANNELS):
            # 1. 第一级：高通滤波
            hp_filtered_chunk, zi_states_hp[ch] = lfilter(b_hp, a_hp, raw_batch[ch], zi=zi_states_hp[ch])

            # 2. 第二级：50Hz陷波滤波
            notch_filtered_chunk, zi_states_notch[ch] = lfilter(b_notch, a_notch, hp_filtered_chunk,
                                                                zi=zi_states_notch[ch])

            # 更新用于绘图的deque
            for value in notch_filtered_chunk:
                filtered_data_queues[ch].append(value)

            # 将最终滤波后的批次数据放入存储队列
            final_filtered_batch[ch].extend(notch_filtered_chunk)

        storage_queue.put(final_filtered_batch)
    print("Filter worker thread finished.")

def data_storage_worker():

    import scipy.io as sio
    import time
    print("Starting data storage thread...")
    data_to_save = [[] for _ in range(NUM_CHANNELS)]
    while True:
        try:
            batch = storage_queue.get()
            if batch is None:
                if data_to_save[0]:
                    mat_data = {f'CH{i + 1}': np.array(data_to_save[i]) for i in range(NUM_CHANNELS)}
                    mat_data['fs'] = SAMPLES_PER_SECOND
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    filename = f"data/EEG_data_final_{timestamp}.mat"
                    sio.savemat(filename, mat_data)
                break
            for ch in range(NUM_CHANNELS): data_to_save[ch].extend(batch[ch])
            if len(data_to_save[0]) >= SAMPLES_PER_FILE:
                mat_data_to_save = {f'CH{i + 1}': np.array(data_to_save[i][:SAMPLES_PER_FILE]) for i in
                                    range(NUM_CHANNELS)}
                mat_data_to_save['fs'] = SAMPLES_PER_SECOND
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"data/EEG_data_{timestamp}.mat"
                sio.savemat(filename, mat_data_to_save)
                data_to_save = [ch_data[SAMPLES_PER_FILE:] for ch_data in data_to_save]
        except Exception as e:
            print(f"An error occurred in storage thread: {e}")
    print("Data storage thread finished.")


# --- Matplotlib 绘图设置 ---
fig, axes = plt.subplots(NUM_CHANNELS, 2, figsize=(15, 12), gridspec_kw={'width_ratios': [3, 1]})
time_axis = np.linspace(-PLOT_DURATION_S, 0, PLOT_SAMPLES)
freq_axis = np.fft.rfftfreq(NFFT, d=1.0 / SAMPLES_PER_SECOND)
lines_time = [axes[i, 0].plot(time_axis, np.zeros(PLOT_SAMPLES))[0] for i in range(NUM_CHANNELS)]
lines_freq = [axes[i, 1].plot(freq_axis, np.zeros(len(freq_axis)))[0] for i in range(NUM_CHANNELS)]


def setup_plot():

    fig.suptitle('Real-time EEG Signal & Spectrum Monitor', fontsize=16)
    for i in range(NUM_CHANNELS):
        axes[i, 0].set_ylabel(f'CH {i + 1} (uV)');
        axes[i, 0].grid(True);
        axes[i, 0].set_xlim(-PLOT_DURATION_S, 0)
        axes[i, 1].set_xlim(0, MAX_FREQ_TO_SHOW);
        axes[i, 1].grid(True);
        axes[i, 1].yaxis.tick_right()
    axes[-1, 0].set_xlabel('Time (s)');
    axes[-1, 1].set_xlabel('Frequency (Hz)')
    plt.tight_layout(rect=[0, 0, 0.95, 0.96])


def update_plot(frame):
    """
    动画更新函数
    """
    # 这个函数现在只负责更新数据和Y轴范围，不返回任何东西
    for i in range(NUM_CHANNELS):
        current_data = np.array(filtered_data_queues[i])
        ax_time, ax_freq = axes[i, 0], axes[i, 1]
        line_time, line_freq = lines_time[i], lines_freq[i]

        # 1. 更新时域图
        line_time.set_ydata(current_data)
        data_min, data_max = np.min(current_data), np.max(current_data)
        padding = (data_max - data_min) * 0.1 if not np.isclose(data_min, data_max) else 1.0
        ax_time.set_ylim(data_min - padding, data_max + padding)

        # 2. 更新频域图
        if len(current_data) >= NFFT:
            fft_data = np.fft.rfft(current_data - np.mean(current_data), n=NFFT)
            freq_magnitude = (2.0 / NFFT) * np.abs(fft_data)
            line_freq.set_ydata(freq_magnitude)

            freq_mask = freq_axis <= MAX_FREQ_TO_SHOW
            if np.any(freq_mask):
                freq_max_val = np.max(freq_magnitude[freq_mask])
                ax_freq.set_ylim(0, freq_max_val * 1.1 if freq_max_val > 0.1 else 0.1)

    return lines_time + lines_freq


if __name__ == '__main__':
    receiver_thread = threading.Thread(target=socket_data_receiver, daemon=True)
    filter_thread = threading.Thread(target=filter_worker, daemon=True)
    storage_thread = threading.Thread(target=data_storage_worker, daemon=True)

    receiver_thread.start()
    filter_thread.start()
    storage_thread.start()

    # 在启动绘图前，等待一小段时间，让后台线程有机会先接收一些数据
    print("Waiting for initial data...")
    time.sleep(1)  # 等待1秒

    setup_plot()

    ani = animation.FuncAnimation(fig, update_plot, blit=False,
                                  interval=PLOT_UPDATE_INTERVAL_MS, repeat=False)

    plt.show()

    print("Plotting window closed. Exiting application.")