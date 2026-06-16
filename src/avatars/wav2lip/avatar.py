# Linly-Talker-Stream (https://github.com/Kedreamix/Linly-Talker-Stream). Copyright [Linly-talker-stream@kedreamix]. Apache-2.0.
# Based on LiveTalking (C) 2024 LiveTalking@lipku https://github.com/lipku/LiveTalking (Apache-2.0).

import math
import torch
import numpy as np

#from .utils import *
import os
import time
import cv2
import glob
import pickle
import copy

import queue
from queue import Queue
from threading import Thread, Event
import torch.multiprocessing as mp


from src.avatars.wav2lip.audio_stream_handler import LipAudioStreamHandler
import asyncio
from av import AudioFrame, VideoFrame
from src.avatars.wav2lip.models import Wav2Lip
from src.avatars.wav2lip.gfpgan_enhancer import GPU_INFER_LOCK, build_gfpgan_enhancer
from src.avatars.base import BaseAvatar

#from imgcache import ImgCache

from src.utils.logging import logger
from src.utils.png_io import read_imgs

device = "cuda" if torch.cuda.is_available() else ("mps" if (hasattr(torch.backends, "mps") and torch.backends.mps.is_available()) else "cpu")

# Wav2Lip v2 checkpoint in ./models/wav2lip.pth; must match warm_up() spatial size in prepare_avatar_model.
WAV2LIP_FACE_SIZE = 256
print('Using {} for inference.'.format(device))


def _infer_dtype(use_fp16: bool) -> torch.dtype:
    return torch.float16 if use_fp16 and device == "cuda" else torch.float32


def _wav2lip_cfg(config):
    if config is None:
        return None
    return getattr(getattr(config, "model", None), "wav2lip", None)


def _use_fp16(config) -> bool:
    wav2lip_cfg = _wav2lip_cfg(config)
    return bool(getattr(wav2lip_cfg, "fp16", False)) and device == "cuda"

# In-process cache for avatar assets: avatar_id -> (frame_list, face_list, coord_list)
_AVATAR_CACHE = {}

def _load(checkpoint_path):
	# weights_only=True: safe for state_dict checkpoints; silences FutureWarning
	kwargs = {"weights_only": True}
	if device != "cuda":
		kwargs["map_location"] = lambda storage, loc: storage
	checkpoint = torch.load(checkpoint_path, **kwargs)
	return checkpoint

def _load_pytorch_model(path, *, use_fp16: bool):
	model = Wav2Lip()
	logger.info("Load checkpoint from: %s", path)
	checkpoint = _load(path)
	s = checkpoint["state_dict"]
	new_s = {}
	for k, v in s.items():
		new_s[k.replace('module.', '')] = v
	model.load_state_dict(new_s)

	model = model.to(device).eval()
	if use_fp16:
		model = model.half()
		logger.info("Wav2Lip model loaded in FP16")
	return model


def load_model(path, config=None, batch_size=None):
	wav2lip_cfg = _wav2lip_cfg(config)
	backend = getattr(wav2lip_cfg, "backend", "pytorch") if wav2lip_cfg else "pytorch"
	use_fp16 = _use_fp16(config)

	if backend == "tensorrt":
		from src.avatars.wav2lip.trt_runner import Wav2LipTensorRTModel, default_onnx_path

		if batch_size is None and config is not None:
			batch_size = int(getattr(config.model, "batch_size", 4) or 4)
		if batch_size is None:
			batch_size = 4
		onnx_path = getattr(wav2lip_cfg, "onnx_path", "") if wav2lip_cfg else ""
		if not onnx_path:
			models_dir = getattr(config.model, "model_path", "./models") if config else "./models"
			onnx_path = default_onnx_path(
				batch_size=batch_size,
				face_size=WAV2LIP_FACE_SIZE,
				models_dir=models_dir,
			)
		trt_cache = getattr(wav2lip_cfg, "trt_cache_path", "./models/trt_cache") if wav2lip_cfg else "./models/trt_cache"
		trt_fp16 = bool(getattr(wav2lip_cfg, "trt_fp16", True)) if wav2lip_cfg else True
		return Wav2LipTensorRTModel.load(
			onnx_path,
			trt_cache_path=trt_cache,
			trt_fp16=trt_fp16,
			device=device,
		)

	return _load_pytorch_model(path, use_fp16=use_fp16)

