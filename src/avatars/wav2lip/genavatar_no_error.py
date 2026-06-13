from os import listdir, path
import numpy as np
import scipy, cv2, os, sys, argparse
import json, subprocess, random, string
from tqdm import tqdm
from glob import glob
import torch
import pickle
import face_detection
from src.utils.png_io import imwrite_png


parser = argparse.ArgumentParser(description='Inference code to lip-sync videos in the wild using Wav2Lip models')
parser.add_argument('--img_size', default=256, type=int,
					help='Face crop stored size (256 matches Wav2Lip; 96 saves disk but upscales at inference)')
parser.add_argument('--avatar_id', default='wav2lip_avatar1', type=str)
parser.add_argument('--full_width', default=1080, type=int,
					help='full_imgs width (1080p portrait); Agora still publishes config video.width x height')
parser.add_argument('--full_height', default=1920, type=int,
					help='full_imgs height (1080p portrait)')
parser.add_argument('--video_path', default='', type=str)
parser.add_argument('--nosmooth', default=False, action='store_true',
					help='Prevent smoothing face detections over a short temporal window')
parser.add_argument('--pads', nargs='+', type=int, default=[0, 10, 0, 0], 
					help='Padding (top, bottom, left, right). Please adjust to include chin at least')
parser.add_argument('--face_det_batch_size', type=int, 
					help='Batch size for face detection', default=16)
parser.add_argument('--draw_boxes', action='store_true',
					help='Save frames with detector box + padded crop drawn (see box_debug/)')
args = parser.parse_args()

device = 'cuda' if torch.cuda.is_available() else 'cpu'
print('Using {} for inference.'.format(device))

def osmakedirs(path_list):
    for path in path_list:
        os.makedirs(path) if not os.path.exists(path) else None

def _normalize_full_frame(frame, target_w: int, target_h: int):
	"""Scale full body frame to avatar asset size (default 1080x1920). Broadcast size is separate (config video.*)."""
	if target_w <= 0 or target_h <= 0:
		return frame
	h, w = frame.shape[:2]
	if w == target_w and h == target_h:
		return frame
	interp = cv2.INTER_AREA if (target_w * target_h) < (w * h) else cv2.INTER_LINEAR
	return cv2.resize(frame, (target_w, target_h), interpolation=interp)

def video2imgs(vid_path, save_path, ext = '.png',cut_frame = 10000000):
    cap = cv2.VideoCapture(vid_path)
    count = 0
    target_w = int(args.full_width)
    target_h = int(args.full_height)
    while True:
        if count > cut_frame:
            break
        ret, frame = cap.read()
        if ret:
            frame = _normalize_full_frame(frame, target_w, target_h)
            imwrite_png(f"{save_path}/{count:08d}.png", frame)
            count += 1
        else:
            break
    if count:
        print(f'full_imgs: {count} frames at {target_w}x{target_h} (face crop stays {args.img_size}x{args.img_size})')

def read_imgs(img_list):
    frames = []
    print('reading images...')
    for img_path in tqdm(img_list):
        frame = cv2.imread(img_path)
        frames.append(frame)
    return frames

def get_smoothened_boxes(boxes, T):
	for i in range(len(boxes)):
		if i + T > len(boxes):
			window = boxes[len(boxes) - T:]
		else:
			window = boxes[i : i + T]
		boxes[i] = np.mean(window, axis=0)
	return boxes

def face_detect_paths(img_paths):
	"""Detect faces reading one frame from disk at a time (lower RAM than read_imgs)."""
	detector = face_detection.FaceAlignment(face_detection.LandmarksType._2D,
											flip_input=False, device=device)

	pady1, pady2, padx1, padx2 = args.pads
	predictions = []
	valid_indices = []
	valid_images = []
	total = len(img_paths)
	for i in tqdm(range(total), desc='face detect'):
		image = cv2.imread(img_paths[i])
		if image is None:
			print(f'WARNING: failed to read frame {img_paths[i]}')
			continue
		try:
			batch_pred = detector.get_detections_for_batch(np.array([image]))
		except RuntimeError:
			raise RuntimeError('Image too big to run face detection on GPU. Please use the --resize_factor argument')
		rect = batch_pred[0]
		if rect is None:
			continue
		predictions.append(rect)
		valid_indices.append(i)
		valid_images.append(image)

	if not predictions:
		raise ValueError('Face not detected in any frame. Ensure the video contains a visible face.')

	raw_boxes = np.array([[r[0], r[1], r[2], r[3]] for r in predictions], dtype=np.float64)
	padded_rows = []
	for idx, rect in enumerate(predictions):
		image = valid_images[idx]
		y1 = max(0, rect[1] - pady1)
		y2 = min(image.shape[0], rect[3] + pady2)
		x1 = max(0, rect[0] - padx1)
		x2 = min(image.shape[1], rect[2] + padx2)
		padded_rows.append([x1, y1, x2, y2])
	boxes = np.array(padded_rows, dtype=np.float64)
	if not args.nosmooth:
		boxes = get_smoothened_boxes(boxes.copy(), T=5)
		if args.draw_boxes:
			raw_boxes = get_smoothened_boxes(raw_boxes.copy(), T=5)

	results = [
		[valid_images[j][int(y1):int(y2), int(x1):int(x2)], (int(y1), int(y2), int(x1), int(x2))]
		for j, (x1, y1, x2, y2) in enumerate(boxes)
	]

	if len(valid_indices) < total:
		print('Skipped {} frame(s) with no face detected (kept {}/{}).'.format(
			total - len(valid_indices), len(valid_indices), total))

	del detector
	overlay = (raw_boxes, boxes) if args.draw_boxes else None
	return results, valid_indices, overlay, valid_images

