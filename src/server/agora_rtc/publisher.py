"""Agora RTC publisher: push avatar A/V frames into an Agora channel.

Agora Python Server SDK rules (publisher path):
- One AgoraService per process (see init_agora_service / shutdown_agora_service).
- Each publisher owns one RTC connection; release connection on stop, not the service.
- Do not call SDK APIs from SDK observer/callback threads (we push YUV from app threads).
- Raw I420 via VIDEO_PUBLISH_TYPE_YUV + push_video_frame; SDK encodes per SenderOptions.codec_type.
- H264 is the most compatible encode path for mobile/web audience clients.
"""
from __future__ import annotations

import os
import pathlib
import queue
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import cv2
import numpy as np

from src.config.schema import AgoraConfig
from src.server.agora_rtc.codec import (
    effective_publish_codec,
    estimate_video_bitrate_kbps,
    normalize_video_codec,
    resolve_sdk_video_codec_type,
)
from src.server.agora_rtc.token_service import build_rtc_token
from src.utils.logging import logger

_SDK_IMPORT_ERROR: str | None = None
_agora_service = None
_agora_service_app_id: str | None = None
_agora_service_lock = threading.Lock()
_publisher_lifecycle_lock = threading.Lock()
_last_publisher_released_at: float = 0.0
_PUBLISHER_RELEASE_COOLDOWN_SEC = 0.8
_CONNECT_WAIT_SEC = 20.0
_active_publisher: "AgoraRTCPublisher | None" = None


@dataclass(frozen=True, slots=True)
class _AudioOutItem:
    pcm: np.ndarray
    eventpoint: dict | None
    audio_type: int


class _PublisherConnectionObserver:
    """Wait for Agora connect() to finish before publish_audio/publish_video."""

    def __init__(self, channel: str):
        self._channel = channel
        self._connected = threading.Event()
        self._failed = threading.Event()
        self._failure_reason: int | None = None

    def wait_connected(self, timeout: float = _CONNECT_WAIT_SEC) -> bool:
        if self._connected.is_set():
            return True
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            if self._failed.is_set():
                return False
            if self._connected.wait(timeout=min(0.25, deadline - time.perf_counter())):
                return True
        return self._connected.is_set()

    def on_connected(self, agora_rtc_conn, conn_info, reason):
        channel = getattr(conn_info, "channel_id", None) or self._channel
        logger.info(
            "Agora on_connected channel=%s reason=%s local_uid=%s",
            channel,
            reason,
            getattr(conn_info, "local_user_id", "?"),
        )
        self._connected.set()

    def on_connection_failure(self, agora_rtc_conn, info, reason):
        logger.error(
            "Agora on_connection_failure channel=%s reason=%s info=%s",
            self._channel,
            reason,
            info,
        )
        self._failure_reason = reason
        self._failed.set()

    def on_disconnected(self, agora_rtc_conn, conn_info, reason):
        logger.warning(
            "Agora on_disconnected channel=%s reason=%s",
            self._channel,
            reason,
        )
        self._connected.clear()

    def on_error(self, agora_rtc_conn, error_code, error_msg):
        logger.error(
            "Agora connection error channel=%s code=%s msg=%s",
            self._channel,
            error_code,
            error_msg,
        )

    def on_token_privilege_did_expire(self, agora_rtc_conn):
        logger.warning("Agora token expired channel=%s publisher_uid may drop", self._channel)

    def on_user_joined(self, agora_rtc_conn, user_id):
        logger.info("Agora audience joined channel=%s remote_uid=%s", self._channel, user_id)

# Agora ExternalVideoFrame constants (match Agora-Python-Server-SDK examples).
_VIDEO_BUFFER_RAW_DATA = 1
_VIDEO_PIXEL_I420 = 1
_VIDEO_PIXEL_RGBA = 4

# BT.709 (unused when pushing raw I420 without explicit color_space; kept for reference).
_COLOR_PRIMARIES_BT709 = 1
_COLOR_TRANSFER_BT709 = 1
_COLOR_MATRIX_BT709 = 1
_COLOR_RANGE_MPEG = 1


def _sdk_available() -> bool:
    return _SDK_IMPORT_ERROR is None


def _configure_agora_ld_library_path() -> None:
    import importlib.util

    spec = importlib.util.find_spec("agora")
    if not spec or not spec.origin:
        logger.warning("Agora pip package not found while configuring LD_LIBRARY_PATH")
        return
    sdk_dir = pathlib.Path(spec.origin).resolve().parent / "agora_sdk"
    if not sdk_dir.is_dir():
        logger.warning("Agora native SDK directory missing: %s", sdk_dir)
        return
    sdk_str = str(sdk_dir)
    existing = os.environ.get("LD_LIBRARY_PATH", "")
    parts = [p for p in existing.split(":") if p]
    if sdk_str not in parts:
        os.environ["LD_LIBRARY_PATH"] = f"{sdk_str}:{existing}" if existing else sdk_str


