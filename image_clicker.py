#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_TARGET_IMAGE_URL = (
    "https://github.com/user-attachments/assets/1f1d29f8-deb0-488c-9d17-2446d4c40e17"
)
DEFAULT_IMAGE_PATH = Path(__file__).resolve().parent / "assets" / "target.png"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SCALE_MATCH_REL_TOL = 0.02
SCALE_IDENTITY_REL_TOL = 0.01
DEFAULT_REGION_PADDING = 120
FULL_SCAN_MISS_LIMIT = 4


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Watch the screen for a target image and click it when found.",
    )
    parser.add_argument(
        "--image",
        type=Path,
        default=DEFAULT_IMAGE_PATH,
        help="Path to the target image to match on screen.",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.9,
        help="Match confidence from 0-1 (requires opencv-python).",
    )
    parser.add_argument(
        "--scan-interval",
        type=float,
        default=0.2,
        help="Seconds to wait between scans when no match is found.",
    )
    parser.add_argument(
        "--click-interval",
        type=float,
        default=0.25,
        help="Seconds to wait after a successful click.",
    )
    parser.add_argument(
        "--toggle-key",
        type=str,
        default="l",
        help="Key that toggles clicking on/off (default: l, case-insensitive).",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Do not attempt to download the default target image.",
    )
    return parser.parse_args()


def is_png(path: Path) -> bool:
    try:
        with path.open("rb") as image_file:
            return image_file.read(len(PNG_SIGNATURE)) == PNG_SIGNATURE
    except OSError:
        return False


def get_error_hint(exc: Exception) -> str | None:
    message = str(exc).lower()
    if not message:
        return None
    if (
        "screen grab failed" in message
        or "screen capture" in message
        or "screencapture" in message
    ):
        return (
            "Screen capture failed. Grant Screen Recording permission to your "
            "terminal/Python app in System Settings → Privacy & Security."
        )
    if "x connection failed" in message or "no display name" in message:
        return (
            "Screen capture failed because no GUI display is available (X connection "
            "failed). Run this script in a desktop session."
        )
    if "accessibility" in message or "not trusted" in message or "assistive" in message:
        return (
            "Mouse/keyboard control failed. Grant Accessibility permission to your "
            "terminal/Python app in System Settings → Privacy & Security."
        )
    return None


def ensure_image(path: Path, allow_download: bool) -> Path:
    if path.exists():
        return path

    if allow_download and path == DEFAULT_IMAGE_PATH:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            print(f"Downloading target image to {path}...")
            urllib.request.urlretrieve(DEFAULT_TARGET_IMAGE_URL, path)
            if not is_png(path):
                path.unlink(missing_ok=True)
                print("Downloaded file is not a PNG image. Please download manually.")
                sys.exit(1)
            return path
        except Exception as exc:
            print(f"Failed to download image: {exc}")

    print(
        "Target image not found. Download it from:\n"
        f"{DEFAULT_TARGET_IMAGE_URL}\n"
        "and save it to the --image path, or pass --image to a local file."
    )
    sys.exit(1)


def locate_target(
    pyautogui: Any,
    image: Any,
    confidence: float,
    region: tuple[int, int, int, int] | None = None,
) -> tuple[int, int, int, int] | None:
    try:
        kwargs: dict[str, Any] = {
            "confidence": confidence,
            "grayscale": True,
        }
        if region is not None:
            kwargs["region"] = region
        return pyautogui.locateOnScreen(image, **kwargs)
    except pyautogui.ImageNotFoundException:
        return None
    except Exception as exc:
        message = str(exc).lower()
        if "opencv" in message and "confidence" in message:
            print(
                "OpenCV is required for confidence matching. "
                "Install with: python3 -m pip install opencv-python"
            )
            sys.exit(1)
        hint = get_error_hint(exc)
        if hint:
            print(hint, file=sys.stderr)
            sys.exit(1)
        raise


def get_screen_scale(pyautogui: Any) -> tuple[float, float]:
    """Return scaling to convert screenshot coordinates to screen coordinates.

    Scaling is applied only when the screenshot dimensions are uniformly scaled
    relative to the screen size within SCALE_MATCH_REL_TOL and differ from 1 by
    SCALE_IDENTITY_REL_TOL.
    """
    try:
        screen_width, screen_height = pyautogui.size()
        screenshot = pyautogui.screenshot()
        screenshot_width, screenshot_height = screenshot.size
    except Exception:
        return (1.0, 1.0)

    if (
        screen_width <= 0
        or screen_height <= 0
        or screenshot_width <= 0
        or screenshot_height <= 0
    ):
        return (1.0, 1.0)

    width_ratio = screenshot_width / screen_width
    height_ratio = screenshot_height / screen_height
    if math.isclose(
        width_ratio, height_ratio, rel_tol=SCALE_MATCH_REL_TOL
    ) and not math.isclose(width_ratio, 1.0, rel_tol=SCALE_IDENTITY_REL_TOL):
        return (1 / width_ratio, 1 / height_ratio)

    return (1.0, 1.0)


