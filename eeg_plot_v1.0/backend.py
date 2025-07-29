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
HIGHPASS_CUTOFF = 0.1
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
    #global zi_states_hp, zi_states_notch
    print("Starting filter worker thread...")

    fs = SAMPLES_PER_SECOND

    hp_cutoff = HIGHPASS_CUTOFF
    lp_cutoff = LOWPASS_CUTOFF
    notch_enabled = True

    # 根据默认值创建初始滤波器
    if hp_cutoff > 0:
        print(f"Initializing with BANDPASS filter: {hp_cutoff} - {lp_cutoff} Hz")
        b_filter, a_filter = butter(FILTER_ORDER, [hp_cutoff, lp_cutoff], btype='bandpass', analog=False, fs=fs)
    else:
        print(f"Initializing with LOWPASS filter: {lp_cutoff} Hz (Highpass is OFF)")
        b_filter, a_filter = butter(FILTER_ORDER, lp_cutoff, btype='lowpass', analog=False, fs=fs)
    zi_states_filter = [lfilter_zi(b_filter, a_filter) for _ in range(NUM_CHANNELS)]


    b_notch, a_notch = iirnotch(NOTCH_FREQ, NOTCH_QUALITY_FACTOR, fs=fs)
    zi_states_notch = [lfilter_zi(b_notch, a_notch) for _ in range(NUM_CHANNELS)]

    while True:

        try:
            command = command_queue.get_nowait()
            if command['type'] == 'UPDATE_SETTINGS':
                new_settings = command['data']
                print("Filter worker received new settings:", new_settings)

                # 重新设计滤波器
                hp_cutoff = new_settings['highpass_cutoff']
                lp_cutoff = new_settings['lowpass_cutoff']
                notch_enabled = new_settings['notch_filter_enabled']

                if hp_cutoff > 0:
                    print(f"Redesigning to BANDPASS filter: {hp_cutoff} - {lp_cutoff} Hz")
                    b_filter, a_filter = butter(FILTER_ORDER, [hp_cutoff, lp_cutoff], btype='bandpass', analog=False,fs=fs)
                else:
                    # 如果高通截止为0，则设计一个低通滤波器
                    print(f"Redesigning to LOWPASS filter: {lp_cutoff} Hz (Highpass is OFF)")
                    b_filter, a_filter = butter(FILTER_ORDER, lp_cutoff, btype='lowpass', analog=False, fs=fs)

                # 无论哪种情况，都重置滤波器状态
                zi_states_filter = [lfilter_zi(b_filter, a_filter) for _ in range(NUM_CHANNELS)]

                if notch_enabled:
                    b_notch, a_notch = iirnotch(NOTCH_FREQ, NOTCH_QUALITY_FACTOR, fs=fs)
                    zi_states_notch = [lfilter_zi(b_notch, a_notch) for _ in range(NUM_CHANNELS)]

        except queue.Empty:
            pass  # 队列为空是正常的

        try:
            raw_batch = raw_data_queue.get(timeout=0.1)
            if raw_batch is None:
                storage_queue.put(None)  # 传递结束信号
                # 也通知绘图队列结束
                for q in filtered_data_queues:
                    q.append(None)  # 发送哨兵值
                break

            final_filtered_batch = [[] for _ in range(NUM_CHANNELS)]
            for ch in range(NUM_CHANNELS):
                processed_chunk, zi_states_filter[ch] = lfilter(b_filter, a_filter, raw_batch[ch], zi=zi_states_filter[ch])

                if notch_enabled:
                    final_chunk, zi_states_notch[ch] = lfilter(b_notch, a_notch, processed_chunk, zi=zi_states_notch[ch])
                else:
                    final_chunk = processed_chunk   # 如果禁用陷波器，则直接跳过

                for value in final_chunk:
                    filtered_data_queues[ch].append(value)
                final_filtered_batch[ch].extend(final_chunk)

            storage_queue.put(final_filtered_batch)

        except queue.Empty:
            continue  # 数据队列为空也是正常的

    print("Filter worker thread finished.")


def data_storage_worker(storage_queue, recording_event):
    print("Starting data storage thread...")
    data_to_save = [[] for _ in range(NUM_CHANNELS)]

    events_to_save = []

    timestamp = None
    filename = None
    is_file_open = False

    recording_start_time = None
    while True:
        try:
            batch = storage_queue.get(timeout=0.1)

            if isinstance(batch, tuple) and batch[0] == 'MARKER':
                # 标记格式: ('MARKER', absolute_timestamp)
                if recording_event.is_set():  # 只在记录期间才保存标记
                    event_time = batch[1]
                    event_label = batch[2]
                    # 计算相对于记录开始的秒数
                    relative_time = event_time - recording_start_time
                    events_to_save.append([relative_time, event_label])
                    print(f"Marker logged at {relative_time:.3f} seconds from recording start.")
                else:
                    print("Marker ignored (not recording).")
                continue

            if recording_event.is_set():
                if not is_file_open:
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    filename = f"data/EEG_data_{timestamp}.mat"
                    print(f"Recording started. Saving to {filename}")
                    is_file_open = True
                    recording_start_time = time.time()

                for ch in range(NUM_CHANNELS):
                    data_to_save[ch].extend(batch[ch])

            if batch == 'STOP_RECORDING' or batch is None:
                if data_to_save and any(data_to_save):
                    print(f"Stopping recording. Finalizing save to {filename}...")
                    mat_data = {f'CH{i + 1}': np.array(data_to_save[i]) for i in range(NUM_CHANNELS)}
                    mat_data['fs'] = SAMPLES_PER_SECOND
                    mat_data['events'] = np.array(events_to_save, dtype=object)
                    sio.savemat(filename, mat_data)
                    print("File saved.")
                else:
                    print("Stop command received, but no data to save.")

                data_to_save = [[] for _ in range(NUM_CHANNELS)]
                events_to_save = []
                is_file_open = False
                recording_start_time = None

                if batch is None:  # 如果是程序退出信号
                    break

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