def _ensure_sdk():
    global _SDK_IMPORT_ERROR
    if _SDK_IMPORT_ERROR is not None:
        raise RuntimeError(_SDK_IMPORT_ERROR)
    _configure_agora_ld_library_path()
    try:
        import agora.rtc.agora_base  # noqa: F401
    except ImportError as exc:
        import importlib.util

        spec = importlib.util.find_spec("agora")
        origin = getattr(spec, "origin", None) if spec else None
        if origin and "site-packages" not in origin.replace("\\", "/"):
            _SDK_IMPORT_ERROR = (
                f"pip package 'agora' is shadowed by local module at {origin}. "
                "Keep app code under src/server/agora_rtc/, not src/server/agora/."
            )
        else:
            _SDK_IMPORT_ERROR = (
                "agora-python-server-sdk not installed. "
                "Install on Linux/macOS: pip install agora-python-server-sdk"
            )
        logger.error("Agora SDK import failed: %s", exc)
        raise RuntimeError(_SDK_IMPORT_ERROR) from exc
    if sys.platform == "win32":
        _SDK_IMPORT_ERROR = (
            "agora-python-server-sdk does not support Windows. "
            "Run the MinaTalker server on Linux/macOS for Agora RTC publishing."
        )
        logger.error(_SDK_IMPORT_ERROR)
        raise RuntimeError(_SDK_IMPORT_ERROR)


def init_agora_service(app_id: str):
    """Create the process-global AgoraService once (SDK: one instance per process)."""
    global _agora_service, _agora_service_app_id
    app_id = (app_id or "").strip()
    if not app_id:
        raise ValueError("Agora app_id is required to initialize AgoraService")
    _ensure_sdk()
    from agora.rtc.agora_service import AgoraService, AgoraServiceConfig

    with _agora_service_lock:
        if _agora_service is not None:
            if _agora_service_app_id and _agora_service_app_id != app_id:
                logger.warning(
                    "Agora AgoraService already initialized for app_id=%s; ignoring %s",
                    _agora_service_app_id,
                    app_id,
                )
            return _agora_service
        config = AgoraServiceConfig()
        config.appid = app_id
        config.enable_video = 1
        config.log_path = "./agora_rtc_log/agorasdk.log"
        config.log_file_size_kb = 2048
        config.data_dir = "./agora_rtc_log"
        config.config_dir = "./agora_rtc_log"
        service = AgoraService()
        service.initialize(config)
        _agora_service = service
        _agora_service_app_id = app_id
        logger.info("Agora AgoraService initialized (process singleton)")
        return _agora_service


def shutdown_agora_service() -> None:
    """Release the process-global AgoraService (call on process shutdown)."""
    global _agora_service, _agora_service_app_id
    with _agora_service_lock:
        service = _agora_service
        _agora_service = None
        _agora_service_app_id = None
    if service is None:
        return
    try:
        service.release()
        logger.info("Agora AgoraService released")
    except Exception:
        logger.exception("Agora AgoraService release failed")


def _get_agora_service(app_id: str):
    return init_agora_service(app_id)


def _resolve_video_pixel_format() -> str:
    """Return configured pixel format for Agora raw video push."""
    value = (os.environ.get("AGORA_VIDEO_PIXEL_FORMAT") or "i420").strip().lower()
    if value in ("rgba", "bgra"):
        return "rgba"
    return "i420"


def _bgr_to_agora_buffer(bgr_frame: np.ndarray, width: int, height: int, pixel_format: str):
    """Convert lip-sync BGR frame to Agora ExternalVideoFrame buffer."""
    if bgr_frame.dtype != np.uint8:
        bgr_frame = bgr_frame.astype(np.uint8)
    bgr_frame = np.ascontiguousarray(bgr_frame)
    h, w = bgr_frame.shape[:2]
    if w != width or h != height:
        interp = cv2.INTER_AREA if (width * height) < (w * h) else cv2.INTER_LINEAR
        bgr_frame = cv2.resize(bgr_frame, (width, height), interpolation=interp)

    if pixel_format == "i420":
        yuv = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2YUV_I420)
        buf = bytearray(yuv.tobytes())
        expected_len = width * height * 3 // 2
        fmt = _VIDEO_PIXEL_I420
        stride = width
    else:
        rgba = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGBA)
        buf = bytearray(rgba.tobytes())
        expected_len = width * height * 4
        fmt = _VIDEO_PIXEL_RGBA
        stride = width

    if len(buf) != expected_len:
        raise ValueError(
            f"Agora frame buffer size mismatch: got={len(buf)} expected={expected_len} ({width}x{height})"
        )
    return buf, fmt, stride, height


def _even_positive(value: int) -> int:
    n = max(2, int(value))
    if n % 2:
        n -= 1
    return n


def _cap_agora_encode_dimensions(width: int, height: int, *, max_long_edge: int = 1280) -> tuple[int, int]:
    """Cap YUV encode size; Agora server encoder can fail silently at very large portrait sizes."""
    w, h = _even_positive(width), _even_positive(height)
    long_edge = max(w, h)
    if long_edge <= max_long_edge:
        return w, h
    scale = max_long_edge / long_edge
    capped_w = _even_positive(int(w * scale))
    capped_h = _even_positive(int(h * scale))
    logger.warning(
        "Agora encode dimensions capped from %dx%d to %dx%d (max long edge %d)",
        w,
        h,
        capped_w,
        capped_h,
        max_long_edge,
    )
    return capped_w, capped_h


