"""Agora RTC publisher: push avatar A/V frames into an Agora channel."""
from __future__ import annotations

import sys
import threading
from typing import Callable, Optional

import cv2
import numpy as np

from src.config.schema import AgoraConfig
from src.server.agora.token_service import build_rtc_token
from src.utils.logging import logger

_SDK_IMPORT_ERROR: str | None = None
_agora_service = None
_agora_service_lock = threading.Lock()


def _sdk_available() -> bool:
    return _SDK_IMPORT_ERROR is None


def _ensure_sdk():
    global _SDK_IMPORT_ERROR
    if _SDK_IMPORT_ERROR is not None:
        raise RuntimeError(_SDK_IMPORT_ERROR)
    try:
        import agora.rtc.agora_base  # noqa: F401
    except ImportError as exc:
        _SDK_IMPORT_ERROR = (
            "agora-python-server-sdk not installed. "
            "Install on Linux/macOS: pip install agora-python-server-sdk"
        )
        logger.error(_SDK_IMPORT_ERROR)
        raise RuntimeError(_SDK_IMPORT_ERROR) from exc
    if sys.platform == "win32":
        _SDK_IMPORT_ERROR = (
            "agora-python-server-sdk does not support Windows. "
            "Run the MinaTalker server on Linux/macOS for Agora RTC publishing."
        )
        logger.error(_SDK_IMPORT_ERROR)
        raise RuntimeError(_SDK_IMPORT_ERROR)


def _get_agora_service(app_id: str):
    global _agora_service
    _ensure_sdk()
    from agora.rtc.agora_service import AgoraService, AgoraServiceConfig

    with _agora_service_lock:
        if _agora_service is not None:
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
        logger.info("Agora AgoraService initialized")
        return _agora_service


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
    ):
        self._agora = agora
        self._channel = channel_name
        self._uid = int(publisher_uid)
        self._width = max(2, int(width))
        self._height = max(2, int(height))
        self._fps = max(1, int(fps))
        self._sample_rate = int(sample_rate)
        self._video_interval = 1.0 / self._fps
        self._video_ts = 0
        self._lock = threading.Lock()
        self._notify_cb: Optional[Callable] = None
        self._connection = None
        self._started = False
        self._closed = False

    def attach_notify(self, callback: Callable):
        self._notify_cb = callback

    def notify(self, eventpoint: dict):
        if self._notify_cb and eventpoint:
            self._notify_cb(eventpoint)

    def start(self):
        if self._started:
            return
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
            VideoCodecType,
            VideoPublishType,
        )
        from agora.rtc.video_frame_sender import ExternalVideoFrame

        self._ExternalVideoFrame = ExternalVideoFrame

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
                target_bitrate=2500,
                cc_mode=TCcMode.CC_ENABLED,
                codec_type=VideoCodecType.VIDEO_CODEC_H264,
            ),
        )

        service = _get_agora_service(app_id)
        connection = service.create_rtc_connection(con_config, publish_config)
        ret = connection.connect(token, self._channel, str(self._uid))
        if ret != 0:
            connection.release()
            raise RuntimeError(f"Agora connect failed with code {ret}")
        connection.publish_audio()
        connection.publish_video()
        self._connection = connection
        self._started = True
        logger.info(
            "Agora publisher joined channel=%s uid=%s (%dx%d@%dfps)",
            self._channel,
            self._uid,
            self._width,
            self._height,
            self._fps,
        )

    def push_video(self, bgr_frame: np.ndarray):
        if self._closed or not self._started or self._connection is None:
            return
        with self._lock:
            h, w = bgr_frame.shape[:2]
            if w != self._width or h != self._height:
                bgr_frame = cv2.resize(bgr_frame, (self._width, self._height))
            yuv = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2YUV_I420)
            frame = self._ExternalVideoFrame()
            frame.buffer = bytearray(yuv.tobytes())
            frame.type = 1
            frame.format = 1
            frame.stride = self._width
            frame.height = self._height
            frame.timestamp = self._video_ts
            frame.metadata = bytearray()
            self._video_ts += int(90000 / self._fps)
            try:
                self._connection.push_video_frame(frame)
            except Exception:
                logger.exception("Agora push_video_frame failed")

    def push_audio(self, pcm_int16: np.ndarray, eventpoint: dict | None = None):
        if eventpoint:
            self.notify(eventpoint)
        if self._closed or not self._started or self._connection is None:
            return
        if pcm_int16 is None or pcm_int16.size == 0:
            return
        with self._lock:
            try:
                self._connection.push_audio_pcm_data(
                    pcm_int16.tobytes(),
                    self._sample_rate,
                    1,
                )
            except Exception:
                logger.exception("Agora push_audio_pcm_data failed")

    def stop(self):
        if self._closed:
            return
        self._closed = True
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
        logger.info("Agora publisher stopped channel=%s uid=%s", self._channel, self._uid)