def get_screenshot_bounds(pyautogui: Any) -> tuple[int, int]:
    """Return screenshot dimensions, falling back to screen size or (0, 0)."""
    try:
        screenshot = pyautogui.screenshot()
        screenshot_width, screenshot_height = screenshot.size
        if screenshot_width > 0 and screenshot_height > 0:
            return (screenshot_width, screenshot_height)
    except Exception:
        pass
    try:
        return pyautogui.size()
    except Exception:
        return (0, 0)


def expand_region(
    region: tuple[int, int, int, int],
    padding: int,
    bounds: tuple[int, int],
) -> tuple[int, int, int, int]:
    """Expand a (left, top, width, height) region within (max_width, max_height).

    Returns the original region when the expansion would be invalid.
    """
    left, top, width, height = region
    max_width, max_height = bounds
    new_left = max(left - padding, 0)
    new_top = max(top - padding, 0)
    new_right = min(left + width + padding, max_width)
    new_bottom = min(top + height + padding, max_height)
    if new_right <= new_left or new_bottom <= new_top:
        return region
    return (
        new_left,
        new_top,
        max(1, new_right - new_left),
        max(1, new_bottom - new_top),
    )


def load_target_image(image_path: Path) -> Any:
    """Load the target image with Pillow, or fall back to the Path on failure."""
    try:
        from PIL import Image
    except ImportError:
        return image_path
    try:
        with Image.open(image_path) as image:
            return image.copy()
    except OSError:
        return image_path


def main() -> int:
    args = parse_args()
    image_path = ensure_image(args.image, not args.no_download)

    import pyautogui
    from pynput import keyboard

    pyautogui.FAILSAFE = True
    screen_scale = get_screen_scale(pyautogui)
    screenshot_bounds = get_screenshot_bounds(pyautogui)
    target_image = load_target_image(image_path)
    if hasattr(target_image, "size"):
        min_size = min(target_image.size)
        region_padding = max(DEFAULT_REGION_PADDING, min_size // 2)
    else:
        region_padding = DEFAULT_REGION_PADDING

    enabled_event = threading.Event()
    enabled_event.set()
    running_event = threading.Event()
    running_event.set()
    search_region: tuple[int, int, int, int] | None = None
    miss_count = 0

    toggle_key = args.toggle_key.lower()
    toggle_key_label = toggle_key.upper()

    def on_press(key: keyboard.Key | keyboard.KeyCode | None) -> bool | None:
        nonlocal search_region, miss_count
        if key == keyboard.Key.esc:
            running_event.clear()
            return False
        if isinstance(key, keyboard.KeyCode) and key.char:
            if key.char.lower() == toggle_key:
                if enabled_event.is_set():
                    enabled_event.clear()
                    print(f"Clicking paused. Press {toggle_key_label} to resume.")
                else:
                    enabled_event.set()
                    search_region = None
                    miss_count = 0
                    print("Clicking enabled.")

    listener = keyboard.Listener(on_press=on_press)
    listener.start()

    print(
        "Listening for the target image. "
        f"Press {toggle_key_label} to toggle, Esc to quit."
    )

    try:
        while running_event.is_set():
            if enabled_event.is_set():
                region = locate_target(
                    pyautogui,
                    target_image,
                    args.confidence,
                    search_region,
                )
                if not region and search_region is not None:
                    miss_count += 1
                    if miss_count >= FULL_SCAN_MISS_LIMIT:
                        region = locate_target(pyautogui, target_image, args.confidence)
                        if not region:
                            search_region = None
                        miss_count = 0
                if region:
                    center = pyautogui.center(region)
                    click_x = round(center[0] * screen_scale[0])
                    click_y = round(center[1] * screen_scale[1])
                    pyautogui.click(click_x, click_y)
                    search_region = expand_region(
                        region,
                        region_padding,
                        screenshot_bounds,
                    )
                    miss_count = 0
                    time.sleep(args.click_interval)
                else:
                    time.sleep(args.scan_interval)
            else:
                time.sleep(0.1)
    except KeyboardInterrupt:
        running_event.clear()
    except pyautogui.FailSafeException:
        running_event.clear()
        print(
            "PyAutoGUI failsafe triggered (mouse in screen corner). Move the mouse "
            "away or disable with pyautogui.FAILSAFE = False.",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        running_event.clear()
        hint = get_error_hint(exc)
        if hint:
            print(hint, file=sys.stderr)
            return 1
        message = str(exc).strip()
        if message:
            details = f"{exc.__class__.__name__}: {message}"
        else:
            details = f"{exc.__class__.__name__} (no error message provided)"
        print(f"Unexpected error: {details}", file=sys.stderr)
        return 1
    finally:
        listener.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
