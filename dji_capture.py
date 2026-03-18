#!/usr/bin/env python
"""
DJI FPV Goggles V2 USB capture: read H.264 from USB, decode via ffmpeg, display with OpenCV.

Protocol: claim interface 3, write magic 0x524d5654 to endpoint 0x03, read H.264 from 0x84.
Device is reset at start and on exit so the next run works without unplugging.
"""

import argparse
import os
import sys
import threading
import time
import subprocess
import signal
import shutil
from typing import Optional, Tuple

import libusb_package
import usb.core 
import usb.util
import numpy as np
import cv2


VENDOR_ID = 0x2CA3
PRODUCT_ID = 0x001F
MAGIC_BYTES = b"\x52\x4D\x56\x54"  # 0x524d5654

BULK_INTERFACE_NUM = 3
BULK_OUT_ENDPOINT = 0x03
BULK_IN_ENDPOINT = 0x84

USB_READ_SIZE = 16384
USB_READ_TIMEOUT_MS = 3000
MAGIC_WRITE_TIMEOUT_MS = 5000
MAGIC_RETRY_INTERVAL = 0.5  # seconds between magic-byte retries

DEFAULT_RESOLUTION = "1280x720"
DEFAULT_FIND_TIMEOUT = 60.0  # seconds to wait for goggles when not using --wait


class USBVideoStreamError(Exception):
    pass


def parse_resolution(res_str: str) -> Tuple[int, int]:
    try:
        w_str, h_str = res_str.lower().split("x")
        w, h = int(w_str), int(h_str)
        if w <= 0 or h <= 0:
            raise ValueError
        return w, h
    except Exception:
        raise argparse.ArgumentTypeError(
            f"Invalid resolution '{res_str}'. Expected format like 1280x720."
        )


def find_goggles(retry_interval: float = 2.0, timeout: Optional[float] = None) -> usb.core.Device:
    backend = libusb_package.get_libusb1_backend()
    waiting = timeout is None
    msg = (
        f"Searching for DJI FPV Goggles V2 (VID=0x{VENDOR_ID:04x}, PID=0x{PRODUCT_ID:04x})..."
        + (" Waiting for device (use Ctrl+C to cancel)..." if waiting else f" (will give up after {int(timeout)}s)...")
    )
    print(msg)
    start = time.time()
    while True:
        dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID, backend=backend)
        if dev is not None:
            print("Goggles found.")
            return dev
        if timeout is not None and (time.time() - start) > timeout:
            raise USBVideoStreamError(
                "Goggles not found. Connect via USB and ensure WinUSB is installed for interface 3 (Zadig). "
                "Use --wait to keep waiting until the device is plugged in."
            )
        print("Goggles not found yet. Retrying...")
        time.sleep(retry_interval)


def reset_device(dev: usb.core.Device) -> None:
    try:
        dev.reset()
        print("Device reset.")
    except usb.core.USBError as e:
        print(f"Note: device reset returned: {e}")


def get_bulk_endpoints(dev: usb.core.Device) -> Tuple[usb.core.Endpoint, usb.core.Endpoint]:
    try:
        dev.set_configuration()
    except usb.core.USBError:
        pass
    cfg = dev.get_active_configuration()
    intf = usb.util.find_descriptor(cfg, bInterfaceNumber=BULK_INTERFACE_NUM)
    if intf is None:
        raise USBVideoStreamError(f"Interface {BULK_INTERFACE_NUM} not found.")
    ep_out = usb.util.find_descriptor(intf, bEndpointAddress=BULK_OUT_ENDPOINT)
    ep_in = usb.util.find_descriptor(intf, bEndpointAddress=BULK_IN_ENDPOINT)
    if ep_out is None or ep_in is None:
        raise USBVideoStreamError(
            f"Endpoints 0x{BULK_OUT_ENDPOINT:02x} / 0x{BULK_IN_ENDPOINT:02x} not found."
        )
    print(f"Using OUT 0x{BULK_OUT_ENDPOINT:02x}, IN 0x{BULK_IN_ENDPOINT:02x}.")
    return ep_out, ep_in


def claim_interface(dev: usb.core.Device) -> None:
    try:
        if dev.is_kernel_driver_active(BULK_INTERFACE_NUM):
            dev.detach_kernel_driver(BULK_INTERFACE_NUM)
    except (NotImplementedError, usb.core.USBError):
        pass
    try:
        usb.util.claim_interface(dev, BULK_INTERFACE_NUM)
        print(f"Claimed interface {BULK_INTERFACE_NUM}.")
    except usb.core.USBError as e:
        raise USBVideoStreamError(
            f"Failed to claim interface {BULK_INTERFACE_NUM}: {e}. "
            "Close other apps using the goggles; ensure WinUSB on interface 3."
        )


