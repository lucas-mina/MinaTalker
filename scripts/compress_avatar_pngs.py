#!/usr/bin/env python3
"""Recompress avatar PNG assets with lossless zlib level 9."""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.utils.logging import logger
from src.utils.png_io import PngProfile, recompress_avatar_pngs


def _iter_avatar_dirs(avatars_root: str, avatar_id: str | None) -> list[str]:
    if avatar_id:
        path = os.path.join(avatars_root, avatar_id)
        if not os.path.isdir(path):
            raise SystemExit(f"Avatar not found: {path}")
        return [path]

    if not os.path.isdir(avatars_root):
        raise SystemExit(f"Avatars root not found: {avatars_root}")

    return sorted(
        os.path.join(avatars_root, name)
        for name in os.listdir(avatars_root)
        if os.path.isdir(os.path.join(avatars_root, name))
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--avatar-id", help="Single avatar folder name under data/avatars/")
    parser.add_argument(
        "--avatars-root",
        default=os.path.join(ROOT, "data", "avatars"),
        help="Root directory containing avatar folders",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Always rewrite PNGs even when larger (needed after palette compression)",
    )
    parser.add_argument("--workers", type=int, default=0, help="Parallel workers (0 = auto)")
    args = parser.parse_args()

    workers = args.workers if args.workers > 0 else None

    for avatar_path in _iter_avatar_dirs(args.avatars_root, args.avatar_id):
        avatar_id = os.path.basename(avatar_path)
        logger.info("Compressing avatar %s (lossless)", avatar_id)
        kwargs = {"profile": PngProfile.LOSSLESS, "force": args.force}
        if workers is not None:
            kwargs["workers"] = workers
        recompress_avatar_pngs(avatar_path, **kwargs)


if __name__ == "__main__":
    main()
