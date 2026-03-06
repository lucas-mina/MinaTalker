import math
import torch
import numpy as np

#from .utils import *
import subprocess
import os
import time
import torch.nn.functional as F
import cv2
import glob
import pickle
import copy

import queue
from queue import Queue
from threading import Thread, Event
import torch.multiprocessing as mp

from src.avatars.musetalk.utils.utils import get_file_type,get_video_fps,datagen
#from musetalk.utils.preprocessing import get_landmark_and_bbox,read_imgs,coord_placeholder
from src.avatars.musetalk.myutil import get_image_blending
from src.avatars.musetalk.utils.utils import load_all_model
from src.avatars.musetalk.whisper.audio2feature import Audio2Feature

from src.avatars.musetalk.audio_stream_handler import MuseAudioStreamHandler
import asyncio
from av import AudioFrame, VideoFrame
from src.avatars.base import BaseAvatar

from tqdm import tqdm
from src.utils.logging import logger

_AVATAR_CACHE = {}


def load_model():
    # load model weights
    vae, unet, pe = load_all_model()
    device = torch.device("cuda" if torch.cuda.is_available() else ("mps" if (hasattr(torch.backends, "mps") and torch.backends.mps.is_available()) else "cpu"))
    timesteps = torch.tensor([0], device=device)
    pe = pe.half().to(device)
    vae.vae = vae.vae.half().to(device)
    #vae.vae.share_memory().to(device)
    unet.model = unet.model.half().to(device)
    #unet.model.share_memory()
    # Initialize audio processor and Whisper model
    audio_processor = Audio2Feature(model_path="./models/musetalk/whisper")
    return vae, unet, pe, timesteps, audio_processor

def load_avatar(avatar_id):
    # Return from cache if available
    cached = _AVATAR_CACHE.get(avatar_id)
    if cached is not None:
        return cached

    #self.video_path = '' #video_path
    #self.bbox_shift = opt.bbox_shift
    avatar_path = f"./data/avatars/{avatar_id}"
    full_imgs_path = f"{avatar_path}/full_imgs" 
    coords_path = f"{avatar_path}/coords.pkl"
    latents_out_path= f"{avatar_path}/latents.pt"
    video_out_path = f"{avatar_path}/vid_output/"
    mask_out_path =f"{avatar_path}/mask"
    mask_coords_path =f"{avatar_path}/mask_coords.pkl"
    avatar_info_path = f"{avatar_path}/avator_info.json"
    # self.avatar_info = {
    #     "avatar_id":self.avatar_id,
    #     "video_path":self.video_path,
    #     "bbox_shift":self.bbox_shift   
    # }

    input_latent_list_cycle = torch.load(latents_out_path)  #,weights_only=True
    with open(coords_path, 'rb') as f:
        coord_list_cycle = pickle.load(f)
    input_img_list = glob.glob(os.path.join(full_imgs_path, '*.[jpJP][pnPN]*[gG]'))
    input_img_list = sorted(input_img_list, key=lambda x: int(os.path.splitext(os.path.basename(x))[0]))
    frame_list_cycle = read_imgs(input_img_list)
    with open(mask_coords_path, 'rb') as f:
        mask_coords_list_cycle = pickle.load(f)
    input_mask_list = glob.glob(os.path.join(mask_out_path, '*.[jpJP][pnPN]*[gG]'))
    input_mask_list = sorted(input_mask_list, key=lambda x: int(os.path.splitext(os.path.basename(x))[0]))
    mask_list_cycle = read_imgs(input_mask_list)
    avatar_data = (
        frame_list_cycle,
        mask_list_cycle,
        coord_list_cycle,
        mask_coords_list_cycle,
        input_latent_list_cycle,
    )
    _AVATAR_CACHE[avatar_id] = avatar_data
    return avatar_data