class AgoraRTCPublisher:
    """Broadcaster that feeds process_frames output into Agora RTC."""

    def __init__(
        self,
        agora: AgoraConfig,
        *,
        channel_name: str,
        publisher_uid: int,
        width: int,
        height: int,
        fps: int,
        sample_rate: int = 16000,
        audio_fps: int = 50,
    ):
        self._agora = agora
        self._channel = channel_name
        self._uid = int(publisher_uid)
        self._width, self._height = _cap_agora_encode_dimensions(width, height)
        self._fps = max(1, int(fps))
        self._audio_fps = max(1, int(audio_fps))
        self._sample_rate = int(sample_rate)
        self._video_interval = 1.0 / self._fps
        self._audio_interval = 1.0 / self._audio_fps
        self._video_start: float | None = None
        self._video_frame_count = 0
        self._audio_start: float | None = None
        self._audio_chunk_count = 0
        self._lock = threading.Lock()
        self._pace_lock = threading.Lock()
        self._notify_cb: Optional[Callable] = None
        self._connection = None
        self._started = False
        self._closed = False
        self._video_frames_pushed = 0
        self._audio_chunks_pushed = 0
        self._pixel_format = _resolve_video_pixel_format()
        self._send_silence_audio = bool(getattr(agora, "send_silence_audio", False))
        self._pace_enabled = bool(getattr(agora, "video_pace_enabled", True))
        prewarm = int(getattr(agora, "video_prewarm_fps", 5) or 0)
        self._prewarm_fps = max(0, prewarm)
        self._streaming_active = False
        self._prewarm_stop: threading.Event | None = None
        self._prewarm_thread: threading.Thread | None = None
        out_buf = int(getattr(agora, "video_out_buffer_frames", 3) or 0)
        self._video_out_buffer_frames = max(0, out_buf)
        self._video_out_queue: queue.Queue | None = (
            queue.Queue(maxsize=self._video_out_buffer_frames)
            if self._video_out_buffer_frames > 0
            else None
        )
        self._audio_out_queue: queue.Queue | None = None
        if self._video_out_queue is not None:
            audio_per_video = max(1, self._audio_fps // max(1, self._fps))
            audio_buf = max(4, (self._video_out_buffer_frames + 2) * audio_per_video)
            self._audio_out_queue = queue.Queue(maxsize=audio_buf)
        self._video_out_stop: threading.Event | None = None
        self._video_out_thread: threading.Thread | None = None
        self._last_video_frame: np.ndarray | None = None
        self._video_out_dropped = 0
        self._audio_out_dropped = 0
        self._video_codec = normalize_video_codec(getattr(agora, "video_codec", None))
        self._client_video_codec = effective_publish_codec(
            self._video_codec,
            self._width,
            self._height,
        )
        override_kbps = int(getattr(agora, "video_target_bitrate_kbps", 0) or 0)
        if override_kbps > 0:
            self._target_bitrate_kbps = override_kbps
        else:
            # YUV publish path needs explicit kbps (official SDK examples); 0 often yields hasVideo=false remotely.
            self._target_bitrate_kbps = estimate_video_bitrate_kbps(
                self._width,
                self._height,
                self._fps,
                self._video_codec,
            )
            logger.info(
                "Agora video_target_bitrate_kbps=0; using estimated %dkbps for %dx%d@%dfps",
                self._target_bitrate_kbps,
                self._width,
                self._height,
                self._fps,
            )

    @property
    def is_alive(self) -> bool:
        return bool(self._started and not self._closed and self._connection is not None)

    @property
    def feeds_idle_video_externally(self) -> bool:
        """True while Agora prewarm thread owns idle frame pacing (skip avatar idle push)."""
        return (
            not self._streaming_active
            and self._prewarm_thread is not None
            and self._prewarm_thread.is_alive()
        )

    @property
    def outbound_video_backlog(self) -> int:
        if self._video_out_queue is None:
            return 0
        return self._video_out_queue.qsize()

    @property
    def outbound_audio_backlog(self) -> int:
        if self._audio_out_queue is None:
            return 0
        return self._audio_out_queue.qsize()

    @property
    def video_out_buffer_capacity(self) -> int:
        return self._video_out_buffer_frames

    def _video_out_fps(self) -> int:
        if self._streaming_active:
            return max(1, self._fps)
        return max(1, self._effective_video_fps())

    def _audio_chunks_per_video_frame(self) -> int:
        return max(1, self._audio_fps // max(1, self._video_out_fps()))

    def attach_notify(self, callback: Callable):
        self._notify_cb = callback

    def notify(self, eventpoint: dict):
        if self._notify_cb and eventpoint:
            self._notify_cb(eventpoint)

    def mark_streaming_active(self) -> None:
        """Lip-sync pipeline producing frames; switch from prewarm to full fps pacing."""
        if self._streaming_active:
            return
        self._streaming_active = True
        self._video_start = None
        self._video_frame_count = 0
        self._audio_start = None
        self._audio_chunk_count = 0
        self._last_video_frame = None
        if self._prewarm_stop is not None:
            self._prewarm_stop.set()
        if self._video_out_queue is not None:
            while True:
                try:
                    self._video_out_queue.get_nowait()
                except queue.Empty:
                    break
        if self._audio_out_queue is not None:
            while True:
                try:
                    self._audio_out_queue.get_nowait()
                except queue.Empty:
                    break
        logger.info(
            "Agora video pacing prewarm@%dfps -> %dfps channel=%s",
            self._prewarm_fps or self._fps,
            self._fps,
            self._channel,
        )

    def _effective_video_fps(self) -> int:
        if self._streaming_active or self._prewarm_fps <= 0:
            return self._fps
        return min(self._fps, self._prewarm_fps)

    def push_idle_startup(self, frames) -> None:
        """Steady paced idle video until lip-sync marks active (Agora CC-friendly)."""
        cycle = list(frames) if frames is not None else []
        if not cycle:
            logger.warning("Agora push_idle_startup skipped: no idle frames channel=%s", self._channel)
            return
        if self._streaming_active:
            self.push_video(cycle[0], paced=True)
            return
        self._video_start = None
        self._video_frame_count = 0
        self.push_video(cycle[0], paced=True)
        logger.info(
            "Agora idle startup channel=%s (%dx%d @%dfps prewarm)",
            self._channel,
            self._width,
            self._height,
            self._effective_video_fps(),
        )
        self.start_idle_prewarm(cycle)

    def start_idle_prewarm(self, frames) -> None:
        """Background idle frames at video_prewarm_fps until lip-sync marks active."""
        if self._prewarm_fps <= 0 or not frames:
            return
        if self._prewarm_thread is not None and self._prewarm_thread.is_alive():
            return
        cycle = list(frames)
        if not cycle:
            return
        stop = threading.Event()
        self._prewarm_stop = stop
        length = len(cycle)
        idx = 0

        def _mirror_index(size: int, index: int) -> int:
            turn = index // size
            res = index % size
            return res if turn % 2 == 0 else size - res - 1

        def _loop() -> None:
            nonlocal idx
            interval = 1.0 / self._prewarm_fps
            logger.info(
                "Agora idle prewarm started channel=%s @%dfps",
                self._channel,
                self._prewarm_fps,
            )
            while not stop.is_set() and not self._closed and not self._streaming_active:
                frame = cycle[_mirror_index(length, idx)]
                idx += 1
                self.push_video(frame, paced=True)
                if self._video_out_queue is not None or not self._pace_enabled:
                    if stop.wait(interval):
                        break
            logger.info("Agora idle prewarm stopped channel=%s", self._channel)

        self._prewarm_thread = threading.Thread(
            name=f"agora-prewarm-{self._channel}",
            target=_loop,
            daemon=True,
        )
        self._prewarm_thread.start()

    def start(self):
        if self._started:
            return
        global _active_publisher, _last_publisher_released_at
        with _publisher_lifecycle_lock:
            prev = _active_publisher
            if prev is not None and prev is not self and prev.is_alive:
                logger.warning(
                    "Agora stopping previous publisher on channel=%s before new channel=%s",
                    getattr(prev, "_channel", "?"),
                    self._channel,
                )
                prev.stop()
            elapsed = time.perf_counter() - _last_publisher_released_at
            if elapsed < _PUBLISHER_RELEASE_COOLDOWN_SEC:
                time.sleep(_PUBLISHER_RELEASE_COOLDOWN_SEC - elapsed)
        _ensure_sdk()
        from agora.rtc.agora_base import (
            AudioProfileType,
            AudioPublishType,
            AudioScenarioType,
            AudioSubscriptionOptions,
            ChannelProfileType,
            ClientRoleType,
            RtcConnectionPublishConfig,
            RTCConnConfig,
            SenderOptions,
            TCcMode,
            VideoDimensions,
            VideoEncoderConfiguration,
            VideoPublishType,
        )
        from agora.rtc.rtc_connection_observer import IRTCConnectionObserver
        from agora.rtc.video_frame_sender import ExternalVideoFrame

        self._ExternalVideoFrame = ExternalVideoFrame

        class _ConnObserver(_PublisherConnectionObserver, IRTCConnectionObserver):
            pass

        app_id = (self._agora.app_id or "").strip()
        token = build_rtc_token(
            self._agora,
            channel_name=self._channel,
            uid=self._uid,
            role="publisher",
        ) or ""

        sub_opt = AudioSubscriptionOptions(
            packet_only=0,
            pcm_data_only=1,
            bytes_per_sample=2,
            number_of_channels=1,
            sample_rate_hz=self._sample_rate,
        )
        con_config = RTCConnConfig(
            auto_subscribe_audio=0,
            auto_subscribe_video=0,
            client_role_type=ClientRoleType.CLIENT_ROLE_BROADCASTER,
            channel_profile=ChannelProfileType.CHANNEL_PROFILE_LIVE_BROADCASTING,
            audio_recv_media_packet=0,
            audio_subs_options=sub_opt,
            enable_audio_recording_or_playout=0,
        )
        publish_config = RtcConnectionPublishConfig(
            audio_profile=AudioProfileType.AUDIO_PROFILE_DEFAULT,
            audio_scenario=AudioScenarioType.AUDIO_SCENARIO_AI_SERVER,
            audio_publish_type=AudioPublishType.AUDIO_PUBLISH_TYPE_PCM,
            video_publish_type=VideoPublishType.VIDEO_PUBLISH_TYPE_YUV,
            is_publish_audio=True,
            is_publish_video=True,
            video_encoded_image_sender_options=SenderOptions(
                target_bitrate=self._target_bitrate_kbps,
                cc_mode=TCcMode.CC_ENABLED,
                codec_type=resolve_sdk_video_codec_type(self._client_video_codec),
            ),
        )

        service = _get_agora_service(app_id)
        connection = service.create_rtc_connection(con_config, publish_config)
        conn_observer = _ConnObserver(self._channel)
        reg_ret = connection.register_observer(conn_observer)
        if reg_ret != 0:
            logger.warning("Agora register_observer returned %s channel=%s", reg_ret, self._channel)
        ret = connection.connect(token, self._channel, str(self._uid))
        if ret != 0:
            connection.release()
            raise RuntimeError(f"Agora connect failed with code {ret}")
        if not conn_observer.wait_connected():
            reason = conn_observer._failure_reason
            connection.release()
            raise RuntimeError(
                f"Agora connect timed out or failed channel={self._channel} reason={reason}"
            )
        enc_config = VideoEncoderConfiguration(
            dimensions=VideoDimensions(width=self._width, height=self._height),
            codec_type=resolve_sdk_video_codec_type(self._client_video_codec),
            frame_rate=max(1, int(self._fps)),
            bitrate=int(self._target_bitrate_kbps),
            min_bitrate=max(800, int(self._target_bitrate_kbps // 3)),
        )
        enc_ret = connection.set_video_encoder_configuration(enc_config)
        if enc_ret != 0:
            logger.warning(
                "Agora set_video_encoder_configuration returned %s channel=%s %dx%d@%dfps bitrate=%dkbps",
                enc_ret,
                self._channel,
                self._width,
                self._height,
                self._fps,
                self._target_bitrate_kbps,
            )
        self._connection = connection
        prime_ret = self._prime_video_track(connection)
        if prime_ret != 0:
            logger.warning(
                "Agora pre-publish video prime returned %s channel=%s",
                prime_ret,
                self._channel,
            )
        video_ret = connection.publish_video()
        audio_ret = connection.publish_audio()
        if audio_ret != 0:
            logger.warning("Agora publish_audio returned %s channel=%s", audio_ret, self._channel)
        if video_ret != 0:
            logger.warning("Agora publish_video returned %s channel=%s", video_ret, self._channel)
        else:
            logger.info(
                "Agora publish_video ok channel=%s uid=%s encoder=%dx%d@%dfps codec=%s",
                self._channel,
                self._uid,
                self._width,
                self._height,
                self._fps,
                self._client_video_codec,
            )
        from agora.rtc.video_encoded_frame_observer import IVideoEncodedFrameObserver

        class _EncodedVideoObserver(IVideoEncodedFrameObserver):
            def __init__(self, channel: str):
                self._channel = channel
                self._count = 0

            def on_encoded_video_frame(self, uid, image_buffer, length, video_encoded_frame_info):
                self._count += 1
                if self._count <= 5 or self._count % 250 == 0:
                    info = video_encoded_frame_info
                    logger.info(
                        "Agora encoded video frame #%d channel=%s len=%s %sx%s fps=%s frame_type=%s",
                        self._count,
                        self._channel,
                        length,
                        getattr(info, "width", "?"),
                        getattr(info, "height", "?"),
                        getattr(info, "frames_per_second", "?"),
                        getattr(info, "frame_type", "?"),
                    )

        enc_obs = _EncodedVideoObserver(self._channel)
        enc_reg = connection.register_video_encoded_frame_observer(enc_obs)
        if enc_reg != 0:
            logger.warning(
                "Agora register_video_encoded_frame_observer returned %s channel=%s",
                enc_reg,
                self._channel,
            )
        self._connection = connection
        self._started = True
        self._start_video_out_thread()
        with _publisher_lifecycle_lock:
            _active_publisher = self
        bitrate_log = (
            f"{self._target_bitrate_kbps}kbps"
            if self._target_bitrate_kbps > 0
            else (
                f"standard/auto (~{estimate_video_bitrate_kbps(self._width, self._height, self._fps, self._video_codec)}kbps est.)"
            )
        )
        logger.info(
            "Agora publisher joined channel=%s uid=%s (%dx%d@%dfps audio@%dfps "
            "encode=%s client_codec=%s bitrate=%s pixel=%s cc=enabled)",
            self._channel,
            self._uid,
            self._width,
            self._height,
            self._fps,
            self._audio_fps,
            self._video_codec,
            self._client_video_codec,
            bitrate_log,
            self._pixel_format,
        )

    def _start_video_out_thread(self) -> None:
        if self._video_out_queue is None or self._video_out_thread is not None:
            return
        stop = threading.Event()
        self._video_out_stop = stop

        def _loop() -> None:
            next_tick = time.perf_counter()
            logger.info(
                "Agora AV out thread started channel=%s video_buf=%d @%dfps audio=%d/video_tick",
                self._channel,
                self._video_out_buffer_frames,
                self._fps,
                self._audio_chunks_per_video_frame(),
            )
            while not stop.is_set():
                fps = self._video_out_fps()
                interval = 1.0 / fps
                now = time.perf_counter()
                if now < next_tick:
                    if stop.wait(next_tick - now):
                        break
                    now = time.perf_counter()

                # Never burst-send to catch up; drop stale queue and resync the clock.
                if now - next_tick >= interval:
                    keep = 1 if self._streaming_active else 0
                    dropped = self._drop_stale_video_queue_frames(max_keep=keep)
                    if dropped:
                        audio_dropped = self._drop_paired_audio_for_video_frames(dropped)
                        logger.warning(
                            "Agora AV out behind schedule; dropped video=%d audio=%d "
                            "channel=%s streaming=%s",
                            dropped,
                            audio_dropped,
                            self._channel,
                            self._streaming_active,
                        )
                    next_tick = now

                with self._lock:
                    if self._closed or not self._started:
                        break
                    conn = self._connection
                    if conn is None:
                        continue
                    if self._closed or self._connection is not conn:
                        continue
                    if self._streaming_active:
                        self._send_streaming_av_tick(conn, fps)
                    else:
                        frame = self._dequeue_video_for_send()
                        if frame is not None:
                            self._send_video_frame(conn, frame)
                        self._send_audio_chunks_for_video_tick(conn, fps)

                next_tick += interval
            dropped = self._video_out_dropped
            if dropped:
                logger.warning(
                    "Agora video out thread stopped channel=%s (dropped_frames=%d)",
                    self._channel,
                    dropped,
                )
            else:
                logger.info("Agora video out thread stopped channel=%s", self._channel)

        self._video_out_thread = threading.Thread(
            name=f"agora-video-out-{self._channel}",
            target=_loop,
            daemon=True,
        )
        self._video_out_thread.start()

    def _stop_video_out_thread(self) -> None:
        if self._video_out_stop is not None:
            self._video_out_stop.set()
        if self._video_out_thread is not None:
            self._video_out_thread.join(timeout=2.0)
            self._video_out_thread = None
        self._video_out_stop = None
        if self._video_out_queue is not None:
            while True:
                try:
                    self._video_out_queue.get_nowait()
                except queue.Empty:
                    break
        if self._audio_out_queue is not None:
            while True:
                try:
                    self._audio_out_queue.get_nowait()
                except queue.Empty:
                    break

    def _enqueue_video_frame(self, bgr_frame: np.ndarray) -> None:
        assert self._video_out_queue is not None
        item = bgr_frame.copy()
        if self._streaming_active:
            deadline = time.perf_counter() + 2.0
            while not self._closed:
                try:
                    self._video_out_queue.put(item, block=True, timeout=0.05)
                    return
                except queue.Full:
                    if time.perf_counter() >= deadline:
                        self._video_out_dropped += 1
                        logger.warning(
                            "Agora video out queue backpressure timeout; dropped frame "
                            "channel=%s qsize=%d total_dropped=%d",
                            self._channel,
                            self._video_out_queue.qsize(),
                            self._video_out_dropped,
                        )
                        return
            return
        try:
            self._video_out_queue.put_nowait(item)
        except queue.Full:
            try:
                self._video_out_queue.get_nowait()
                self._video_out_dropped += 1
                if self._video_out_dropped in (1, 10) or self._video_out_dropped % 100 == 0:
                    logger.warning(
                        "Agora video out queue full; dropped oldest idle frame channel=%s total_dropped=%d",
                        self._channel,
                        self._video_out_dropped,
                    )
            except queue.Empty:
                logger.warning(
                    "Agora video out queue full but empty on drop channel=%s",
                    self._channel,
                )
            try:
                self._video_out_queue.put_nowait(item)
            except queue.Full:
                logger.warning(
                    "Agora video out queue still full after drop channel=%s",
                    self._channel,
                )

    def _drop_stale_video_queue_frames(self, *, max_keep: int = 0) -> int:
        """Drop queued frames when the out thread fell behind (avoid burst playback)."""
        assert self._video_out_queue is not None
        q = self._video_out_queue
        dropped = 0
        while q.qsize() > max(0, max_keep):
            try:
                q.get_nowait()
                dropped += 1
            except queue.Empty:
                break
        if dropped:
            self._video_out_dropped += dropped
        return dropped

    def _drop_paired_audio_for_video_frames(self, video_frames: int) -> int:
        if video_frames <= 0 or self._audio_out_queue is None:
            return 0
        return self._drop_stale_audio_queue_frames(
            video_frames * self._audio_chunks_per_video_frame()
        )

    def _dequeue_video_for_send(self) -> np.ndarray | None:
        assert self._video_out_queue is not None
        q = self._video_out_queue
        max_lag = self._video_out_buffer_frames + 2
        while q.qsize() > max_lag:
            try:
                q.get_nowait()
                self._video_out_dropped += 1
                if self._streaming_active:
                    self._drop_paired_audio_for_video_frames(1)
            except queue.Empty:
                break
        frame = None
        try:
            frame = q.get_nowait()
        except queue.Empty:
            pass
        if frame is not None:
            self._last_video_frame = frame
            return frame
        if self._streaming_active:
            return None
        return self._last_video_frame

    def _send_streaming_av_tick(self, conn, video_fps: int) -> None:
        """Send one lip-sync video frame and its paired audio chunks (no stale video hold)."""
        frame = self._dequeue_video_for_send()
        if frame is None:
            if self._audio_out_queue is not None:
                pending = self._audio_out_queue.qsize()
                if pending:
                    dropped = self._drop_stale_audio_queue_frames(pending)
                    logger.warning(
                        "Agora lip-sync stall: no fresh video frame; dropped %d orphaned "
                        "audio chunk(s) channel=%s",
                        dropped,
                        self._channel,
                    )
            return
        chunks = max(1, self._audio_fps // max(1, video_fps))
        audio_items = self._dequeue_audio_chunks_for_send(chunks)
        if len(audio_items) < chunks:
            logger.warning(
                "Agora lip-sync skew: got %d/%d audio chunk(s) for video frame channel=%s",
                len(audio_items),
                chunks,
                self._channel,
            )
        self._send_video_frame(conn, frame)
        for item in audio_items:
            self._send_audio_item(conn, item)

    def _enqueue_audio_item(self, item: _AudioOutItem) -> None:
        assert self._audio_out_queue is not None
        if self._streaming_active:
            deadline = time.perf_counter() + 2.0
            while not self._closed:
                try:
                    self._audio_out_queue.put(item, block=True, timeout=0.05)
                    return
                except queue.Full:
                    if time.perf_counter() >= deadline:
                        self._audio_out_dropped += 1
                        logger.warning(
                            "Agora audio out queue backpressure timeout; dropped chunk "
                            "channel=%s qsize=%d total_dropped=%d",
                            self._channel,
                            self._audio_out_queue.qsize(),
                            self._audio_out_dropped,
                        )
                        return
            return
        try:
            self._audio_out_queue.put_nowait(item)
        except queue.Full:
            try:
                self._audio_out_queue.get_nowait()
                self._audio_out_dropped += 1
                if self._audio_out_dropped in (1, 10) or self._audio_out_dropped % 100 == 0:
                    logger.warning(
                        "Agora audio out queue full; dropped oldest idle chunk channel=%s total_dropped=%d",
                        self._channel,
                        self._audio_out_dropped,
                    )
            except queue.Empty:
                logger.warning(
                    "Agora audio out queue full but empty on drop channel=%s",
                    self._channel,
                )
            try:
                self._audio_out_queue.put_nowait(item)
            except queue.Full:
                logger.warning(
                    "Agora audio out queue still full after drop channel=%s",
                    self._channel,
                )

    def _drop_stale_audio_queue_frames(self, count: int) -> int:
        if self._audio_out_queue is None or count <= 0:
            return 0
        dropped = 0
        for _ in range(count):
            try:
                self._audio_out_queue.get_nowait()
                dropped += 1
                self._audio_out_dropped += 1
            except queue.Empty:
                break
        return dropped

    def _dequeue_audio_chunks_for_send(self, count: int) -> list[_AudioOutItem]:
        assert self._audio_out_queue is not None
        q = self._audio_out_queue
        max_lag = (self._video_out_buffer_frames + 2) * self._audio_chunks_per_video_frame()
        while q.qsize() > max_lag:
            try:
                q.get_nowait()
                self._audio_out_dropped += 1
                if self._streaming_active and self._audio_out_dropped in (1, 10, 100):
                    logger.warning(
                        "Agora audio queue overflow trim during lip-sync channel=%s qsize=%d",
                        self._channel,
                        q.qsize(),
                    )
            except queue.Empty:
                break
        items: list[_AudioOutItem] = []
        for _ in range(count):
            try:
                items.append(q.get_nowait())
            except queue.Empty:
                break
        return items

    def _send_audio_chunks_for_video_tick(self, conn, video_fps: int) -> None:
        if self._audio_out_queue is None:
            return
        chunks = max(1, self._audio_fps // max(1, video_fps))
        for item in self._dequeue_audio_chunks_for_send(chunks):
            self._send_audio_item(conn, item)

    def _send_audio_item(self, conn, item: _AudioOutItem) -> int:
        if item.audio_type == 1 and not self._send_silence_audio:
            return 0
        pcm_int16 = item.pcm
        if pcm_int16 is None or pcm_int16.size == 0:
            return 0
        if item.eventpoint:
            self.notify(item.eventpoint)
        try:
            if pcm_int16.dtype != np.int16:
                pcm_int16 = pcm_int16.astype(np.int16)
            pcm = np.ascontiguousarray(pcm_int16)
            ret = conn.push_audio_pcm_data(
                bytearray(pcm.tobytes()),
                self._sample_rate,
                1,
            )
        except Exception as exc:
            logger.warning(
                "Agora push_audio_pcm_data failed channel=%s: %s",
                self._channel,
                exc,
            )
            return -1
        if ret != 0:
            logger.warning("Agora push_audio_pcm_data returned %s", ret)
            return ret
        self._audio_chunks_pushed += 1
        if self._audio_chunks_pushed == 1:
            logger.info("Agora first audio chunk pushed channel=%s", self._channel)
        return 0

    def _video_pace_wait_sec(self) -> float:
        """Seconds to sleep before next video frame (0 = send now / catch up)."""
        if self._video_out_queue is not None:
            return 0.0
        if not self._pace_enabled:
            return 0.0
        # Lip-sync: ship frames as soon as Wav2Lip produces them; pacing added lag on top of batch inference delay.
        if self._streaming_active:
            return 0.0
        with self._pace_lock:
            fps = self._effective_video_fps()
            interval = 1.0 / max(1, fps)
            now = time.perf_counter()
            if self._video_start is None:
                self._video_start = now
                self._video_frame_count = 0
                return 0.0
            self._video_frame_count += 1
            return max(0.0, self._video_start + self._video_frame_count * interval - now)

    def _audio_pace_wait_sec(self) -> float:
        if self._audio_out_queue is not None:
            return 0.0
        with self._pace_lock:
            now = time.perf_counter()
            if self._audio_start is None:
                self._audio_start = now
                self._audio_chunk_count = 0
                return 0.0
            self._audio_chunk_count += 1
            return max(0.0, self._audio_start + self._audio_chunk_count * self._audio_interval - now)

    def _prime_video_track(self, conn) -> int:
        """Push a few YUV frames before publish_video (Agora YUV send examples)."""
        blank = np.zeros((self._height, self._width, 3), dtype=np.uint8)
        last_ret = 0
        for i in range(3):
            last_ret = self._send_video_frame(conn, blank, log_first=(i == 0))
            if last_ret != 0:
                logger.warning(
                    "Agora pre-publish prime frame %d returned %s channel=%s",
                    i + 1,
                    last_ret,
                    self._channel,
                )
                break
        return last_ret

    def _send_video_frame(self, conn, bgr_frame: np.ndarray, *, log_first: bool = False) -> int:
        try:
            buf, fmt, stride, height = _bgr_to_agora_buffer(
                bgr_frame,
                self._width,
                self._height,
                self._pixel_format,
            )
        except Exception:
            logger.exception("Agora push_video frame conversion failed")
            return -1
        frame = self._ExternalVideoFrame()
        frame.type = _VIDEO_BUFFER_RAW_DATA
        frame.format = fmt
        frame.buffer = buf
        frame.stride = stride
        frame.height = height
        # Official YUV examples pass 0; SDK assigns capture timestamps.
        frame.timestamp = 0
        frame.metadata = bytearray()
        try:
            ret = conn.push_video_frame(frame)
        except Exception as exc:
            logger.warning(
                "Agora push_video_frame failed channel=%s: %s",
                self._channel,
                exc,
            )
            return -1
        if ret != 0:
            logger.warning("Agora push_video_frame returned %s", ret)
            return ret
        self._video_frames_pushed += 1
        if log_first or self._video_frames_pushed == 1:
            logger.info(
                "Agora video frame pushed channel=%s (%dx%d pixel=%s ts=auto)",
                self._channel,
                self._width,
                self._height,
                self._pixel_format,
            )
        return 0

    def push_video(self, bgr_frame: np.ndarray, *, paced: bool = True):
        if bgr_frame is None or bgr_frame.size == 0:
            logger.warning("Agora push_video skipped empty frame")
            return
        if self._video_out_queue is not None:
            self._enqueue_video_frame(bgr_frame)
            return
        if paced:
            wait = self._video_pace_wait_sec()
            if wait > 0:
                time.sleep(wait)
        with self._lock:
            if self._closed or not self._started:
                return
            conn = self._connection
            if conn is None:
                return
            if self._closed or self._connection is not conn:
                return
            ret = self._send_video_frame(conn, bgr_frame)
            if ret != 0:
                return

    def push_audio(
        self,
        pcm_int16: np.ndarray,
        eventpoint: dict | None = None,
        *,
        audio_type: int = 0,
    ):
        # audio_type 1 = pipeline idle silence (zeros); 0 = speech; >1 = custom audio
        if audio_type == 1 and not self._send_silence_audio:
            return
        if pcm_int16 is None or pcm_int16.size == 0:
            return
        if self._audio_out_queue is not None:
            self._enqueue_audio_item(
                _AudioOutItem(
                    pcm=pcm_int16.copy(),
                    eventpoint=eventpoint,
                    audio_type=audio_type,
                )
            )
            return
        if eventpoint:
            self.notify(eventpoint)
        wait = self._audio_pace_wait_sec()
        if wait > 0:
            time.sleep(wait)
        with self._lock:
            if self._closed or not self._started:
                return
            conn = self._connection
            if conn is None:
                return
            if self._closed or self._connection is not conn:
                return
            self._send_audio_item(
                conn,
                _AudioOutItem(
                    pcm=pcm_int16,
                    eventpoint=None,
                    audio_type=audio_type,
                ),
            )

    def stop(self):
        if self._closed:
            return
        global _active_publisher, _last_publisher_released_at
        if self._prewarm_stop is not None:
            self._prewarm_stop.set()
        if self._prewarm_thread is not None:
            self._prewarm_thread.join(timeout=2)
            self._prewarm_thread = None
        self._stop_video_out_thread()
        with self._lock:
            self._closed = True
            self._started = False
            conn = self._connection
            self._connection = None
        if conn is not None:
            try:
                conn.disconnect()
            except Exception:
                logger.exception("Agora disconnect failed")
            try:
                conn.release()
            except Exception:
                logger.exception("Agora connection release failed")
        logger.info(
            "Agora publisher stopped channel=%s uid=%s (video_frames=%d audio_chunks=%d)",
            self._channel,
            self._uid,
            self._video_frames_pushed,
            self._audio_chunks_pushed,
        )
        with _publisher_lifecycle_lock:
            if _active_publisher is self:
                _active_publisher = None
            _last_publisher_released_at = time.perf_counter()
