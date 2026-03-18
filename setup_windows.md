### DJI FPV Goggles V2 USB Capture – Windows Setup

This guide walks you through setting up Windows to use `dji_capture.py` with DJI FPV Goggles V2 over USB.

The high‑level path is:
- **Install WinUSB** driver for the goggles’ **bulk transfer interface (interface 3)** using Zadig.
- **Install ffmpeg** (via `winget`) and make sure it is on your `PATH`.
- **Install Python dependencies** from `requirements.txt`.
- **Run `dji_capture.py`** and verify you get video.

---

## 1. Prerequisites

- Windows 10 or later.
- Python 3.8+ installed and available on `PATH` (check with `python --version`).
- DJI FPV Goggles V2.
- A good USB‑C cable between PC and goggles.

On the goggles:
- Go into the goggles’ settings and **turn off Auto Thermal Management / Auto Temperature Control**.  
  **Reason**: the goggles may dim or shut off the display / video after some time if thermal management is enabled, which can look like a black screen in the capture.

---

## 2. Install WinUSB driver for the goggles using Zadig

`dji_capture.py` uses **libusb / pyusb** to access a **bulk transfer interface** on the goggles (typically **interface 3**).  
On Windows, you must bind this interface to the **WinUSB** driver so libusb can talk to it.

### 2.1 Download Zadig

1. Open a browser and search for **“Zadig USB driver”** or go to the official Zadig site (`https://zadig.akeo.ie`).
2. Download the latest **Zadig** executable (`Zadig.exe`).
3. Run `Zadig.exe` as Administrator (right‑click → **Run as administrator**).

### 2.2 Put goggles into the correct USB mode

1. Power on the DJI FPV Goggles V2.
2. Connect them to the PC via USB.
3. If the goggles present a mode selection (e.g. storage vs. other), choose the mode that exposes them as a device (not UMS/SD card only).  
   (Exact UI may vary by firmware; in most cases, just having them on and plugged in is sufficient.)

### 2.3 Select the correct interface (interface 3)

1. In **Zadig**, go to **Options → List All Devices**.
2. In the dropdown, look for an entry similar to:
   - `DJI FPV Goggles V2`  
   - `DJI Goggles`  
   - Or similar, with **USB ID** `2CA3:001F`.
3. For some devices, Zadig shows different **interfaces** (e.g. `Interface 0`, `Interface 1`, `Interface 2`, `Interface 3`).
   - **Select the entry that corresponds to interface 3**, or the interface that is clearly labeled as the **bulk** / **data** interface if shown.

> **Important:** Do **not** change the driver for unrelated system devices. Double‑check you are working with the device that has **Vendor ID 0x2CA3** and **Product ID 0x001F**.

### 2.4 Install WinUSB

1. With the goggles interface selected:
   - On the right, under **Driver**, choose **WinUSB**.
2. Click **Install Driver** (or **Replace Driver** if something else is bound).
3. Wait for the installation to complete successfully.

Once done, Windows will use **WinUSB** for that interface, and **libusb / pyusb** can access it.

---

## 3. Install ffmpeg via winget

`dji_capture.py` uses **ffmpeg** as a subprocess to decode the raw H.264 stream from the goggles into BGR frames.

### 3.1 Install with winget

1. Open **Windows Terminal** or **PowerShell**.
2. Run:

```powershell
winget install Gyan.FFmpeg
```

3. After installation, open a **new** terminal and verify:

```powershell
ffmpeg -version
```

You should see ffmpeg version information. If `ffmpeg` is not found, make sure `winget` added it to your `PATH`, or manually add the install directory.

> On Windows, `dji_capture.py` starts ffmpeg with the **`CREATE_NO_WINDOW`** flag so you will not see a separate console window for ffmpeg.

---

## 4. Install Python dependencies

From the project directory (where `dji_capture.py` and `requirements.txt` live):