def load_avatar(avatar_id):
    # Return from cache if already loaded
    cached = _AVATAR_CACHE.get(avatar_id)
    if cached is not None:
        return cached

    avatar_path = f"./data/avatars/{avatar_id}"
    full_imgs_path = f"{avatar_path}/full_imgs" 
    face_imgs_path = f"{avatar_path}/face_imgs" 
    coords_path = f"{avatar_path}/coords.pkl"
    
    with open(coords_path, 'rb') as f:
        coord_list_cycle = pickle.load(f)
    input_img_list = glob.glob(os.path.join(full_imgs_path, '*.[jpJP][pnPN]*[gG]'))
    input_img_list = sorted(input_img_list, key=lambda x: int(os.path.splitext(os.path.basename(x))[0]))
    frame_list_cycle = read_imgs(input_img_list)
    #self.imagecache = ImgCache(len(self.coord_list_cycle),self.full_imgs_path,1000)
    input_face_list = glob.glob(os.path.join(face_imgs_path, '*.[jpJP][pnPN]*[gG]'))
    input_face_list = sorted(input_face_list, key=lambda x: int(os.path.splitext(os.path.basename(x))[0]))
    face_list_cycle = read_imgs(input_face_list)

    avatar_data = (frame_list_cycle, face_list_cycle, coord_list_cycle)
    _AVATAR_CACHE[avatar_id] = avatar_data
    return avatar_data


def preload_avatars(avatar_ids):
    """
    Preload avatar assets into memory for the given ids.
    Safe to call multiple times; already-cached ids are skipped.
    """
    for avatar_id in avatar_ids:
        if not isinstance(avatar_id, str) or not avatar_id:
            continue
        if avatar_id in _AVATAR_CACHE:
            continue
        try:
            logger.info("Preloading Wav2Lip avatar assets: %s", avatar_id)
            load_avatar(avatar_id)
        except Exception:
            logger.exception("Failed to preload Wav2Lip avatar %s", avatar_id)

@torch.no_grad()
def warm_up(batch_size, model, modelres):
    # 预热函数
    logger.info('warmup model...')
    try:
        dtype = next(model.parameters()).dtype
    except (StopIteration, AttributeError):
        dtype = torch.float32
    img_batch = torch.ones(batch_size, 6, modelres, modelres, device=device, dtype=dtype)
    mel_batch = torch.ones(batch_size, 1, 80, 16, device=device, dtype=dtype)
    model(mel_batch, img_batch)

def __mirror_index(size, index):
    #size = len(self.coord_list_cycle)
    turn = index // size
    res = index % size
    if turn % 2 == 0:
        return res
    else:
        return size - res - 1 

