import sounddevice as sd
import numpy as np
import threading
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
import time
import os
import soundfile as sf
from pynput import keyboard

console = Console()
SAMPLERATE = 44100
CHANNELS = 2
VIRTUAL_OUTPUT_NAME = "Virtual Input"  # virtual mic output
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


SOUNDS = {
    "1": "sounds/sound.wav",
    # add more here
}


loaded_sounds = {}
for key, rel_path in SOUNDS.items():
    abs_path = os.path.join(SCRIPT_DIR, rel_path)
    if not os.path.exists(abs_path):
        console.print(f"[yellow][WARNING][/yellow] Sound file for key {key} not found: {abs_path}")
        continue
    try:
        data, sr = sf.read(abs_path, dtype='float32')
        if data.ndim == 1 and CHANNELS == 2:
            data = np.column_stack([data, data])
        if sr != SAMPLERATE:
            duration = data.shape[0] / sr
            new_length = int(duration * SAMPLERATE)
            data_new = np.zeros((new_length, CHANNELS), dtype='float32')
            for ch in range(CHANNELS):
                data_new[:, ch] = np.interp(
                    np.linspace(0, len(data), new_length, endpoint=False),
                    np.arange(len(data)),
                    data[:, ch] if CHANNELS == 2 else data
                )
            data = data_new
        loaded_sounds[key] = data
        console.print(f"[green][INFO][/green] Loaded '{abs_path}' for key {key}")
    except Exception as e:
        console.print(f"[red][ERROR][/red] Failed to load '{abs_path}': {e}")

play_queue = []
mic_enabled = True  

# Audio callback
def audio_callback(outdata, frames, time_info, status):
    global mic_enabled
    outdata[:] = 0
    if not mic_enabled:
        return  
    remove_list = []
    for idx, sound in enumerate(play_queue):
        length = min(len(sound['data']) - sound['pos'], frames)
        outdata[:length] += sound['data'][sound['pos']:sound['pos'] + length]
        sound['pos'] += length
        if sound['pos'] >= len(sound['data']):
            remove_list.append(idx)
    for idx in reversed(remove_list):
        play_queue.pop(idx)
    np.clip(outdata, -1, 1, out=outdata)
    # Convert stereo to mono if needed (first channel only)
    outdata[:, 0] = outdata.mean(axis=1)
    outdata[:, 1] = outdata[:, 0]
    # Optional volume adjustment
    outdata[:] *= 0.5

# Play sound
def play_sound(key):
    if key in loaded_sounds:
        play_queue.append({'data': loaded_sounds[key], 'pos': 0})

# UI
def render_ui():
    table = Table(title="Virtual Mic Soundboard", expand=True)
    table.add_column("Key", justify="center")
    table.add_column("Sound", justify="center")
    table.add_column("Status", justify="center")
    for key, file in SOUNDS.items():
        status = "[green]Playing[/green]" if any(s for s in play_queue if s['data'] is loaded_sounds[key]) else "[red]Idle[/red]"
        table.add_row(key, os.path.basename(file), status)
    mic_status = "[bold green]ON[/bold green]" if mic_enabled else "[bold red]MUTED[/bold red]"
    instructions = f"[bold]Press 1,2,3... to play sounds. F1: Mic ON, F2: Mic OFF, ESC: Quit. Mic: {mic_status}[/bold]"
    return Panel(table, title=instructions, border_style="blue")

# Find VB-Cable device
def find_output_device(name_contains):
    for i, dev in enumerate(sd.query_devices()):
        if dev['max_output_channels'] > 0 and name_contains.lower() in dev['name'].lower():
            return i
    return None

device_index = find_output_device(VIRTUAL_OUTPUT_NAME)
if device_index is None:
    console.print(f"[yellow][WARNING][/yellow] Virtual audio cable not found. Using default output.")
    device_index = None

# Hotkey listener
def hotkey_listener():
    global mic_enabled
    def on_press(key):
        global mic_enabled
        try:
            k = key.char
            if k in loaded_sounds:
                play_sound(k)
        except AttributeError:
            if key == keyboard.Key.f1:
                mic_enabled = True
            elif key == keyboard.Key.f2:
                mic_enabled = False
            elif key == keyboard.Key.esc:
                return False
    listener = keyboard.Listener(on_press=on_press)
    listener.start()
    listener.join()

# Main
try:
    with sd.OutputStream(
        samplerate=SAMPLERATE,
        channels=CHANNELS,
        callback=audio_callback,
        device=device_index,
        blocksize=512
    ):
        with Live(render_ui(), refresh_per_second=10, console=console) as live:
            listener_thread = threading.Thread(target=hotkey_listener, daemon=True)
            listener_thread.start()
            while listener_thread.is_alive():
                live.update(render_ui())
                time.sleep(0.05)
except Exception as e:
    console.print(f"[red][ERROR][/red] Failed to open audio device: {e}")

console.print("[bold green]Exited Soundboard[/bold green]")
input("Press Enter to exit...")
