# Game-test-ai

## Image clicker

This project provides a small Python helper that watches your screen for the target image and clicks it whenever it appears. Press **L** to toggle the clicker on/off.

### Requirements

- macOS (tested on Apple Silicon / M2)
- Python 3.10+

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

### macOS permissions

Grant the terminal (or your Python launcher) these permissions in **System Settings → Privacy & Security**:

- **Accessibility** (to allow clicking)
- **Screen Recording** (to allow screen capture)

### Run

```bash
python3 image_clicker.py
```

By default the script uses `assets/target.png`. If it is missing, it will attempt to download the screenshot automatically. If the download fails, save the screenshot locally and pass the path:

```bash
python3 image_clicker.py --image /path/to/target.png
```

### Controls

- **L**: toggle clicking on/off
- **Esc**: quit
- Move the mouse to the top-left corner to trigger the PyAutoGUI failsafe

### Notes

- If the target is not detected, try lowering `--confidence` (for example `0.85`) or provide a fresh screenshot taken at the same scale as your display.
