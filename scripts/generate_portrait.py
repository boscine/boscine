import os
import sys
import math
import base64
import argparse

# Optional numpy/cv2 import guard
try:
    import numpy as np
    import cv2
    IMPL_AVAILABLE = True
except ImportError:
    IMPL_AVAILABLE = False

try:
    from rembg import remove
    REMBG_AVAILABLE = True
except ImportError:
    REMBG_AVAILABLE = False

ASCII_RAMP = " .`:-=+*cs#%@"

def process_image(image_path, target_cols=90):
    if not IMPL_AVAILABLE:
        raise RuntimeError("numpy and opencv-python are required to process image files.")
        
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Could not open image file: {image_path}")

    h, w, _ = img.shape

    if REMBG_AVAILABLE:
        print("Performing background removal with rembg...")
        with open(image_path, "rb") as f:
            img_bytes = f.read()
        out_bytes = remove(img_bytes)
        nparr = np.frombuffer(out_bytes, np.uint8)
        rgba = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)
        
        if rgba is not None and rgba.shape[2] == 4:
            alpha = rgba[:, :, 3] / 255.0
            rgb = rgba[:, :, :3]
            bg = np.ones_like(rgb, dtype=np.uint8) * 255
            composite = (rgb * alpha[:, :, None] + bg * (1 - alpha[:, :, None])).astype(np.uint8)
        else:
            composite = img
    else:
        composite = img

    gray = cv2.cvtColor(composite, cv2.COLOR_BGR2GRAY)
    target_rows = int(round(target_cols * (h / w) * 0.48))
    resized = cv2.resize(gray, (target_cols, target_rows), interpolation=cv2.INTER_AREA)

    filtered = cv2.bilateralFilter(resized, d=5, sigmaColor=75, sigmaSpace=75)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    clahe_img = clahe.apply(filtered)

    normalized = clahe_img / 255.0
    darkened = np.power(normalized, 1.7) * 255.0
    darkened = np.clip(darkened, 0, 255).astype(np.uint8)

    ramp_len = len(ASCII_RAMP)
    rows_text = []
    for r in range(target_rows):
        row_chars = []
        for c in range(target_cols):
            val = darkened[r, c]
            idx = int((255 - val) / 255.0 * (ramp_len - 1))
            idx = max(0, min(ramp_len - 1, idx))
            row_chars.append(ASCII_RAMP[idx])
        rows_text.append("".join(row_chars))

    return rows_text, target_cols, target_rows

def generate_svg(rows_text, cols, rows, font_b64=None, output_path="portrait.svg"):
    font_size = 12.9
    char_w = 7.74
    char_h = 13.5
    margin = 20
    
    svg_w = int(cols * char_w + margin * 2)
    svg_h = int(rows * char_h + margin * 2)

    font_style = ""
    font_family = "'JetBrains Mono', 'Liberation Mono', 'DejaVu Sans Mono', monospace"
    if font_b64:
        font_style = f"""
    @font-face {{
      font-family: 'JetBrains Mono';
      src: url(data:font/woff2;charset=utf-8;base64,{font_b64}) format('woff2');
      font-weight: normal;
      font-style: normal;
    }}
    """

    svg_lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">',
        '  <style>',
        font_style,
        f'    .ascii-text {{ font-family: {font_family}; font-size: {font_size}px; fill: #58a6ff; xml:space: preserve; white-space: pre; }}',
        '    .bg { fill: #0d1117; rx: 8px; }',
        '  </style>',
        f'  <rect width="{svg_w}" height="{svg_h}" class="bg" />',
        '  <defs>'
    ]

    total_row_duration = 0.08
    for idx in range(rows):
        y_pos = margin + idx * char_h
        begin_sec = round(idx * 0.09, 2)
        
        clip_def = f'''    <clipPath id="clip-{idx}">
      <rect x="{margin}" y="{y_pos - 10}" width="0" height="{char_h + 4}">
        <animate attributeName="width" from="0" to="{cols * char_w}" dur="{total_row_duration}s" begin="{begin_sec}s" fill="freeze" />
      </rect>
    </clipPath>'''
        svg_lines.append(clip_def)

    svg_lines.append('  </defs>')

    for idx, text_line in enumerate(rows_text):
        y_pos = margin + (idx + 1) * char_h - 3
        escaped_text = text_line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace(" ", "&#160;")
        text_el = f'  <text x="{margin}" y="{y_pos}" class="ascii-text" clip-path="url(#clip-{idx})">{escaped_text}</text>'
        svg_lines.append(text_el)

    svg_lines.append('</svg>')

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(svg_lines))
    print(f"Generated SVG portrait: {output_path}")

def generate_sample_portrait(cols=90, font_b64=None, output_path="portrait.svg"):
    aspect_ratio = 1.2
    rows = int(cols * aspect_ratio * 0.48)
    rows_text = []
    
    cx, cy = cols / 2, rows / 2
    for r in range(rows):
        row_chars = []
        for c in range(cols):
            dx = (c - cx) / (cols / 2)
            dy = (r - cy) / (rows / 2)
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < 0.35:
                val = 20
            elif dist < 0.7:
                val = 120 + int(30 * math.sin(c * 0.2 + r * 0.2))
            elif dist < 0.9:
                val = 200
            else:
                val = 255

            ramp_len = len(ASCII_RAMP)
            idx = int((255 - val) / 255.0 * (ramp_len - 1))
            idx = max(0, min(ramp_len - 1, idx))
            row_chars.append(ASCII_RAMP[idx])
        rows_text.append("".join(row_chars))

    generate_svg(rows_text, cols, rows, font_b64=font_b64, output_path=output_path)

def main():
    parser = argparse.ArgumentParser(description="Generate animated ASCII SVG portrait from photo.")
    parser.add_argument("--image", type=str, help="Path to input photo")
    parser.add_argument("--cols", type=int, default=90, help="Column count (default: 90)")
    parser.add_argument("--font", type=str, help="Path to woff2 font file to base64 embed")
    parser.add_argument("--output", type=str, default="portrait.svg", help="Output SVG path")
    args = parser.parse_args()

    font_b64 = None
    if args.font and os.path.exists(args.font):
        with open(args.font, "rb") as f:
            font_b64 = base64.b64encode(f.read()).decode("ascii")

    if args.image and os.path.exists(args.image):
        rows_text, cols, rows = process_image(args.image, target_cols=args.cols)
        generate_svg(rows_text, cols, rows, font_b64=font_b64, output_path=args.output)
    else:
        generate_sample_portrait(cols=args.cols, font_b64=font_b64, output_path=args.output)

if __name__ == "__main__":
    main()