def _draw_box_overlay(bgr, raw_xyxy, pad_xyxy):
	"""Draw raw detector rect (orange) and padded crop (green). xyxy = xmin, ymin, xmax, ymax."""
	out = bgr.copy()
	x1, y1, x2, y2 = [int(round(v)) for v in raw_xyxy]
	cv2.rectangle(out, (x1, y1), (x2, y2), (0, 165, 255), 2)
	cv2.putText(out, 'det', (x1, max(0, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 165, 255), 1, cv2.LINE_AA)
	px1, py1, px2, py2 = [int(round(v)) for v in pad_xyxy]
	cv2.rectangle(out, (px1, py1), (px2, py2), (0, 255, 0), 2)
	cv2.putText(out, 'pad', (px1, min(out.shape[0] - 4, py2 + 14)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1, cv2.LINE_AA)
	return out

def face_detect(images):
	detector = face_detection.FaceAlignment(face_detection.LandmarksType._2D, 
											flip_input=False, device=device)

	pady1, pady2, padx1, padx2 = args.pads
	# Process frame-by-frame to avoid inhomogeneous shape when frames differ in size,
	# and to allow skipping frames where no face is detected.
	predictions = []
	valid_indices = []
	for i in tqdm(range(len(images))):
		try:
			# Single-image batch avoids np.array shape errors from varying frame sizes
			batch_pred = detector.get_detections_for_batch(np.array([images[i]]))
		except RuntimeError:
			raise RuntimeError('Image too big to run face detection on GPU. Please use the --resize_factor argument')
		rect = batch_pred[0]
		if rect is None:
			# Skip frames where no face was detected
			continue
		predictions.append(rect)
		valid_indices.append(i)

	if not predictions:
		raise ValueError('Face not detected in any frame. Ensure the video contains a visible face.')

	# Raw detector boxes (xmin, ymin, xmax, ymax) and padded crops; smooth both when enabled.
	raw_boxes = np.array([[r[0], r[1], r[2], r[3]] for r in predictions], dtype=np.float64)
	padded_rows = []
	for idx, rect in enumerate(predictions):
		image = images[valid_indices[idx]]
		y1 = max(0, rect[1] - pady1)
		y2 = min(image.shape[0], rect[3] + pady2)
		x1 = max(0, rect[0] - padx1)
		x2 = min(image.shape[1], rect[2] + padx2)
		padded_rows.append([x1, y1, x2, y2])
	boxes = np.array(padded_rows, dtype=np.float64)
	if not args.nosmooth:
		boxes = get_smoothened_boxes(boxes.copy(), T=5)
		if args.draw_boxes:
			raw_boxes = get_smoothened_boxes(raw_boxes.copy(), T=5)

	# Return (cropped_face, coords) only for frames where face was detected
	results = [
		[images[valid_indices[j]][int(y1):int(y2), int(x1):int(x2)], (int(y1), int(y2), int(x1), int(x2))]
		for j, (x1, y1, x2, y2) in enumerate(boxes)
	]

	if len(valid_indices) < len(images):
		print('Skipped {} frame(s) with no face detected (kept {}/{}).'.format(
			len(images) - len(valid_indices), len(valid_indices), len(images)))

	del detector
	overlay = (raw_boxes, boxes) if args.draw_boxes else None
	return results, valid_indices, overlay

if __name__ == "__main__":
    avatar_path = f"./data/avatars/{args.avatar_id}"
    full_imgs_path = f"{avatar_path}/full_imgs" 
    face_imgs_path = f"{avatar_path}/face_imgs" 
    coords_path = f"{avatar_path}/coords.pkl"
    box_debug_path = f"{avatar_path}/box_debug"
    prep_paths = [avatar_path, full_imgs_path, face_imgs_path]
    if args.draw_boxes:
        prep_paths.append(box_debug_path)
    osmakedirs(prep_paths)
    print(args)

    #if os.path.isfile(args.video_path):
    video2imgs(args.video_path, full_imgs_path, ext = 'png')
    input_img_list = sorted(glob(os.path.join(full_imgs_path, '*.[jpJP][pnPN]*[gG]')))

    face_det_results, valid_indices, overlay, valid_images = face_detect_paths(input_img_list)
    coord_list = []
    # Write only valid frames to full_imgs so full_imgs and face_imgs stay in sync for avatar load
    for idx, (frame, coords) in enumerate(face_det_results):
        src_full = valid_images[idx]
        imwrite_png(f"{full_imgs_path}/{idx:08d}.png", src_full)
        resized_crop_frame = cv2.resize(frame, (args.img_size, args.img_size))
        imwrite_png(f"{face_imgs_path}/{idx:08d}.png", resized_crop_frame)
        coord_list.append(coords)
        if overlay is not None:
            raw_boxes, pad_boxes = overlay
            vis = _draw_box_overlay(src_full, raw_boxes[idx], pad_boxes[idx])
            imwrite_png(f"{box_debug_path}/{idx:08d}.png", vis)

    with open(coords_path, 'wb') as f:
        pickle.dump(coord_list, f)
