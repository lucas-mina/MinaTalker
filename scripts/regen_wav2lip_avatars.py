#!/usr/bin/env python3
"""Regenerate wav2lip avatar PNGs from source video (lossless, no watermark)."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GENAVATAR = os.path.join(ROOT, "src", "avatars", "wav2lip", "genavatar_no_error.py")
AVATAR_CONFIG = os.path.join(ROOT, "config", "avatar_config.yaml")
WAV2LIP_CONFIG = os.path.join(ROOT, "config", "config_wav2lip.yaml")

# Avatar full_imgs resolution (1080p portrait). Agora publish uses config video.width/height.
DEFAULT_FULL_WIDTH = 1080
DEFAULT_FULL_HEIGHT = 1920

# avatar folder name -> source mp4 under ./video/
AVATAR_VIDEO_MAP: dict[str, str] = {
    "wav2lip_act_300": "video/ACT_SPK_LS_300/ACT_SPK_LS_300.mp4",
    "wav2lip_act_300_ex": "video/ACT_SPK_LS_300/ACT_SPK_LS_300.mp4",
    "wav2lip_act_400": "video/ACT_SPK_LS_400/ACT_SPK_LS_400.mp4",
    "wav2lip_act_400_ex": "video/ACT_SPK_LS_400/ACT_SPK_LS_400.mp4",
    "wav2lip_act_spk_ls01": "video/ACT_SPK_LS01/ACT_SPK_LS01.mp4",
    "wav2lip_act_spk_ls02": "video/ACT_SPK_LS02/ACT_SPK_LS02.mp4",
    "wav2lip_act_spk_ls03": "video/ACT_SPK_LS03/ACT_SPK_LS03.mp4",
    "wav2lip_act_spk_ls04": "video/ACT_SPK_LS04/ACT_SPK_LS04.mp4",
    "wav2lip_act_spk_ls05": "video/ACT_SPK_LS05/ACT_SPK_LS05.mp4",
    "wav2lip_act_spk_ls06": "video/ACT_SPK_LS06/ACT_SPK_LS06.mp4",
    "wav2lip_act_spk_ls07": "video/ACT_SPK_LS07/ACT_SPK_LS07.mp4",
    "wav2lip_act_spk_ls240_01": "video/ACT_SPK_LS240_01/ACT_SPK_LS240_01.mp4",
    "wav2lip_act_spk_ls240_01_ex": "video/ACT_SPK_LS240_01/ACT_SPK_LS240_01.mp4",
    "wav2lip_act_spk_ls_01": "video/ACT_SPK_LS_01/ACT_SPK_LS_01.mp4",
    "wav2lip_carey_act_spk_ls_01": "video/Carey_ACT_SPK_LS_01/Carey_ACT_SPK_LS_01.mp4",
    "wav2lip_iman_spk_ls04": "video/IMAN_SPK_LS04/IMAN_SPK_LS04.mp4",
    "wav2lip_ling_170": "video/Ling Lipsync Test170/Ling Lipsync Test170.mp4",
    "wav2lip_ling_170_ex": "video/Ling Lipsync Test170/Ling Lipsync Test170.mp4",
    "wav2lip_ling_213": "video/Ling Lipsync Test213/Ling Lipsync Test213.mp4",
    "wav2lip_ling_213_ex": "video/Ling Lipsync Test213/Ling Lipsync Test213.mp4",
    "wav2lip_ling_act_spk_ls_02": "video/LING_ACT_SPK_LS_02/LING_ACT_SPK_LS_02.mp4",
    "wav2lip_mykol_act_spk_ls_01": "video/MYKOL_ACT_SPK_LS_01/MYKOL_ACT_SPK_LS_01.mp4",
    "wav2lip_sunny_act_spk_ls_01": "video/Sunny_ACT_SPK_LS_01/Sunny_ACT_SPK_LS_01.mp4",
    "wav2lip_test_girl": "video/ACT_SPK_LS_400/ACT_SPK_LS_400.mp4",
    "wav2lip_test_girl_ex": "video/ACT_SPK_LS_400/ACT_SPK_LS_400.mp4",
}


def _broadcast_size_from_config() -> tuple[int, int]:
    try:
        with open(WAV2LIP_CONFIG, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        video = data.get("video") or {}
        w = int(video.get("width") or DEFAULT_FULL_WIDTH)
        h = int(video.get("height") or DEFAULT_FULL_HEIGHT)
        return w, h
    except Exception:
        return 864, 1536


def _live_avatar_ids_from_config() -> list[str]:
    with open(AVATAR_CONFIG, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    ids: set[str] = set()
    for entry in data.get("avatars") or []:
        if not entry.get("live", True):
            continue
        for key in ("model_avatar_id", "model_avatar_id_ex"):
            raw = entry.get(key)
            if raw is None:
                continue
            text = str(raw).strip()
            if text:
                ids.add(text)
    return sorted(ids)


def _avatar_complete(avatars_root: str, avatar_id: str) -> bool:
    base = os.path.join(avatars_root, avatar_id)
    coords = os.path.join(base, "coords.pkl")
    face_dir = os.path.join(base, "face_imgs")
    if not os.path.isfile(coords):
        return False
    if not os.path.isdir(face_dir):
        return False
    return any(name.lower().endswith(".png") for name in os.listdir(face_dir))


def _iter_targets(
    avatars_root: str,
    avatar_id: str | None,
    *,
    from_config: bool,
    skip_complete: bool,
) -> list[str]:
    if avatar_id:
        targets = [avatar_id]
    elif from_config:
        targets = _live_avatar_ids_from_config()
    else:
        if not os.path.isdir(avatars_root):
            raise SystemExit(f"Avatars root not found: {avatars_root}")
        targets = sorted(
            name
            for name in os.listdir(avatars_root)
            if os.path.isdir(os.path.join(avatars_root, name))
        )

    if skip_complete:
        targets = [t for t in targets if not _avatar_complete(avatars_root, t)]
    return targets


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--avatar-id")
    parser.add_argument(
        "--avatars-root",
        default=os.path.join(ROOT, "data", "avatars"),
    )
    parser.add_argument(
        "--from-config",
        action="store_true",
        help="Only regen model_avatar_id / _ex from config/avatar_config.yaml (live entries)",
    )
    parser.add_argument(
        "--skip-complete",
        action="store_true",
        help="Skip avatars that already have coords.pkl and face_imgs/*.png",
    )
    parser.add_argument("--full-width", type=int, default=DEFAULT_FULL_WIDTH)
    parser.add_argument("--full-height", type=int, default=DEFAULT_FULL_HEIGHT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    pub_w, pub_h = _broadcast_size_from_config()
    print(
        f"Avatar assets: full_imgs {args.full_width}x{args.full_height} | "
        f"Agora broadcast (unchanged): {pub_w}x{pub_h} from config"
    )

    targets = _iter_targets(
        args.avatars_root,
        args.avatar_id,
        from_config=args.from_config,
        skip_complete=args.skip_complete,
    )
    if not targets:
        print("Nothing to regen.")
        return

    missing_video: list[str] = []
    for avatar_id in targets:
        video_rel = AVATAR_VIDEO_MAP.get(avatar_id)
        if not video_rel:
            missing_video.append(avatar_id)
            continue
        video_path = os.path.join(ROOT, video_rel)
        if not os.path.isfile(video_path):
            print(f"SKIP {avatar_id}: video missing: {video_path}", file=sys.stderr)
            missing_video.append(avatar_id)
            continue

        cmd = [
            sys.executable,
            GENAVATAR,
            "--avatar_id",
            avatar_id,
            "--video_path",
            video_path,
            "--full_width",
            str(args.full_width),
            "--full_height",
            str(args.full_height),
        ]
        print(f"REGEN {avatar_id} <- {video_rel}")
        if args.dry_run:
            continue
        env = os.environ.copy()
        env["PYTHONPATH"] = ROOT
        result = subprocess.run(cmd, cwd=ROOT, env=env)
        if result.returncode != 0:
            raise SystemExit(f"genavatar failed for {avatar_id} (exit {result.returncode})")

    if missing_video:
        print(
            "WARNING: no source video mapping for: "
            + ", ".join(sorted(set(missing_video))),
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
