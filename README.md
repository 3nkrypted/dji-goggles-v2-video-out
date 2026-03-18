# DJI Goggles V2 — USB Video Out

Standalone tool to stream live FPV video from DJI FPV Goggles V2 to your PC over USB-C

Tested with Caddx Vista paired to Goggles V2.

Based on the USB bulk transfer protocol discovered by [fpv-wtf/voc-poc](https://github.com/fpv-wtf/voc-poc).

## How it works

The DJI Goggles V2 expose a USB bulk transfer endpoint. This tool sends magic bytes `0x524d5654` to initiate an H.264 video stream, decodes it with ffmpeg, and displays it using OpenCV.

## Usage
```
python dji_capture.py                                          # Normal display
python dji_capture.py --spectator --title "FPV Live Feed"      # Clean fullscreen
python dji_capture.py --wait                                   # Wait for goggles
python dji_capture.py --raw | ffplay -i - -f h264              # Pipe to ffplay
python dji_capture.py --record flight.mp4                      # Record to file
```

## Requirements

- DJI FPV Goggles V2
- USB-C data cable
- Python 3.10+ and ffmpeg on PATH
- WinUSB driver via Zadig (see setup_windows.md)

## Install
```
pip install -r requirements.txt
```

## Standalone EXE

Download from [Releases](https://github.com/3nkrypted/dji-goggles-v2-video-out/releases) or build yourself:
```
build.bat
```

## Credits

Protocol discovered by [fpv-wtf](https://github.com/fpv-wtf).
