"""
Yuehao
(WiFi Version - Refactored Backend)
"""

import queue
import socket
import struct
import numpy as np
from collections import deque
import threading
from scipy.signal import butter, iirnotch, lfilter_zi, lfilter
from queue import Queue
import time
import scipy.io as sio
import os

# --- 1. 配置区 ---
# WiFi/Socket 配置
HOST = '0.0.0.0'
PORT = 8080

# 数据帧和批处理配置
FRAME_SIZE = 27
BATCH_SIZE = 10
BATCH_HEADER = b'\xaa\xbb\xcc\xdd'
BATCH_HEADER_LEN = len(BATCH_HEADER)
PAYLOAD_SIZE = FRAME_SIZE * BATCH_SIZE
NUM_CHANNELS = 8
SAMPLES_PER_SECOND = 250
V_REF = 5.0
GAIN = 24.0
LSB_TO_UV = (V_REF / GAIN / (2**23 - 1)) * 1000000.0

# 滤波器配置
HIGHPASS_CUTOFF = 0.5
LOWPASS_CUTOFF = 100.0
FILTER_ORDER = 4
NOTCH_FREQ = 50.0
NOTCH_QUALITY_FACTOR = 30.0

# --- 2. 数据解析 ---
def parse_and_put_raw_data(payload_data, raw_data_queue):
    """
    解析一个数据负载 (270字节) 并放入原始数据队列
    (这个函数可以从两个版本中任选其一，如果数据格式相同)
    """
    if len(payload_data) != PAYLOAD_SIZE:
        print(f"[Parser] Warning: Received payload of incorrect size {len(payload_data)}. Expected {PAYLOAD_SIZE}.")
        return

    parsed_batch = [[] for _ in range(NUM_CHANNELS)]
    for i in range(BATCH_SIZE):
        frame_start = i * FRAME_SIZE
        frame_data = payload_data[frame_start : frame_start + FRAME_SIZE]

        for ch in range(NUM_CHANNELS):
            ch_start = 3 + ch * 3
            ch_bytes = frame_data[ch_start : ch_start + 3]
            # 使用更健壮的符号位扩展方式
            raw_value = int.from_bytes(ch_bytes, byteorder='big', signed=True)
            voltage = raw_value * LSB_TO_UV
            parsed_batch[ch].append(voltage)

    raw_data_queue.put(parsed_batch)

# --- 3. 数据接收 (使用WiFi/Socket版本) ---
def socket_data_receiver(raw_data_queue: Queue):
    print("Starting data receiver thread...")
    while True: # 添加重连循环
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((HOST, PORT))
                s.listen()
                print(f"Server listening on {HOST}:{PORT}")
                conn, addr = s.accept()
                with conn:
                    print(f"Connected by {addr}")
                    buffer = b''
                    while True:
                        data = conn.recv(4096)
                        if not data:
                            print("Client disconnected.")
                            break
                        buffer += data
                        while True:
                            header_pos = buffer.find(BATCH_HEADER)
                            if header_pos == -1:
                                # 如果缓冲区过大但找不到头，清空一部分以防内存溢出
                                if len(buffer) > PAYLOAD_SIZE * 2:
                                    buffer = buffer[-PAYLOAD_SIZE:]
                                break

                            required_len = header_pos + BATCH_HEADER_LEN + PAYLOAD_SIZE
                            if len(buffer) < required_len:
                                break

                            payload_start = header_pos + BATCH_HEADER_LEN
                            payload_end = payload_start + PAYLOAD_SIZE
                            payload = buffer[payload_start:payload_end]
                            parse_and_put_raw_data(payload, raw_data_queue)
                            buffer = buffer[payload_end:]
        except Exception as e:
            print(f"An error occurred in receiver thread: {e}. Reconnecting in 5 seconds...")
            time.sleep(5)
        finally:
            print("Restarting socket server...")

# --- 4. 滤波器和存储线程 (使用最新的蓝牙版本逻辑) ---
def filter_worker(raw_data_queue, filtered_data_queues, storage_queue, command_queue):
    """
    处理流程: 原始数据 -> [主滤波器] -> [陷波滤波器] -> (数据, 采样率) -> 输出队列
    """
    print("Starting filter worker thread...")
    local_filtered_queues = filtered_data_queues
    fs = SAMPLES_PER_SECOND
    hp_cutoff = HIGHPASS_CUTOFF
    lp_cutoff = LOWPASS_CUTOFF
    notch_enabled = True

    def design_and_reset_filters(current_fs, hp, lp, notch_on):
        print(f"[Filter] Designing filters for {current_fs} SPS...")
        if hp > 0.01:
            b_main, a_main = butter(FILTER_ORDER, [hp, lp], btype='bandpass', analog=False, fs=current_fs)
        else:
            b_main, a_main = butter(FILTER_ORDER, lp, btype='lowpass', analog=False, fs=current_fs)
        zi_main = [lfilter_zi(b_main, a_main) for _ in range(NUM_CHANNELS)]
        b_n, a_n, zi_n = None, None, None
        if notch_on:
            b_n, a_n = iirnotch(NOTCH_FREQ, NOTCH_QUALITY_FACTOR, fs=current_fs)
            zi_n = [lfilter_zi(b_n, a_n) for _ in range(NUM_CHANNELS)]
        return b_main, a_main, zi_main, b_n, a_n, zi_n

    b_filter, a_filter, zi_states_filter, \
        b_notch, a_notch, zi_states_notch = design_and_reset_filters(fs, hp_cutoff, lp_cutoff, notch_enabled)

    while True:
        try:
            command = command_queue.get_nowait()
            if command['type'] == 'UPDATE_SETTINGS':
                settings = command['data']
                print("[Filter] Received new settings:", settings)
                if 'new_queues' in settings:
                    print("[Filter] Switching to new data queues provided by UI.")
                    local_filtered_queues = settings['new_queues']
                fs = settings.get('samples_per_second', fs) # 允许单独更新滤波器而不改变采样率
                hp_cutoff = settings['highpass_cutoff']
                lp_cutoff = settings['lowpass_cutoff']
                notch_enabled = settings['notch_filter_enabled']
                b_filter, a_filter, zi_states_filter, \
                    b_notch, a_notch, zi_states_notch = design_and_reset_filters(fs, hp_cutoff, lp_cutoff, notch_enabled)
        except queue.Empty:
            pass

        try:
            raw_batch = raw_data_queue.get(timeout=1.0)
            if raw_batch is None:
                storage_queue.put(None)
                break
            final_filtered_batch = [[] for _ in range(NUM_CHANNELS)]
            for ch in range(NUM_CHANNELS):
                processed_chunk, zi_states_filter[ch] = lfilter(b_filter, a_filter, raw_batch[ch], zi=zi_states_filter[ch])
                if notch_enabled:
                    final_chunk, zi_states_notch[ch] = lfilter(b_notch, a_notch, processed_chunk, zi=zi_states_notch[ch])
                else:
                    final_chunk = processed_chunk
                for value in final_chunk:
                    local_filtered_queues[ch].append(value)
                final_filtered_batch[ch].extend(final_chunk)
            storage_queue.put(('DATA', final_filtered_batch, fs))
        except queue.Empty:
            continue
    print("Filter worker thread finished.")