```powershell
cd C:\Users\dan\Documents\simple_digital_fpv_input
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

`requirements.txt` includes:
- **pyusb** – USB access from Python
- **opencv-python** – display frames, FPS overlay, and recording
- **numpy** – efficient frame reshaping
- **libusb** – Python/libusb binding used by pyusb on Windows

---

## 5. Running `dji_capture.py`

### 5.1 Basic live view

With goggles connected and powered on:

```powershell
cd C:\Users\dan\Documents\simple_digital_fpv_input
.venv\Scripts\activate
python dji_capture.py
```

You should see an OpenCV window titled `DJI FPV Goggles` showing the live video.

- **Press `q`** to quit.
- **Press `s`** to save a PNG screenshot into the current directory.

The script overlays an **FPS counter** on the top‑left of the frame.

### 5.2 Raw H.264 mode (`--raw`)

To dump the raw H.264 stream to stdout (for piping into `ffplay` or `ffmpeg`):

```powershell
python dji_capture.py --raw | ffplay -f h264 -i -
```

- In `--raw` mode, **no OpenCV window** is shown.
- The script sends the magic USB packet to start the stream and writes the raw H.264 bytes to stdout.

### 5.3 Recording while displaying (`--record`)

To display and simultaneously record to MP4:

```powershell
python dji_capture.py --record goggles_capture.mp4
```

- The script uses OpenCV’s `VideoWriter` to save an MP4 (`mp4v` codec) at the chosen resolution.
- Press `q` to stop; the file is finalized when you exit.

> **Note:** `--record` is ignored in `--raw` mode (you are responsible for recording when piping the raw stream).

### 5.4 Changing resolution (`--resolution`)

The script decodes whatever resolution the goggles send, then uses ffmpeg to scale to the requested output resolution for display/recording.

Example:

```powershell
python dji_capture.py --resolution 1920x1080
```

Default is **`1280x720`**.

---

## 6. Troubleshooting

### 6.1 “Goggles not found”

Symptoms:
- Script prints something like:
  - `Goggles not found. Make sure they are powered on and connected via USB.`

Checks:
- Are the goggles **powered on**?
- Is the **USB cable** firmly connected and capable of data (not charge‑only)?
- In **Device Manager**, do you see a device with **VID 0x2CA3** and **PID 0x001F** when the goggles are connected?
- Did you follow the **Zadig (WinUSB)** section and bind the right interface (interface 3)?

If needed, unplug/replug the goggles, then rerun `dji_capture.py`.

### 6.2 “Failed to claim interface” / “Could not find a bulk-transfer interface”

Possible reasons:
- Another program is using the goggles (e.g. DJI software or a previous run of the script).
- The driver is not correctly set to **WinUSB** on the bulk interface.

Steps:
1. Close any DJI or other video capture apps.
2. Unplug and reconnect the goggles.
3. Re‑run **Zadig** and verify:
   - You selected the device with **ID 2CA3:001F**.
   - You chose the **correct interface (3)**, not a different interface.
   - The right‑hand driver is **WinUSB**.
4. Reboot Windows if the interface seems stuck or in use.

### 6.3 ffmpeg errors / “ffmpeg not found”

Symptoms:
- `Error: ffmpeg not found. Install it and ensure it is on your PATH.`

Fix:
- Re‑run:

```powershell
winget install Gyan.FFmpeg
```

- Open a **new** terminal and check:

```powershell
ffmpeg -version
```

If still not found, ensure the ffmpeg install directory is on `PATH` or call it via full path in `dji_capture.py` (advanced).

### 6.4 No video / black screen

Possible causes:
- Goggles are not sending video (e.g. no input / no arms / different mode).
- Auto Thermal Management is dimming or shutting off the video after a while.
- The magic bytes were not accepted due to USB issues.

Checks:
- Verify the goggles are **actually displaying video** in the eyepieces.
- In goggles’ settings, **disable Auto Thermal Management / Auto Temperature Control**.
- Make sure the USB connection is stable; try another port or cable.
- Watch the console output for any USB read errors.

### 6.5 Performance / high CPU usage

Decoding H.264 in software and scaling in ffmpeg + OpenCV display can be CPU intensive.

Tips:
- Use the default **1280x720** resolution or even lower (e.g. `854x480`) to reduce load:

```powershell
python dji_capture.py --resolution 854x480
```

- Close other heavy applications.
- Use a machine with a reasonably modern CPU / GPU for best results.

---

## 7. Summary

Once you have:
- Installed **WinUSB** on the goggles’ **interface 3** via Zadig,
- Installed **ffmpeg** via `winget`,
- Installed Python dependencies from `requirements.txt`,

You can:
- Run `python dji_capture.py` for a live OpenCV view (with FPS and screenshots).
- Use `--record` to save MP4 while displaying.
- Use `--raw` to pipe the H.264 stream directly into tools like `ffplay`.