def release_interface(dev: usb.core.Device) -> None:
    try:
        usb.util.release_interface(dev, BULK_INTERFACE_NUM)
        print(f"Released interface {BULK_INTERFACE_NUM}.")
    except usb.core.USBError:
        pass


def start_ffmpeg(width: int, height: int) -> subprocess.Popen:
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path is None:
        raise USBVideoStreamError(
            "ffmpeg not found. Install it (e.g. via winget or include ffmpeg.exe beside the dji_capture.exe) "
            "and ensure it can be launched as 'ffmpeg'."
        )

    cmd = [
        ffmpeg_path, "-loglevel", "error", "-fflags", "nobuffer", "-flags", "low_delay",
        "-an", "-i", "-",
        "-vf", f"scale={width}:{height}",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-",
    ]
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
        )
    except FileNotFoundError:
        raise USBVideoStreamError(
            "ffmpeg not found. Install it (e.g. winget install Gyan.FFmpeg) and ensure it is on PATH."
        )
    if proc.stdin is None or proc.stdout is None:
        raise USBVideoStreamError("Failed to start ffmpeg with pipes.")
    return proc


def _is_timeout_error(e: Exception) -> bool:
    if getattr(e, "errno", None) == 110:
        return True
    return "timeout" in str(e).lower()


def usb_reader_thread(
    ep_in: usb.core.Endpoint,
    ep_out: usb.core.Endpoint,
    ffmpeg_stdin,
    stop_event: threading.Event,
) -> None:
    while not stop_event.is_set():
        try:
            ep_out.write(MAGIC_BYTES, timeout=MAGIC_WRITE_TIMEOUT_MS)
            print("Magic bytes sent.")
            break
        except usb.core.USBError as e:
            if _is_timeout_error(e):
                print("Magic bytes write timed out, retrying...")
                time.sleep(MAGIC_RETRY_INTERVAL)
                continue
            print(f"Failed to send magic bytes: {e}")
            stop_event.set()
            return
    else:
        return
    while not stop_event.is_set():
        try:
            data = ep_in.read(USB_READ_SIZE, timeout=USB_READ_TIMEOUT_MS)
            if not data:
                continue
            if ffmpeg_stdin.closed:
                break
            ffmpeg_stdin.write(bytes(data))
            ffmpeg_stdin.flush()
        except usb.core.USBError as e:
            if getattr(e, "errno", None) == 110 or "timeout" in str(e).lower():
                continue
            print(f"USB read error: {e}")
            break
        except BrokenPipeError:
            break
        except Exception as e:
            print(f"USB reader error: {e}")
            break
    print("USB reader thread exiting.")


