# DroidMic PC Server

This is the PC server component of **DroidMic**, a wireless microphone solution that streams audio from your Android phone to your PC over Wi-Fi.

The Python server runs on your PC, receives raw PCM audio via WebSocket, and pipes it into a virtual microphone device so that any desktop application (Discord, Zoom, OBS, etc.) can use your phone as a standard microphone input.

---

## Prerequisites

- **Python 3.10+**
- Both the PC and the Android phone must be on the **same Wi-Fi network**.

---

## Setup & Installation

### Option 1: Linux (PulseAudio / PipeWire)

On Linux, the server uses the `module-null-sink` feature of PulseAudio/PipeWire to create a native virtual microphone.

1. **Install system dependencies:**
   You will need the PortAudio development headers to compile `PyAudio`.
   ```bash
   # Debian/Ubuntu
   sudo apt install python3-pip portaudio19-dev

   # Arch Linux
   sudo pacman -S python-pip portaudio

   # Fedora
   sudo dnf install python3-pip portaudio-devel
   ```

2. **Install Python requirements:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Create the virtual microphone:**
   Run the included shell script to create the PulseAudio loopback devices.
   ```bash
   chmod +x setup_virtual_mic.sh
   ./setup_virtual_mic.sh
   ```

### Option 2: Windows

On Windows, the server relies on a third-party virtual audio cable driver to route the audio.

1. **Install Virtual Audio Cable:**
   Download and install [VB-Cable](https://vb-audio.com/Cable/) (free). Once installed, it will add a "CABLE Input" and "CABLE Output" to your system's sound devices.

2. **Install Python requirements:**
   ```powershell
   pip install -r requirements.txt
   ```

---

## Usage

1. **Start the server:**
   ```bash
   python server.py
   ```
   
   The server will bind to `0.0.0.0` and wait for incoming connections on port `8765`:
   ```text
   DroidMic Server
   Listening on ws://0.0.0.0:8765
   Waiting for Android client to connect...
   ```

2. **Find your local IP address:**
   You'll need this IP address to enter into the Android app.
   - **Linux:** Run `hostname -I | awk '{print $1}'`
   - **Windows:** Run `ipconfig` and look for the IPv4 Address.

3. **Connect the App:**
   Open the DroidMic app on your Android phone, enter the IP address, and tap "Connect & Stream".

4. **Select the Microphone in your Apps:**
   - **Linux:** In Discord, Zoom, or your system settings, select **"DroidMic Microphone"** as the input device.
   - **Windows:** Select **"CABLE Output (VB-Audio Virtual Cable)"** as your input device.

---

## File Structure

- `server.py`: The main asyncio WebSocket server.
- `config.py`: Shared constants for the audio format (44100Hz, 16-bit PCM).
- `audio_sink.py`: The abstract base class for cross-platform audio routing.
- `audio_sink_linux.py`: Linux implementation using PyAudio and PulseAudio.
- `audio_sink_windows.py`: Windows implementation using PyAudio and VB-Cable.
- `setup_virtual_mic.sh`: Helper script to configure PulseAudio loopbacks on Linux.

---

## Security Notice

The server currently uses unencrypted WebSocket connections (`ws://`). It is designed to be used only on trusted local area networks.