def data_storage_worker(storage_queue, recording_event):
    """
    数据存储线程 (修复版)
    """
    print("Starting data storage thread...")
    channel_names_for_saving = [f'CH{i + 1}' for i in range(NUM_CHANNELS)]
    data_to_save = [[] for _ in range(NUM_CHANNELS)]
    events_to_save = []
    filename = None
    is_file_open = False
    recording_start_time = None
    current_fs_for_saving = SAMPLES_PER_SECOND

    while True:
        try:
            item = storage_queue.get(timeout=0.1)

            # --- 简化消息处理逻辑 ---
            command = item[0] if isinstance(item, tuple) else None

            if command == 'DATA':
                _, batch_data, fs = item
                if recording_event.is_set():
                    if not is_file_open:
                        timestamp = time.strftime("%Y%m%d_%H%M%S")
                        filename = f"data/EEG_data_{timestamp}.mat"
                        print(f"Recording started. Saving to {filename}")
                        is_file_open = True
                        # 如果是第一个数据包，就用当前时间作为记录开始时间
                        if recording_start_time is None:
                            recording_start_time = time.time()

                    for ch in range(NUM_CHANNELS):
                        data_to_save[ch].extend(batch_data[ch])
                    current_fs_for_saving = fs

            elif command == 'MARKER':
                if recording_event.is_set():
                    # --- 关键修复 ---
                    # 如果这是记录开始后的第一个事件（无论是数据还是标记）
                    # 就用这个标记的绝对时间作为记录的开始时间
                    if recording_start_time is None:
                        recording_start_time = item[1]  # item[1] is event_time

                    _, event_time, event_label = item
                    relative_time = event_time - recording_start_time
                    events_to_save.append([relative_time, event_label])
                    print(f"Marker logged: '{event_label}' at {relative_time:.3f} seconds.")
                else:
                    print("Marker ignored (not recording).")

            elif command == 'STOP_RECORDING' or item is None:  # Stop or Exit
                if is_file_open and any(data_to_save):
                    if command == 'STOP_RECORDING':
                        channel_names_for_saving = item[1]

                    print(
                        f"Finalizing save to {filename} with names: {channel_names_for_saving} and FS: {current_fs_for_saving}")

                    # 检查 data_to_save 的长度是否与 channel_names_for_saving 匹配
                    num_channels_to_save = len(channel_names_for_saving)
                    mat_data = {
                        channel_names_for_saving[i]: np.array(data_to_save[i])
                        for i in range(num_channels_to_save) if i < len(data_to_save) and data_to_save[i]
                    }
                    mat_data['fs'] = current_fs_for_saving
                    mat_data['events'] = np.array(events_to_save, dtype=object)
                    mat_data['channel_order'] = np.array(channel_names_for_saving, dtype=object)

                    # 确保 'data' 目录存在
                    if not os.path.exists('data'):
                        os.makedirs('data')
                    sio.savemat(filename, mat_data)
                    print("File saved.")
                else:
                    print("Stop/Exit command received, but no data to save.")

                # Reset for next recording
                data_to_save = [[] for _ in range(NUM_CHANNELS)]
                events_to_save = []
                is_file_open = False
                recording_start_time = None
                channel_names_for_saving = [f'CH{i + 1}' for i in range(NUM_CHANNELS)]

                if item is None:  # Exit command
                    break

        except queue.Empty:
            continue
        except Exception as e:
            print(f"An error occurred in storage thread: {e}")
            import traceback
            traceback.print_exc()
            break

    print("Data storage thread finished.")

# --- 5. 启动函数 (修改版) ---
def start_backend_threads(raw_q, filtered_qs, storage_q, recording_event, cmd_q_filter):
    """启动所有后台线程 (WiFi 版本)"""
    receiver_thread = threading.Thread(target=socket_data_receiver, args=(raw_q,), daemon=True)
    filter_thread = threading.Thread(target=filter_worker, args=(raw_q, filtered_qs, storage_q, cmd_q_filter), daemon=True)
    storage_thread = threading.Thread(target=data_storage_worker, args=(storage_q, recording_event), daemon=True)

    receiver_thread.start()
    filter_thread.start()
    storage_thread.start()

    return receiver_thread, filter_thread, storage_thread