def inference(quit_event, batch_size, face_list_cycle, audio_feat_queue, audio_out_queue, res_frame_queue, model, gfpgan=None):
    
    #model = load_model("./models/wav2lip.pth")
    # input_face_list = glob.glob(os.path.join(face_imgs_path, '*.[jpJP][pnPN]*[gG]'))
    # input_face_list = sorted(input_face_list, key=lambda x: int(os.path.splitext(os.path.basename(x))[0]))
    # face_list_cycle = read_imgs(input_face_list)
    
    #input_latent_list_cycle = torch.load(latents_out_path)
    length = len(face_list_cycle)
    index = 0
    count=0
    counttime=0
    logger.info('start inference')
    while not quit_event.is_set():
        starttime=time.perf_counter()
        mel_batch = []
        try:
            mel_batch = audio_feat_queue.get(block=True, timeout=1)
        except queue.Empty:
            continue
            
        is_all_silence=True
        audio_frames = []
        for _ in range(batch_size*2):
            frame,type,eventpoint = audio_out_queue.get()
            audio_frames.append((frame,type,eventpoint))
            if type==0:
                is_all_silence=False

        if is_all_silence:
            for i in range(batch_size):
                res_frame_queue.put((None,__mirror_index(length,index),audio_frames[i*2:i*2+2]))
                index = index + 1
        else:
            # print('infer=======')
            t=time.perf_counter()
            img_batch = []
            for i in range(batch_size):
                idx = __mirror_index(length,index+i)
                face = face_list_cycle[idx]
                h, w = face.shape[:2]
                if h != WAV2LIP_FACE_SIZE or w != WAV2LIP_FACE_SIZE:
                    face = cv2.resize(
                        face,
                        (WAV2LIP_FACE_SIZE, WAV2LIP_FACE_SIZE),
                        interpolation=cv2.INTER_LANCZOS4,
                    )
                img_batch.append(face)
            img_batch, mel_batch = np.asarray(img_batch), np.asarray(mel_batch)

            img_masked = img_batch.copy()
            img_masked[:, face.shape[0]//2:] = 0

            img_batch = np.concatenate((img_masked, img_batch), axis=3) / 255.
            mel_batch = np.reshape(mel_batch, [len(mel_batch), mel_batch.shape[1], mel_batch.shape[2], 1])

            try:
                dtype = next(model.parameters()).dtype
            except (StopIteration, AttributeError):
                dtype = torch.float32
            img_batch = torch.as_tensor(
                np.transpose(img_batch, (0, 3, 1, 2)),
                device=device,
                dtype=dtype,
            )
            mel_batch = torch.as_tensor(
                np.transpose(mel_batch, (0, 3, 1, 2)),
                device=device,
                dtype=dtype,
            )

            with torch.no_grad():
                if gfpgan is not None:
                    with GPU_INFER_LOCK:
                        pred = model(mel_batch, img_batch)
                        pred = (
                            pred.float()
                            .clamp_(0.0, 1.0)
                            .mul_(255.0)
                            .byte()
                            .permute(0, 2, 3, 1)
                            .cpu()
                            .numpy()
                        )
                        pred = np.stack(
                            [gfpgan.enhance(frame, _lock=False) for frame in pred],
                            axis=0,
                        )
                else:
                    pred = model(mel_batch, img_batch)
                    pred = (
                        pred.float()
                        .clamp_(0.0, 1.0)
                        .mul_(255.0)
                        .byte()
                        .permute(0, 2, 3, 1)
                        .cpu()
                        .numpy()
                    )

            counttime += (time.perf_counter() - t)
            count += batch_size
            #_totalframe += 1
            if count>=100:
                logger.info(f"------actual avg infer fps:{count/counttime:.4f}")
                count=0
                counttime=0
            for i,res_frame in enumerate(pred):
                #self.__pushmedia(res_frame,loop,audio_track,video_track)
                res_frame_queue.put((res_frame,__mirror_index(length,index),audio_frames[i*2:i*2+2]))
                index = index + 1
            #print('total batch time:',time.perf_counter()-starttime)            
    logger.info('lipreal inference processor stop')

class Wav2LipAvatar(BaseAvatar):
    @torch.no_grad()
    def __init__(self, config, model, avatar):
        super().__init__(config)
        #self.opt = opt # shared with the trainer's opt to support in-place modification of rendering parameters.
        # self.W = opt.W
        # self.H = opt.H

        self.fps = config.audio.fps # 20 ms per frame
        
        self.batch_size = config.model.batch_size
        self.idx = 0
        self.res_frame_queue = Queue(max(24, self.batch_size * 6))
        #self.__loadavatar()
        self.model = model
        frames, faces, coords = avatar
        # Each instance needs its own list objects so that switch_avatar's
        # in-place slice assignment doesn't corrupt the shared cache entry.
        self.frame_list_cycle = list(frames)
        self.face_list_cycle  = list(faces)
        self.coord_list_cycle = list(coords)

        self.gfpgan = build_gfpgan_enhancer(config)
        if self.gfpgan is not None:
            self.gfpgan.warm_up(WAV2LIP_FACE_SIZE)

        self.audio_stream = LipAudioStreamHandler(config, self)
        self.audio_stream.warm_up()
        
        self.render_event = mp.Event()
    
    # def __del__(self):
    #     logger.info(f'lipreal({self.sessionid}) delete')

    def paste_back_frame(self,pred_frame,idx:int):
        bbox = self.coord_list_cycle[idx]
        combine_frame = self.frame_list_cycle[idx].copy()
        #combine_frame = copy.deepcopy(self.imagecache.get_img(idx))
        y1, y2, x1, x2 = bbox
        res_frame = cv2.resize(pred_frame.astype(np.uint8),(x2-x1,y2-y1))
        #combine_frame = get_image(ori_frame,res_frame,bbox)
        #t=time.perf_counter()
        combine_frame[y1:y2, x1:x2] = res_frame
        return combine_frame

    def switch_avatar(self, avatar_id: str):
        """
        Switch the underlying avatar frames/coords to a different
        pre-generated wav2lip avatar (e.g. wav2lip_avatar1_ex).

        This reloads the avatar data from ./data/avatars/<avatar_id>
        but reuses the already loaded Wav2Lip model.

        The inference thread captured the face_list_cycle object and its
        length at start-up. We must keep the same list object and the same
        length so the running inference loop never sees an out-of-range index.
        If the new avatar has a different frame count we cycle/trim it to
        match the original length before swapping in-place.
        """
        logger.info("Wav2LipAvatar.switch_avatar -> %s", avatar_id)
        try:
            new_frames, new_faces, new_coords = load_avatar(avatar_id)
        except Exception:
            logger.exception("Failed to switch Wav2Lip avatar to %s", avatar_id)
            return

        old_len = len(self.face_list_cycle)
        new_len = len(new_faces)

        if new_len != old_len:
            logger.info(
                "Wav2LipAvatar.switch_avatar(%s): frame count changed "
                "(%d -> %d); normalizing to %d by cycling.",
                avatar_id, old_len, new_len, old_len,
            )
            # Build lists of exactly old_len by cycling through the new data
            def _normalize(lst, target):
                if not lst:
                    return lst
                return [lst[i % len(lst)] for i in range(target)]

            new_faces  = _normalize(new_faces,  old_len)
            new_frames = _normalize(new_frames, old_len)
            new_coords = _normalize(new_coords, old_len)

        # Replace background frames and coords (these are read via self.* in
        # process_frames / paste_back_frame, so simple reassignment is safe).
        self.frame_list_cycle = new_frames
        self.coord_list_cycle = new_coords

        # Update face_list_cycle in-place so the inference thread, which
        # holds a direct reference to the original list object, immediately
        # starts pulling from the new avatar's face crops.
        self.face_list_cycle[:] = new_faces
            
    def render(self,quit_event,loop=None,audio_track=None,video_track=None,media_sink=None):
        #if self.opt.asr:
        #     self.audio_stream.warm_up()

        self.init_customindex()
        self.tts.render(quit_event)
        
        infer_quit_event = Event()
        infer_thread = Thread(target=inference, args=(infer_quit_event,self.batch_size,self.face_list_cycle,
                                           self.audio_stream.feat_queue,self.audio_stream.output_queue,self.res_frame_queue,
                                           self.model,self.gfpgan,))  #mp.Process
        infer_thread.start()
        
        process_quit_event = Event()
        process_thread = Thread(target=self.process_frames, args=(process_quit_event,loop,audio_track,video_track), kwargs={"media_sink": media_sink})
        process_thread.start()

        #self.render_event.set() #start infer process render
        count=0
        totaltime=0
        _starttime=time.perf_counter()
        #_totalframe=0
        while not quit_event.is_set(): 
            # update texture every frame
            # audio stream thread...
            t = time.perf_counter()
            self.audio_stream.run_step()

            # if video_track._queue.qsize()>=2*self.config.model.batch_size:
            #     print('sleep qsize=',video_track._queue.qsize())
            #     time.sleep(0.04*video_track._queue.qsize()*0.8)
            if video_track and video_track._queue.qsize()>=5:
                logger.debug('sleep qsize=%d',video_track._queue.qsize())
                time.sleep(0.04*video_track._queue.qsize()*0.8)
            elif media_sink is not None:
                streaming = bool(getattr(media_sink, "is_streaming_active", False))
                if streaming:
                    q = self.res_frame_queue.qsize()
                    if q > self.batch_size:
                        time.sleep(min(0.2, 0.04 * q * 0.6))
                    else:
                        step_interval = (self.batch_size * 2) / self.config.audio.fps
                        elapsed = time.perf_counter() - t
                        if elapsed < step_interval:
                            time.sleep(step_interval - elapsed)
                else:
                    v_backlog = getattr(media_sink, "outbound_video_backlog", 0)
                    buf_cap = getattr(media_sink, "video_out_buffer_capacity", 3)
                    if v_backlog >= max(1, buf_cap - 1):
                        logger.debug(
                            'Agora outbound video backlog=%d cap=%d', v_backlog, buf_cap
                        )
                        time.sleep(min(0.12, 0.04 * v_backlog * 0.8))
                    elif self.res_frame_queue.qsize() >= self.batch_size:
                        backlog = self.res_frame_queue.qsize()
                        logger.debug('Agora render backlog qsize=%d', backlog)
                        time.sleep(min(0.12, 0.04 * backlog * 0.5))
                    else:
                        step_interval = (self.batch_size * 2) / self.config.audio.fps
                        elapsed = time.perf_counter() - t
                        if elapsed < step_interval:
                            time.sleep(step_interval - elapsed)
                
            # delay = _starttime+_totalframe*0.04-time.perf_counter() #40ms
            # if delay > 0:
            #     time.sleep(delay)
        #self.render_event.clear() #end infer process render
        logger.info('lipreal thread stop')

        infer_quit_event.set()
        infer_thread.join()

        process_quit_event.set()
        process_thread.join()
            