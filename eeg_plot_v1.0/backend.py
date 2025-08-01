"""
Yuehao

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


# --- basic config ---
HOST = '0.0.0.0'
PORT = 8080
BATCH_HEADER = b'\xaa\xbb\xcc\xdd'
BATCH_HEADER_LEN = len(BATCH_HEADER)
FRAME_SIZE = 27
BATCH_SIZE = 10
PAYLOAD_SIZE = FRAME_SIZE * BATCH_SIZE
NUM_CHANNELS = 8
SAMPLES_PER_SECOND = 250
LSB_TO_UV = ((5.0 / 24.0 / 16777216.0) * 1000000.0)
SAVE_DURATION_S = 60
SAMPLES_PER_FILE = SAMPLES_PER_SECOND * SAVE_DURATION_S

# --- filter config ---
HIGHPASS_CUTOFF = 0.5
LOWPASS_CUTOFF = 100.0
FILTER_ORDER = 4
NOTCH_FREQ = 50.0
NOTCH_QUALITY_FACTOR = 30.0

# b_hp, a_hp = butter(FILTER_ORDER, HIGHPASS_CUTOFF, btype='high', analog=False, fs=SAMPLES_PER_SECOND)
# zi_states_hp = [lfilter_zi(b_hp, a_hp) for _ in range(NUM_CHANNELS)]
# b_notch, a_notch = iirnotch(NOTCH_FREQ, NOTCH_QUALITY_FACTOR, fs=SAMPLES_PER_SECOND)
# zi_states_notch = [lfilter_zi(b_notch, a_notch) for _ in range(NUM_CHANNELS)]


# --- data process ---
def parse_and_put_raw_data(payload_data, raw_data_queue):
    if len(payload_data) != PAYLOAD_SIZE: return
    parsed_batch = [[] for _ in range(NUM_CHANNELS)]
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
            parsed_batch[ch].append(voltage)
    raw_data_queue.put(parsed_batch)


# --- data recieve ---
def socket_data_receiver(raw_data_queue):
    print("Starting data receiver thread...")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # 允许地址重用
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
                        if header_pos == -1: break
                        if len(buffer) < header_pos + BATCH_HEADER_LEN + PAYLOAD_SIZE: break
                        payload_start = header_pos + BATCH_HEADER_LEN
                        payload_end = payload_start + PAYLOAD_SIZE
                        payload = buffer[payload_start:payload_end]
                        parse_and_put_raw_data(payload, raw_data_queue)
                        buffer = buffer[payload_end:]
    except Exception as e:
        print(f"An error occurred in receiver thread: {e}")
    finally:
        print("Data receiver thread finished.")
        raw_data_queue.put(None) # 发送结束信号


def filter_worker(raw_data_queue, filtered_data_queues, storage_queue, command_queue):
    """
    处理流程: 原始数据 -> [主滤波器(带通/低通)] -> [陷波滤波器] -> 输出队列
    """
    print("Starting filter worker thread...")

    # --- 初始参数 ---
    fs = SAMPLES_PER_SECOND
    hp_cutoff = HIGHPASS_CUTOFF
    lp_cutoff = LOWPASS_CUTOFF
    notch_enabled = True

    # --- 内部函数，用于设计和重置滤波器，避免代码重复 ---
    def design_and_reset_filters(hp, lp, notch_on):
        """根据给定的参数设计滤波器并返回系数和初始状态"""
        # 1. 设计主滤波器 (带通或低通)
        if hp > 0.01:
            print(f"[Filter] Designing BANDPASS filter: {hp:.1f} - {lp:.1f} Hz")
            b_main, a_main = butter(FILTER_ORDER, [hp, lp], btype='bandpass', analog=False, fs=fs)
        else:
            print(f"[Filter] Designing LOWPASS filter: {lp:.1f} Hz (Highpass is OFF)")
            b_main, a_main = butter(FILTER_ORDER, lp, btype='lowpass', analog=False, fs=fs)
        zi_main = [lfilter_zi(b_main, a_main) for _ in range(NUM_CHANNELS)]

        # 2. 设计陷波器
        b_n, a_n, zi_n = None, None, None
        if notch_on:
            print("[Filter] Designing NOTCH filter: 50 Hz")
            b_n, a_n = iirnotch(NOTCH_FREQ, NOTCH_QUALITY_FACTOR, fs=fs)
            zi_n = [lfilter_zi(b_n, a_n) for _ in range(NUM_CHANNELS)]

        return b_main, a_main, zi_main, b_n, a_n, zi_n

    # --- 初始化滤波器 ---
    b_filter, a_filter, zi_states_filter, \
        b_notch, a_notch, zi_states_notch = design_and_reset_filters(hp_cutoff, lp_cutoff, notch_enabled)

    while True:
        # --- 1. 检查来自User的命令，更新滤波器设置 ---
        try:
            command = command_queue.get_nowait()
            if command['type'] == 'UPDATE_SETTINGS':
                settings = command['data']
                print("[Filter] Received new settings:", settings)
                hp_cutoff, lp_cutoff, notch_enabled = settings['highpass_cutoff'], settings['lowpass_cutoff'], settings[
                    'notch_filter_enabled']

                # 使用辅助函数重新设计所有滤波器并重置状态
                b_filter, a_filter, zi_states_filter, \
                    b_notch, a_notch, zi_states_notch = design_and_reset_filters(hp_cutoff, lp_cutoff, notch_enabled)
        except queue.Empty:
            pass  # 队列为空是正常的，继续执行

        # --- 2. 从数据接收线程获取一批原始数据 ---
        try:
            raw_batch = raw_data_queue.get(timeout=0.1)
            if raw_batch is None:
                storage_queue.put(None)
                for q in filtered_data_queues:
                    q.append(None)
                break

            # --- 3. 对数据进行串联滤波处理 ---
            final_filtered_batch = [[] for _ in range(NUM_CHANNELS)]
            for ch in range(NUM_CHANNELS):

                # 1、: 对原始数据进行带通/低通滤波
                processed_chunk, zi_states_filter[ch] = lfilter(
                    b_filter, a_filter, raw_batch[ch], zi=zi_states_filter[ch]
                )

                # 2、: 对上一步的结果进行陷波滤波
                if notch_enabled:
                    final_chunk, zi_states_notch[ch] = lfilter(
                        b_notch, a_notch, processed_chunk, zi=zi_states_notch[ch]
                    )
                else:
                    # 如果禁用陷波器，则直接使用上一步的结果
                    final_chunk = processed_chunk

                # --- 流程结束 ---

                # 将最终处理好的数据分发到绘图队列
                for value in final_chunk:
                    filtered_data_queues[ch].append(value)

                # 将最终处理好的数据添加到准备存储的批次中
                final_filtered_batch[ch].extend(final_chunk)

            # 将整批处理好的数据放入存储队列
            storage_queue.put(final_filtered_batch)

        except queue.Empty:
            continue  # 数据队列暂时为空，继续循环等待

    print("Filter worker thread finished.")


def data_storage_worker(storage_queue, recording_event):
    print("Starting data storage thread...")
    # 默认通道名
    channel_names_for_saving = [f'CH{i + 1}' for i in range(NUM_CHANNELS)]
    data_to_save = [[] for _ in range(NUM_CHANNELS)]
    events_to_save = []

    timestamp = None
    filename = None
    is_file_open = False
    recording_start_time = None

    while True:
        try:
            batch = storage_queue.get(timeout=0.1)

            # --- 逻辑判断部分 ---
            is_marker = isinstance(batch, tuple) and batch[0] == 'MARKER'
            is_stop_command = isinstance(batch, tuple) and batch[0] == 'STOP_RECORDING'
            is_exit_command = batch is None
            is_data_batch = not (is_marker or is_stop_command or is_exit_command)

            # --- 处理标记 ---
            if is_marker:
                if recording_event.is_set() and recording_start_time is not None:
                    _, event_time, event_label = batch
                    relative_time = event_time - recording_start_time
                    events_to_save.append([relative_time, event_label])
                    print(f"Marker logged at {relative_time:.3f} seconds.")
                else:
                    print("Marker ignored (not recording).")
                continue  # 处理完标记后继续下一次循环

            # --- 处理数据 ---
            if recording_event.is_set() and is_data_batch:
                if not is_file_open:
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    filename = f"data/EEG_data_{timestamp}.mat"
                    print(f"Recording started. Saving to {filename}")
                    is_file_open = True
                    recording_start_time = time.time()

                for ch in range(NUM_CHANNELS):
                    data_to_save[ch].extend(batch[ch])

            # --- 处理停止或退出 ---
            if is_stop_command or is_exit_command:
                # *** 关键修正点：从停止命令中提取通道名 ***
                if is_stop_command:
                    channel_names_for_saving = batch[1]

                if data_to_save and any(data_to_save):
                    print(f"Finalizing save to {filename} with names: {channel_names_for_saving}")

                    # 使用正确的通道名保存
                    mat_data = {
                        channel_names_for_saving[i]: np.array(data_to_save[i])
                        for i in range(NUM_CHANNELS)
                    }
                    mat_data['fs'] = SAMPLES_PER_SECOND
                    mat_data['events'] = np.array(events_to_save, dtype=object)
                    mat_data['channel_order'] = np.array(channel_names_for_saving, dtype=object)  # 也保存通道顺序
                    sio.savemat(filename, mat_data)
                    print("File saved.")
                else:

                    print("Stop/Exit command received, but no data to save.")

                # 重置状态
                data_to_save = [[] for _ in range(NUM_CHANNELS)]
                events_to_save = []
                is_file_open = False
                recording_start_time = None
                channel_names_for_saving = [f'CH{i + 1}' for i in range(NUM_CHANNELS)]  # 恢复默认

                if is_exit_command:
                    break  # 如果是程序退出，则跳出循环

        except queue.Empty:
            continue
        except Exception as e:
            print(f"An error occurred in storage thread: {e}")
            break

    print("Data storage thread finished.")


def start_backend_threads(raw_q, filtered_qs, storage_q, recording_event, command_queue):
    """启动所有后台线程"""
    receiver_thread = threading.Thread(target=socket_data_receiver, args=(raw_q,), daemon=True)
    filter_thread = threading.Thread(target=filter_worker, args=(raw_q, filtered_qs, storage_q, command_queue), daemon=True)
    storage_thread = threading.Thread(target=data_storage_worker, args=(storage_q, recording_event), daemon=True)

    receiver_thread.start()
    filter_thread.start()
    storage_thread.start()

    return receiver_thread, filter_thread, storage_thread




