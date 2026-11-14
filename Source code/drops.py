"""Counting item drops on a results screen by the colour of their frame.

AOT:R's divine fragments sit in a square frame that runs from pink-purple on the left to light
blue on the right (the 4 kinds of fragment share it; only the item inside differs). count_frames()
finds those frames on a screenshot: it doesn't matter which fragment it is or where on the screen
the results are."""

import cv2
import numpy as np

# hue ranges (OpenCV: 0-180) of the frame: pink / magenta on the left, light blue on the right
PINK = (135, 172)
BLUE = (84, 112)
GRADIENT = (84, 172)  # everything from light blue through purple to pink


def _frame_mask(hsv, hues):
    lo, hi = hues
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    return ((h >= lo) & (h <= hi) & (s >= 90) & (v >= 150)).astype(np.uint8)


def count_frames(img, full_height=None):
    """How many divine-fragment frames are on the screenshot (BGR), and where: (count, [rects]).
    full_height: the whole screen's height when img is only a part of it (slot sizes depend on it)."""
    H = full_height or img.shape[0]
    scale = 1.0
    if H > 900:  # work on a smaller copy: frames are big, this is plenty and much quicker
        scale = 900 / H
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    any_frame = _frame_mask(hsv, GRADIENT)
    pink = _frame_mask(hsv, PINK)
    blue = _frame_mask(hsv, BLUE)
    # join the frame's sides into one shape
    joined = cv2.dilate(any_frame, np.ones((3, 3), np.uint8))
    n, _labels, stats, _ = cv2.connectedComponentsWithStats(joined, 8)
    h_img = H * scale
    found = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        # a slot is a square about 3.5-10 % of the screen's height
        if not (0.035 * h_img <= h <= 0.10 * h_img) or not (0.75 <= w / h <= 1.33):
            continue
        frame = any_frame[y:y + h, x:x + w]
        if frame.sum() > 0.45 * w * h:  # a frame is an outline, not a filled patch of colour
            continue
        # its edges must be coloured all round (a frame), not just a few spots
        edge = max(2, w // 10)
        sides = [frame[:, :edge], frame[:, -edge:], frame[:edge, :], frame[-edge:, :]]
        if any(sd.mean() < 0.12 for sd in sides):
            continue
        # pink on the left side, light blue on the right side
        left_pink = pink[y:y + h, x:x + edge].mean()
        right_blue = blue[y:y + h, x + w - edge:x + w].mean()
        if left_pink < 0.15 or right_blue < 0.15:
            continue
        found.append((int(x / scale), int(y / scale), int(w / scale), int(h / scale)))
    return len(found), found
