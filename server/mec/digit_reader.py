# digit_reader.py
import numpy as np
import cv2
from tensorflow.keras.models import load_model

_model_cache = {}

def load_digit_model(model_path, input_size=40):
    """
    Load Keras digit model (expects shape (None, H, W, 1)).
    Caches the model object.
    """
    key = (model_path, input_size)
    if key in _model_cache:
        return _model_cache[key]
    model = load_model(model_path)
    _model_cache[key] = (model, input_size)
    return _model_cache[key]

def _preprocess_digit_img(img, size):
    """
    img: grayscale crop of single digit (numpy array)
    size: (int) target width/height (square)
    Returns: normalized float32 array shaped (size, size, 1)
    """
    # Ensure grayscale
    if len(img.shape) == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Resize preserving aspect by padding
    h, w = img.shape[:2]
    # threshold and invert to get white foreground on black
    _, th = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Find bounding box of the digit to crop tightly (helps with alignment)
    coords = cv2.findNonZero(th)
    if coords is not None:
        x, y, wbox, hbox = cv2.boundingRect(coords)
        digit = th[y:y+hbox, x:x+wbox]
    else:
        digit = th
    # Resize to fit into target size while keeping aspect
    digit_h, digit_w = digit.shape[:2]
    if digit_h == 0 or digit_w == 0:
        digit_resized = np.zeros((size, size), dtype=np.uint8)
    else:
        scale = (size - 4) / max(digit_h, digit_w)  # small margin
        new_w = max(1, int(digit_w * scale))
        new_h = max(1, int(digit_h * scale))
        digit_resized = cv2.resize(digit, (new_w, new_h), interpolation=cv2.INTER_AREA)
        # pad to size
        canvas = np.zeros((size, size), dtype=np.uint8)
        sx = (size - new_h) // 2
        sy = (size - new_w) // 2
        canvas[sx:sx+new_h, sy:sy+new_w] = digit_resized
        digit_resized = canvas
    # normalize to 0..1 float32, invert so model sees 1 for foreground if needed
    arr = digit_resized.astype(np.float32) / 255.0
    # Model likely trained on white digit (1) on black (0). If needed invert:
    # Check mean to guess
    if np.mean(arr) > 0.6:
        arr = 1.0 - arr
    arr = arr.reshape((size, size, 1))
    return arr

def segment_4_digits(roi_img):
    """
    roi_img: color or gray image for rollerset (contains 4 digits horizontally).
    Returns list of 4 grayscale digit crops (numpy arrays).
    Segmentation: equal vertical splits into 4 parts (works for fixed-position rollers).
    """
    if len(roi_img.shape) == 3:
        gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
    else:
        gray = roi_img.copy()
    h, w = gray.shape
    # remove small border to avoid edges
    pad = max(2, int(0.03 * w))
    left = pad
    right = w - pad
    usable = gray[:, left:right]
    uw = usable.shape[1]
    # split into 4 equal wide zones
    digit_width = uw // 4
    digits = []
    for i in range(4):
        sx = i * digit_width
        ex = sx + digit_width if i < 3 else uw  # last gets remainder
        crop = usable[:, sx:ex]
        digits.append(crop)
    return digits

def read_roller_number(roi_img, model_tuple=None, model_path=None, model_input_size=40, return_conf=False):
    """
    Read a 4-digit roller ROI and return a string of 4 digits.
    Provide either model_tuple (model, input_size) returned from load_digit_model,
    or model_path and model_input_size.
    """
    if model_tuple is None:
        if model_path is None:
            raise ValueError("Provide model_tuple or model_path")
        model, _ = load_digit_model(model_path, model_input_size)
    else:
        model, _ = model_tuple

    size = model_input_size
    digit_crops = segment_4_digits(roi_img)
    digits = []
    confs = []
    for crop in digit_crops:
        x = _preprocess_digit_img(crop, size)
        x_input = np.expand_dims(x, axis=0)  # shape (1,H,W,1)
        preds = model.predict(x_input, verbose=0)
        if preds.ndim == 2 and preds.shape[1] >= 10:
            idx = int(preds[0].argmax())
            prob = float(preds[0][idx])
            digits.append(str(idx))
            confs.append(prob)
        else:
            # fallback: try thresholding and simple centroid heuristic -> uncertain
            digits.append("?")
            confs.append(0.0)
    result = "".join(digits)
    if return_conf:
        return result, confs
    return result