def display_loop(
    ffmpeg_proc: subprocess.Popen,
    width: int,
    height: int,
    record_path: Optional[str],
    window_title: str,
    spectator: bool,
) -> None:
    frame_size = width * height * 3
    writer = None
    if record_path:
        writer = cv2.VideoWriter(
            record_path, cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (width, height)
        )
        if not writer.isOpened():
            writer = None
        else:
            print(f"Recording to {record_path}")

    cv2.namedWindow(window_title, cv2.WINDOW_NORMAL)
    if spectator:
        # Fullscreen, clean spectator view (no overlays / debug text)
        cv2.setWindowProperty(window_title, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    else:
        print("Display: press 'q' to quit, 's' for screenshot.")
    frame_count = 0
    fps = 0.0
    last_fps_time = time.time()
    shot_idx = 0
    try:
        while True:
            buf = b""
            while len(buf) < frame_size:
                chunk = ffmpeg_proc.stdout.read(frame_size - len(buf))
                if not chunk:
                    return
                buf += chunk
            frame = np.frombuffer(buf, dtype=np.uint8).reshape((height, width, 3)).copy()
            frame_count += 1
            now = time.time()
            if not spectator:
                if now - last_fps_time >= 1.0:
                    fps = frame_count / (now - last_fps_time)
                    frame_count = 0
                    last_fps_time = now
                cv2.putText(
                    frame, f"FPS: {fps:.1f}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2, cv2.LINE_AA,
                )
            if writer is not None:
                writer.write(frame)
            cv2.imshow(window_title, frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            elif key == ord("s"):
                name = f"screenshot_{int(time.time())}_{shot_idx}.png"
                cv2.imwrite(name, frame)
                print(f"Saved {name}")
                shot_idx += 1
    finally:
        if writer is not None:
            writer.release()
        cv2.destroyAllWindows()


def usb_raw_thread(
    ep_in: usb.core.Endpoint,
    ep_out: usb.core.Endpoint,
    stop_event: threading.Event,
) -> None:
    out = getattr(sys.stdout, "buffer", sys.stdout)
    if os.name == "nt":
        try:
            import msvcrt
            msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
        except Exception:
            pass
    while not stop_event.is_set():
        try:
            ep_out.write(MAGIC_BYTES, timeout=MAGIC_WRITE_TIMEOUT_MS)
            print("Magic bytes sent.", file=sys.stderr)
            break
        except usb.core.USBError as e:
            if _is_timeout_error(e):
                print("Magic bytes write timed out, retrying...", file=sys.stderr)
                time.sleep(MAGIC_RETRY_INTERVAL)
                continue
            print(f"Magic write failed: {e}", file=sys.stderr)
            stop_event.set()
            return
    else:
        return
    while not stop_event.is_set():
        try:
            data = ep_in.read(USB_READ_SIZE, timeout=USB_READ_TIMEOUT_MS)
            if not data:
                continue
            out.write(bytes(data))
            out.flush()
        except usb.core.USBError as e:
            if getattr(e, "errno", None) == 110 or "timeout" in str(e).lower():
                continue
            print(f"USB read error: {e}", file=sys.stderr)
            break
        except BrokenPipeError:
            break
    print("USB raw thread exiting.", file=sys.stderr)


def run_raw(resolution: Tuple[int, int], wait: bool) -> None:
    dev = find_goggles(timeout=None if wait else DEFAULT_FIND_TIMEOUT)
    try:
        reset_device(dev)
        ep_out, ep_in = get_bulk_endpoints(dev)
        claim_interface(dev)
        stop = threading.Event()
        t = threading.Thread(target=usb_raw_thread, args=(ep_in, ep_out, stop), daemon=True)
        t.start()
        try:
            while t.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            stop.set()
            t.join(timeout=2.0)
    finally:
        release_interface(dev)
        reset_device(dev)


def run_display(
    resolution: Tuple[int, int],
    record_path: Optional[str],
    window_title: str,
    spectator: bool,
    wait: bool,
) -> None:
    width, height = resolution
    dev = find_goggles(timeout=None if wait else DEFAULT_FIND_TIMEOUT)
    try:
        reset_device(dev)
        ep_out, ep_in = get_bulk_endpoints(dev)
        claim_interface(dev)
        ffmpeg_proc = start_ffmpeg(width, height)
        stop = threading.Event()
        reader = threading.Thread(
            target=usb_reader_thread,
            args=(ep_in, ep_out, ffmpeg_proc.stdin, stop),
            daemon=True,
        )
        reader.start()
        try:
            display_loop(
                ffmpeg_proc,
                width,
                height,
                record_path,
                window_title=window_title,
                spectator=spectator,
            )
        except KeyboardInterrupt:
            pass
        finally:
            stop.set()
            if ffmpeg_proc.stdin and not ffmpeg_proc.stdin.closed:
                try:
                    ffmpeg_proc.stdin.close()
                except Exception:
                    pass
            try:
                ffmpeg_proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                try:
                    ffmpeg_proc.kill()
                except Exception:
                    pass
            reader.join(timeout=2.0)
    finally:
        release_interface(dev)
        reset_device(dev)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture video from DJI FPV Goggles V2 over USB."
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Dump raw H.264 to stdout (e.g. pipe to ffplay -f h264 -i -).",
    )
    parser.add_argument(
        "--record",
        metavar="PATH",
        help="Record to MP4 while displaying.",
    )
    parser.add_argument(
        "--spectator",
        action="store_true",
        help="Fullscreen spectator mode (no FPS overlay or debug text).",
    )
    parser.add_argument(
        "--title",
        default="DJI FPV Goggles",
        help="Window title text (e.g. 'FPV Live Feed').",
    )
    parser.add_argument(
        "--resolution",
        default=DEFAULT_RESOLUTION,
        type=parse_resolution,
        help=f"Display/record resolution WxH (default {DEFAULT_RESOLUTION}).",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Wait for goggles to be plugged in; connect automatically when they appear.",
    )
    args = parser.parse_args()
    try:
        signal.signal(signal.SIGINT, signal.SIG_DFL)
    except ValueError:
        pass
    try:
        if args.raw:
            run_raw(args.resolution, wait=args.wait)
        else:
            run_display(
                args.resolution,
                args.record,
                window_title=args.title,
                spectator=args.spectator,
                wait=args.wait,
            )
    except USBVideoStreamError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