def preload_avatars(avatar_ids):
    """
    Preload MuseTalk avatar assets into memory for the given ids.
    Safe to call multiple times; already-cached ids are skipped.
    """
    for avatar_id in avatar_ids:
        if not isinstance(avatar_id, str) or not avatar_id:
            continue
        if avatar_id in _AVATAR_CACHE:
            continue
        try:
            logger.info("Preloading MuseTalk avatar assets: %s", avatar_id)
            load_avatar(avatar_id)
        except Exception:
            logger.exception("Failed to preload MuseTalk avatar %s", avatar_id)

@torch.no_grad()
def warm_up(batch_size,model):
    # 预热函数
    logger.info('warmup model...')
    vae, unet, pe, timesteps, audio_processor = model
    #batch_size = 16
    #timesteps = torch.tensor([0], device=unet.device)
    whisper_batch = np.ones((batch_size, 50, 384), dtype=np.uint8)
    latent_batch = torch.ones(batch_size, 8, 32, 32).to(unet.device)

    audio_feature_batch = torch.from_numpy(whisper_batch)
    audio_feature_batch = audio_feature_batch.to(device=unet.device, dtype=unet.model.dtype)
    audio_feature_batch = pe(audio_feature_batch)
    latent_batch = latent_batch.to(dtype=unet.model.dtype)
    pred_latents = unet.model(latent_batch,
                              timesteps,
                              encoder_hidden_states=audio_feature_batch).sample
    vae.decode_latents(pred_latents)

def read_imgs(img_list):
    frames = []
    logger.info('reading images...')
    for img_path in tqdm(img_list):
        frame = cv2.imread(img_path)
        frames.append(frame)
    return frames

def __mirror_index(size, index):
    #size = len(self.coord_list_cycle)
    turn = index // size
    res = index % size
    if turn % 2 == 0:
        return res
    else:
        return size - res - 1 

@torch.no_grad()
def inference(quit_event,batch_size,input_latent_list_cycle,audio_feat_queue,audio_out_queue,res_frame_queue,
              vae, unet, pe,timesteps): #vae, unet, pe,timesteps
    
    # vae, unet, pe = load_diffusion_model()
    # device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    # timesteps = torch.tensor([0], device=device)
    # pe = pe.half()
    # vae.vae = vae.vae.half()
    # unet.model = unet.model.half()
    
    length = len(input_latent_list_cycle)
    index = 0
    count=0
    counttime=0
    logger.info('start inference')
    while not quit_event.is_set():
        starttime=time.perf_counter()
        try:
            whisper_chunks = audio_feat_queue.get(block=True, timeout=1)
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
            whisper_batch = np.stack(whisper_chunks)
            latent_batch = []
            for i in range(batch_size):
                idx = __mirror_index(length,index+i)
                latent = input_latent_list_cycle[idx]
                latent_batch.append(latent)
            latent_batch = torch.cat(latent_batch, dim=0)
            
            # for i, (whisper_batch,latent_batch) in enumerate(gen):
            audio_feature_batch = torch.from_numpy(whisper_batch)
            audio_feature_batch = audio_feature_batch.to(device=unet.device,
                                                            dtype=unet.model.dtype)
            audio_feature_batch = pe(audio_feature_batch)
            latent_batch = latent_batch.to(dtype=unet.model.dtype)
            # print('prepare time:',time.perf_counter()-t)
            # t=time.perf_counter()

            pred_latents = unet.model(latent_batch, 
                                        timesteps, 
                                        encoder_hidden_states=audio_feature_batch).sample
            # print('unet time:',time.perf_counter()-t)
            # t=time.perf_counter()
            recon = vae.decode_latents(pred_latents)
            # infer_inqueue.put((whisper_batch,latent_batch,sessionid))
            # recon,outsessionid = infer_outqueue.get()
            # if outsessionid != sessionid:
            #     print('outsessionid:',outsessionid,' mysessionid:',sessionid)

            # print('vae time:',time.perf_counter()-t)
            #print('diffusion len=',len(recon))
            counttime += (time.perf_counter() - t)
            count += batch_size
            #_totalframe += 1
            if count>=100:
                logger.info(f"------actual avg infer fps:{count/counttime:.4f}")
                count=0
                counttime=0
            for i,res_frame in enumerate(recon):
                #self.__pushmedia(res_frame,loop,audio_track,video_track)
                res_frame_queue.put((res_frame,__mirror_index(length,index),audio_frames[i*2:i*2+2]))
                index = index + 1
            #print('total batch time:',time.perf_counter()-starttime)            
    logger.info('musereal inference processor stop')

