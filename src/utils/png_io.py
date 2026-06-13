"""PNG read/write helpers with lossless compression and parallel decode."""

from __future__ import annotations

import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum
from typing import Sequence

import cv2
import numpy as np
from tqdm import tqdm

from src.utils.logging import logger

# OpenCV default PNG compression is ~3; 9 is slower to write but smaller on disk.
PNG_COMPRESSION_LEVEL = 9
DEFAULT_READ_WORKERS = max(4, min(16, (os.cpu_count() or 4)))


class PngProfile(str, Enum):
    """PNG encode profile (lossless only)."""

    LOSSLESS = "lossless"


def imwrite_png(path: str, bgr: np.ndarray, profile: PngProfile = PngProfile.LOSSLESS) -> None:
    """Write a BGR uint8 image as lossless PNG (zlib level 9)."""
    if profile is not PngProfile.LOSSLESS:
        logger.warning("Unsupported PNG profile %s; using lossless", profile.value)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    ok = cv2.imwrite(
        path,
        bgr,
        [int(cv2.IMWRITE_PNG_COMPRESSION), PNG_COMPRESSION_LEVEL],
    )
    if not ok:
        raise OSError(f"cv2.imwrite failed for {path}")


def imread_png(path: str) -> np.ndarray:
    frame = cv2.imread(path, cv2.IMREAD_COLOR)
    if frame is None:
        raise OSError(f"cv2.imread failed for {path}")
    return frame


def _read_one(path: str) -> tuple[str, np.ndarray]:
    return path, imread_png(path)


def read_imgs(
    img_list: Sequence[str],
    *,
    workers: int = DEFAULT_READ_WORKERS,
    show_progress: bool = True,
) -> list[np.ndarray]:
    """Decode PNG paths to BGR frames, preserving img_list order."""
    if not img_list:
        return []

    if workers <= 1 or len(img_list) == 1:
        iterator = img_list
        if show_progress:
            logger.info("reading images...")
            iterator = tqdm(img_list)
        return [imread_png(path) for path in iterator]

    logger.info("reading images with %d workers...", workers)
    ordered: list[np.ndarray | None] = [None] * len(img_list)
    index_by_path = {path: idx for idx, path in enumerate(img_list)}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_read_one, path): path for path in img_list}
        progress = tqdm(total=len(futures), disable=not show_progress)
        for future in as_completed(futures):
            path, frame = future.result()
            ordered[index_by_path[path]] = frame
            progress.update(1)
        progress.close()

    if any(frame is None for frame in ordered):
        missing = sum(1 for frame in ordered if frame is None)
        raise OSError(f"Failed to decode {missing} PNG frame(s)")

    return ordered  # type: ignore[return-value]


def recompress_png_file(
    path: str,
    profile: PngProfile = PngProfile.LOSSLESS,
    *,
    min_savings_ratio: float = 0.02,
    force: bool = False,
) -> tuple[int, int]:
    """
    Re-encode a PNG in place.

    Returns (before_bytes, after_bytes). Skips rewrite when savings are tiny
    unless force=True (e.g. converting palette PNG back to full-color lossless).
    """
    before = os.path.getsize(path)
    bgr = imread_png(path)

    fd, tmp_path = tempfile.mkstemp(suffix=".png", dir=os.path.dirname(path) or ".")
    os.close(fd)
    try:
        imwrite_png(tmp_path, bgr, profile=profile)
        after = os.path.getsize(tmp_path)
        if not force and after >= before * (1.0 - min_savings_ratio):
            os.remove(tmp_path)
            return before, before
        os.replace(tmp_path, path)
        return before, after
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def recompress_png_dir(
    directory: str,
    profile: PngProfile = PngProfile.LOSSLESS,
    *,
    workers: int = DEFAULT_READ_WORKERS,
    force: bool = False,
) -> tuple[int, int, int]:
    """Recompress every *.png under directory (non-recursive)."""
    if not os.path.isdir(directory):
        raise NotADirectoryError(directory)

    paths = sorted(
        os.path.join(directory, name)
        for name in os.listdir(directory)
        if name.lower().endswith(".png")
    )
    if not paths:
        logger.warning("No PNG files found in %s", directory)
        return 0, 0, 0

    total_before = 0
    total_after = 0
    logger.info(
        "Recompressing %d PNG(s) in %s (lossless, force=%s)",
        len(paths),
        directory,
        force,
    )

    def _one(path: str) -> tuple[int, int]:
        return recompress_png_file(path, profile, force=force)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for before, after in tqdm(pool.map(_one, paths), total=len(paths)):
            total_before += before
            total_after += after

    return len(paths), total_before, total_after


def recompress_avatar_pngs(
    avatar_path: str,
    *,
    profile: PngProfile = PngProfile.LOSSLESS,
    workers: int = DEFAULT_READ_WORKERS,
    force: bool = False,
) -> None:
    """Recompress wav2lip-style avatar folders: full_imgs + face_imgs (both lossless)."""
    full_dir = os.path.join(avatar_path, "full_imgs")
    face_dir = os.path.join(avatar_path, "face_imgs")

    if os.path.isdir(full_dir):
        count, before, after = recompress_png_dir(
            full_dir, profile, workers=workers, force=force
        )
        if count:
            delta_mb = (after - before) / (1024 * 1024)
            logger.info(
                "full_imgs: %d files, %.1f MB -> %.1f MB (%+.1f MB)",
                count,
                before / (1024 * 1024),
                after / (1024 * 1024),
                delta_mb,
            )
    else:
        logger.warning("Missing full_imgs directory: %s", full_dir)

    if os.path.isdir(face_dir):
        count, before, after = recompress_png_dir(
            face_dir, profile, workers=workers, force=force
        )
        if count:
            delta_mb = (after - before) / (1024 * 1024)
            logger.info(
                "face_imgs: %d files, %.1f MB -> %.1f MB (%+.1f MB)",
                count,
                before / (1024 * 1024),
                after / (1024 * 1024),
                delta_mb,
            )
    else:
        logger.warning("Missing face_imgs directory: %s", face_dir)
