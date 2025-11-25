# barcode_ultra_robust.py
import cv2
import numpy as np

# ------------------------------------------------------------
# EAN-13 Encoding Tables
# ------------------------------------------------------------
L = ["0001101","0011001","0010011","0111101","0100011",
     "0110001","0101111","0111011","0110111","0001011"]
G = ["0100111","0110011","0011011","0100001","0010111",
     "0001111","0010001","0000111","0001001","0011111"]
R = [s[::-1] for s in L]

# ------------------------------------------------------------
# 1. Preprocessing + Auto-crop + Deskew
# ------------------------------------------------------------
def deskew_horizontal(bw_img):
    h, w = bw_img.shape
    if h < 20 or w < 100:
        return bw_img

    edges = cv2.Canny(bw_img, 50, 150, apertureSize=3)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=max(30, min(h, w) // 10))
    if lines is None:
        return bw_img

    angles = []
    for rho, theta in lines[:, 0]:
        # Consider near-horizontal: theta ~ 90° (= π/2 rad)
        deviation = abs(theta - np.pi / 2)
        if deviation < np.pi / 8:  # ±22.5°
            angles.append(deviation if theta < np.pi / 2 else -deviation)

    if not angles:
        return bw_img

    median_angle = np.median(angles) * 180 / np.pi
    if abs(median_angle) < 1.0:
        return bw_img

    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
    rotated = cv2.warpAffine(
        bw_img, M, (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=255  # white background
    )
    print(f"✅ Deskewed by {median_angle:+.2f}°")
    return rotated


def get_binary_candidates(gray):
    """Return list of plausible binary images (black bars on white)"""
    blurred = cv2.GaussianBlur(gray, (7, 7), 0)

    candidates = []

    # 1. Adaptive (your original)
    bin1 = cv2.adaptiveThreshold(
        blurred, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 41, 10
    )
    candidates.append(bin1)

    # 2. Otsu (with inversion attempts)
    _, otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    candidates.append(255 - otsu)  # dark-on-light
    candidates.append(otsu)         # light-on-dark (if needed)

    # 3. CLAHE-enhanced + Otsu
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    enhanced = clahe.apply(blurred)
    _, cl = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    candidates.append(255 - cl)
    candidates.append(cl)

    # Deduplicate by sum (roughly)
    uniq = []
    seen = set()
    for cand in candidates:
        key = round(np.sum(cand) / 1000)
        if key not in seen:
            seen.add(key)
            uniq.append(cand)
    return uniq[:4]  # limit to top 4


def preprocess_and_crop(img_path):
    img = cv2.imread(img_path)
    if img is None:
        raise FileNotFoundError(f"Image not found: {img_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h_orig, w_orig = gray.shape

    # Downscale for speed if large
    if max(h_orig, w_orig) > 1200:
        scale = 1000 / max(h_orig, w_orig)
        gray = cv2.resize(gray, (int(w_orig * scale), int(h_orig * scale)), interpolation=cv2.INTER_AREA)
        print(f"📏 Downscaled to {gray.shape}")

    best_band = None
    best_score = -1

    for idx, binary in enumerate(get_binary_candidates(gray)):
        binary = deskew_horizontal(binary)

        # Find high-gradient rows
        grad = np.abs(np.diff(binary.astype(np.int16), axis=1)).sum(axis=1)
        if len(grad) < 30:
            continue

        top_rows = np.argsort(grad)[-min(30, len(grad) // 2):]
        y_min = max(0, int(np.min(top_rows) - 15))
        y_max = min(binary.shape[0], int(np.max(top_rows) + 15))
        band = binary[y_min:y_max, :]

        # Score by black pixel density (avoid over-cropped/empty)
        black_frac = np.mean(band == 0)
        score = black_frac * 0.7 + (y_max - y_min) / binary.shape[0] * 0.3

        if score > best_score:
            best_score = score
            best_band = band
            print(f"✅ Binary candidate {idx+1}: band {band.shape}, black={black_frac:.2%}")

    if best_band is None:
        raise RuntimeError("Failed to extract barcode band")

    return best_band


# ------------------------------------------------------------
# 2. Get clean 1D scan line (best-of-N, not average)
# ------------------------------------------------------------
def get_scan_signal(binary_band, candidates=30):
    h, w = binary_band.shape
    if h < 3:
        return binary_band[0] // 255

    best_line = None
    best_trans = -1

    # Sample random + evenly spaced lines
    ys = np.unique(np.concatenate([
        np.linspace(5, h-6, min(15, h-10), dtype=int),
        np.random.randint(5, h-5, size=candidates)
    ]))

    for y in ys:
        if y < 0 or y >= h:
            continue
        line = binary_band[y].astype(np.uint8) // 255  # 1 = black, 0 = white
        trans = np.sum(np.abs(np.diff(line)))
        if trans > best_trans:
            best_trans = trans
            best_line = line

    print(f"🎯 Chose scan line with {best_trans} transitions")
    return best_line


# ------------------------------------------------------------
# 3. Forgiving EAN-13 decoder
# ------------------------------------------------------------
def match_pattern(block):
    if len(block) != 4:
        return None
    total = sum(block)
    if total == 0:
        return None

    # Try normalizing to 6, 7, or 8 modules
    for target in [7, 6, 8]:
        ratios = [round(x * target / total) for x in block]
        # Clamp to [1,4], adjust sum
        for _ in range(5):
            s = sum(ratios)
            if s == target:
                break
            if s > target:
                i = np.argmax(ratios)
                ratios[i] = max(1, ratios[i] - 1)
            else:
                i = np.argmax(ratios)
                ratios[i] = min(4, ratios[i] + 1)
        if sum(ratios) != target:
            continue
        pat = ''.join(map(str, ratios))
        if pat in L: return L.index(pat)
        if pat in G: return G.index(pat)
        if pat in R: return R.index(pat)

    return None


def decode_ean13(signal):
    if len(signal) < 50:
        return None

    # Get run-length encoding (0→1 or 1→0 transitions)
    changes = np.where(np.diff(signal, prepend=signal[0]))[0]
    runs = np.diff(np.append(changes, len(signal))).astype(float)

    # Estimate module size: median of smallest non-zero runs
    nonzero = runs[runs > 0]
    if len(nonzero) < 5:
        return None
    module = np.median(np.sort(nonzero)[:max(3, len(nonzero)//5)])
    module = max(0.7, min(5.0, module))  # clamp reasonable range
    print(f"[DEBUG] Estimated module ≈ {module:.2f}, runs: {len(runs)}")

    # Search forward and backward
    search_range = list(range(0, max(1, len(runs) - 50))) + \
                   list(range(max(0, len(runs)-200), len(runs)-50))
    search_range = sorted(set(search_range))

    for start_idx in search_range:
        if start_idx + 55 > len(runs):
            continue

        # Check start guard: ~[1,1,1] modules
        g = runs[start_idx:start_idx+3]
        if len(g) < 3:
            continue
        if not all(0.4 < x/module < 2.6 for x in g):
            continue

        digits = []
        pos = start_idx + 3

        # Left 6 digits (L/G)
        for _ in range(6):
            if pos + 3 >= len(runs):
                break
            d = match_pattern(runs[pos:pos+4])
            if d is None:
                break
            digits.append(d)
            pos += 4
        else:  # only if loop didn’t break
            # Center guard: 5 modules → [1,1,1,1,1]
            if pos + 4 >= len(runs):
                continue
            cg = runs[pos:pos+5]
            if all(0.4 < x/module < 2.6 for x in cg):
                pos += 5

                # Right 6 digits (R)
                for _ in range(6):
                    if pos + 3 >= len(runs):
                        break
                    d = match_pattern(runs[pos:pos+4])
                    if d is None:
                        break
                    digits.append(d)
                    pos += 4
                else:
                    if len(digits) == 12:
                        # Checksum
                        s = sum(digits[::2]) * 3 + sum(digits[1::2])
                        check = (10 - s % 10) % 10
                        result = ''.join(map(str, digits)) + str(check)
                        print(f"🎉 Candidate decode: {result}")
                        return result

    print("❌ No valid EAN-13 pattern found")
    return None


# ------------------------------------------------------------
# 4. Main API
# ------------------------------------------------------------
def scan_barcode_image(path):
    try:
        band = preprocess_and_crop(path)
        signal = get_scan_signal(band, candidates=40)
        result = decode_ean13(signal)
        return result
    except Exception as e:
        print(f"⚠️ Exception: {e}")
        import traceback
        traceback.print_exc()
        return None


# ========= RUN =========
if __name__ == "__main__":
    import sys
    img_path = sys.argv[1] if len(sys.argv) > 1 else "ean_13-3450569701.png"
    print(f"🔍 Scanning: {img_path}")
    code = scan_barcode_image(img_path)
    print("\n" + "="*50)
    if code:
        print(f"✅ SUCCESS: {code}")
    else:
        print("❌ FAILED — suggestions:")
        print("   • Is the barcode EAN-13 (13 digits, usually on products)?")
        print("   • Try a higher-res, front-on, well-lit photo.")
        print("   • If rotated >10°, re-shoot straight-on.")
        print("   • Share the image — I’ll decode it manually in seconds 😊")
    print("="*50)