class MuseTalkAvatar(BaseAvatar):
    @torch.no_grad()
    def __init__(self, config, model, avatar):
        super().__init__(config)
        #self.opt = opt # shared with the trainer's opt to support in-place modification of rendering parameters.
        # self.W = opt.W
        # self.H = opt.H

        self.fps = config.audio.fps # 20 ms per frame

        self.batch_size = config.model.batch_size
        self.idx = 0
        self.res_frame_queue = mp.Queue(self.batch_size*2)

        self.vae, self.unet, self.pe, self.timesteps, self.audio_processor = model
        frames, masks, coords, mask_coords, latents = avatar
        # Each instance needs its own list objects so that switch_avatar's
        # in-place slice assignment doesn't corrupt the shared cache entry.
        self.frame_list_cycle       = list(frames)
        self.mask_list_cycle        = list(masks)
        self.coord_list_cycle       = list(coords)
        self.mask_coords_list_cycle = list(mask_coords)
        self.input_latent_list_cycle = list(latents)
        #self.__loadavatar()

        self.audio_stream = MuseAudioStreamHandler(config, self, self.audio_processor)
        self.audio_stream.warm_up()
        
        self.render_event = mp.Event()

    # def __del__(self):
    #     logger.info(f'musereal({self.sessionid}) delete')
    

    def __mirror_index(self, index):
        size = len(self.coord_list_cycle)
        turn = index // size
        res = index % size
        if turn % 2 == 0:
            return res
        else:
            return size - res - 1  

    def __warm_up(self): 
        self.audio_stream.run_step()
        whisper_chunks = self.audio_stream.get_next_feat()
        whisper_batch = np.stack(whisper_chunks)
        latent_batch = []
        for i in range(self.batch_size):
            idx = self.__mirror_index(self.idx+i)
            latent = self.input_latent_list_cycle[idx]
            latent_batch.append(latent)
        latent_batch = torch.cat(latent_batch, dim=0)
        logger.info('infer=======')
        # for i, (whisper_batch,latent_batch) in enumerate(gen):
        audio_feature_batch = torch.from_numpy(whisper_batch)
        audio_feature_batch = audio_feature_batch.to(device=self.unet.device,
                                                        dtype=self.unet.model.dtype)
        audio_feature_batch = self.pe(audio_feature_batch)
        latent_batch = latent_batch.to(dtype=self.unet.model.dtype)

        pred_latents = self.unet.model(latent_batch, 
                                    self.timesteps, 
                                    encoder_hidden_states=audio_feature_batch).sample
        recon = self.vae.decode_latents(pred_latents)
      

    def paste_back_frame(self,pred_frame,idx:int):
        bbox = self.coord_list_cycle[idx]
        ori_frame = copy.deepcopy(self.frame_list_cycle[idx])
        x1, y1, x2, y2 = bbox

        res_frame = cv2.resize(pred_frame.astype(np.uint8),(x2-x1,y2-y1))
        mask = self.mask_list_cycle[idx]
        mask_crop_box = self.mask_coords_list_cycle[idx]

        combine_frame = get_image_blending(ori_frame,res_frame,bbox,mask,mask_crop_box)
        return combine_frame

    def switch_avatar(self, avatar_id: str):
        """
        Switch the underlying MuseTalk avatar (latents/masks/coords)
        to a different pre-generated avatar id, e.g. avator_1_ex.

        The inference thread holds a direct reference to input_latent_list_cycle
        and captured its length at start-up. We must keep the same list object
        and the same length. If the new avatar has a different frame count we
        normalize it by cycling/trimming before swapping in-place.
        """
        logger.info("MuseTalkAvatar.switch_avatar -> %s", avatar_id)
        try:
            avatar = load_avatar(avatar_id)
        except Exception:
            logger.exception("Failed to switch MuseTalk avatar to %s", avatar_id)
            return

        (
            new_frames,
            new_masks,
            new_coords,
            new_mask_coords,
            new_latents,
        ) = avatar

        old_len = len(self.input_latent_list_cycle)
        new_len = len(new_latents)

        if new_len != old_len:
            logger.info(
                "MuseTalkAvatar.switch_avatar(%s): frame count changed "
                "(%d -> %d); normalizing to %d by cycling.",
                avatar_id, old_len, new_len, old_len,
            )

            def _normalize(lst, target):
                if not lst:
                    return lst
                return [lst[i % len(lst)] for i in range(target)]

            new_frames      = _normalize(new_frames,      old_len)
            new_masks       = _normalize(new_masks,       old_len)
            new_coords      = _normalize(new_coords,      old_len)
            new_mask_coords = _normalize(new_mask_coords, old_len)
            new_latents     = _normalize(new_latents,     old_len)

        # Reassign background and mask lists (read via self.* only)
        self.frame_list_cycle       = new_frames
        self.mask_list_cycle        = new_masks
        self.coord_list_cycle       = new_coords
        self.mask_coords_list_cycle = new_mask_coords

        # Update latents in-place so the inference thread immediately
        # uses the new avatar without seeing an out-of-range index.
        self.input_latent_list_cycle[:] = new_latents
            
    def render(self,quit_event,loop=None,audio_track=None,video_track=None):
        #if self.opt.asr:
        #     self.audio_stream.warm_up()

        self.init_customindex()
        self.tts.render(quit_event)
        
        #self.render_event.set() #start infer process render
        infer_quit_event = Event()
        infer_thread = Thread(target=inference, args=(infer_quit_event,self.batch_size,self.input_latent_list_cycle,
                                           self.audio_stream.feat_queue,self.audio_stream.output_queue,self.res_frame_queue,
                                           self.vae, self.unet, self.pe,self.timesteps)) #mp.Process
        infer_thread.start()
        
        process_quit_event = Event()
        process_thread = Thread(target=self.process_frames, args=(process_quit_event,loop,audio_track,video_track))
        process_thread.start()

        
        count=0
        totaltime=0
        _starttime=time.perf_counter()
        #_totalframe=0
        while not quit_event.is_set(): #todo
            # update texture every frame
            # audio stream thread...
            t = time.perf_counter()
            self.audio_stream.run_step()
            #self.test_step(loop,audio_track,video_track)
            # totaltime += (time.perf_counter() - t)
            # count += self.opt.batch_size
            # if count>=100:
            #     print(f"------actual avg infer fps:{count/totaltime:.4f}")
            #     count=0
            #     totaltime=0
            if video_track and video_track._queue.qsize()>=1.5*self.config.model.batch_size:
                logger.debug('sleep qsize=%d',video_track._queue.qsize())
                time.sleep(0.04*video_track._queue.qsize()*0.8)
            # if video_track._queue.qsize()>=5:
            #     print('sleep qsize=',video_track._queue.qsize())
            #     time.sleep(0.04*video_track._queue.qsize()*0.8)
                
            # delay = _starttime+_totalframe*0.04-time.perf_counter() #40ms
            # if delay > 0:
            #     time.sleep(delay)
        logger.info('musereal thread stop')

        infer_quit_event.set()
        infer_thread.join()

        process_quit_event.set()
        process_thread.join()
            
