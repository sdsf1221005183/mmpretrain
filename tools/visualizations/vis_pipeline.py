# Copyright (c) OpenMMLab. All rights reserved.
import argparse
import copy
import itertools
import os
import re
import sys
from pathlib import Path
from typing import List

import cv2
import mmcv
import numpy as np
from mmcv import Config, DictAction, ProgressBar

from mmcls.core import visualization as vis
from mmcls.datasets.builder import PIPELINES, build_dataset, build_from_cfg
from mmcls.models.utils import to_2tuple


def parse_args():
    parser = argparse.ArgumentParser(
        description='Visualize a Dataset Pipeline')
    parser.add_argument('config', help='config file path')
    parser.add_argument(
        '--skip-type',
        type=str,
        nargs='*',
        default=['ToTensor', 'Normalize', 'ImageToTensor', 'Collect'],
        help='the pipelines to skip when visualizing')
    parser.add_argument(
        '--output-dir',
        default='',
        type=str,
        help='folder to save output pictures, if not set, do not save.')
    parser.add_argument(
        '--phase',
        default='train',
        type=str,
        choices=['train', 'test', 'val'],
        help='phase of dataset to visualize, accept "train" "test" and "val".'
        ' Default train.')
    parser.add_argument(
        '--number',
        type=int,
        default=sys.maxsize,
        help='number of images selected to visualize, must bigger than 0. if '
        'the number is bigger than length of dataset, show all the images in '
        'dataset; default "sys.maxsize", show all images in dataset')
    parser.add_argument(
        '--mode',
        default='concat',
        type=str,
        choices=['original', 'transformed', 'concat', 'pipeline'],
        help='display mode; display original pictures or transformed pictures'
        ' or comparison pictures. "original" means show images load from disk'
        '; "transformed" means to show images after transformed; "concat" '
        'means show images stitched by "original" and "output" images. '
        '"pipeline" means show all the intermediate images. Default concat.')
    parser.add_argument(
        '--show',
        default=False,
        action='store_true',
        help='whether to display images in pop-up window. Default False.')
    parser.add_argument(
        '--adaptive',
        default=False,
        action='store_true',
        help='whether to automatically adjust the visualization image size')
    parser.add_argument(
        '--min-edge-length',
        default=200,
        type=int,
        help='the min edge length when visualizing images, used when '
        '"--adaptive" is true. Default 200.')
    parser.add_argument(
        '--max-edge-length',
        default=1000,
        type=int,
        help='the max edge length when visualizing images, used when '
        '"--adaptive" is true. Default 1000.')
    parser.add_argument(
        '--bgr2rgb',
        default=False,
        action='store_true',
        help='flip the color channel order of images')
    parser.add_argument(
        '--window-size',
        default='12*7',
        help='size of the window to display images, in format of "$W*$H".')
    parser.add_argument(
        '--cfg-options',
        nargs='+',
        action=DictAction,
        help='override some settings in the used config, the key-value pair '
        'in xxx=yyy format will be merged into config file. If the value to '
        'be overwritten is a list, it should be like key="[a,b]" or key=a,b '
        'It also allows nested list/tuple values, e.g. key="[(a,b),(c,d)]" '
        'Note that the quotation marks are necessary and that no white space '
        'is allowed.')
    parser.add_argument(
        '--show-options',
        nargs='+',
        action=DictAction,
        help='custom options for display. key-value pair in xxx=yyy. options '
        'in `mmcls.core.visualization.ImshowInfosContextManager.put_img_infos`'
    )
    args = parser.parse_args()

    assert args.number > 0, "'args.number' must be larger than zero."
    if args.window_size != '':
        assert re.match(r'\d+\*\d+', args.window_size), \
            "'window-size' must be in format 'W*H'."
    if args.output_dir == '' and not args.show:
        raise ValueError("if '--output-dir' and '--show' are not set, "
                         'nothing will happen when the program running.')

    if args.show_options is None:
        args.show_options = {}
    return args


def retrieve_data_cfg(config_path, skip_type, cfg_options, phase):
    cfg = Config.fromfile(config_path)
    if cfg_options is not None:
        cfg.merge_from_dict(cfg_options)
    data_cfg = cfg.data[phase]
    while 'dataset' in data_cfg:
        data_cfg = data_cfg['dataset']
    data_cfg['pipeline'] = [
        x for x in data_cfg.pipeline if x['type'] not in skip_type
    ]

    return cfg


def build_dataset_pipelines(cfg, phase):
    """build dataset and pipeline from config.

    Separate the pipeline except 'LoadImageFromFile' step if
    'LoadImageFromFile' in the pipeline.
    """
    data_cfg = cfg.data[phase]
    loadimage_pipeline = []
    if len(data_cfg.pipeline
           ) != 0 and data_cfg.pipeline[0]['type'] == 'LoadImageFromFile':
        loadimage_pipeline.append(data_cfg.pipeline.pop(0))
    origin_pipeline = data_cfg.pipeline
    data_cfg.pipeline = loadimage_pipeline
    dataset = build_dataset(data_cfg)
    pipelines = {
        pipeline_cfg['type']: build_from_cfg(pipeline_cfg, PIPELINES)
        for pipeline_cfg in origin_pipeline
    }

    return dataset, pipelines


def concat_imgs(imgs: List[np.ndarray], steps: List[str]) -> np.ndarray:
    """Concat list of pictures into a single big picture, align height here."""
    shapes = [img.shape for img in imgs]
    heights = [shape[0] for shape in shapes]
    widths = [shape[1] for shape in shapes]
    max_height = max(heights)
    text_height, pic_horizontal_gap = max_height // 10, min(widths) // 10
    for i, img in enumerate(imgs):
        cur_height = heights[i]
        pad_height = max_height - cur_height
        pad_top, pad_bottom = to_2tuple(pad_height // 2)
        # handle instance that the pad_height is an odd number
        if pad_height % 2 == 1:
            pad_top = pad_top + 1
        pad_bottom += text_height * 3 # keep pxs to put step information text
        pad_left, pad_right = to_2tuple(pic_horizontal_gap)

        # make border
        img = cv2.copyMakeBorder(
            img,
            pad_top,
            pad_bottom,
            pad_left,
            pad_right,
            cv2.BORDER_CONSTANT,
            value=(255, 255, 255))
        # put transformer phase
        imgs[i] = cv2.putText(
            img=img, 
            text=steps[i],
            org=(pic_horizontal_gap, max_height + text_height // 2),
            fontFace=cv2.FONT_HERSHEY_COMPLEX, 
            fontScale=0.5, 
            color=(0, 0, 0), 
            lineType=1)
        # put image size
        imgs[i] = cv2.putText(
            img=img, 
            text=str(shapes[i]),
            org=(pic_horizontal_gap, max_height + int(text_height * 1.5)),
            fontFace=cv2.FONT_HERSHEY_COMPLEX, 
            fontScale=0.5, 
            color=(0, 0, 0), 
            lineType=1)

    # High alignment for concatenating
    board = np.concatenate(imgs, axis=1)
    return board


def adaptive_size(image, min_edge_length, max_edge_length, src_shape):
    """rescale image if image is too small to put text like cifra."""
    assert min_edge_length >= 0 and max_edge_length >= 0
    assert max_edge_length >= min_edge_length
    image_h, image_w, _ = src_shape

    if image_h < min_edge_length or image_w < min_edge_length:
        image = mmcv.imrescale(
            image, min(min_edge_length / image_h, min_edge_length / image_h))
    if image_h > max_edge_length or image_w > max_edge_length:
        image = mmcv.imrescale(
            image, max(max_edge_length / image_h, max_edge_length / image_w))
    return image


def get_display_img(args, item, pipelines):
    """get image to display."""
    # srcs picture could be in RGB or BGR order due to different backends.
    if args.bgr2rgb:
        item['img'] = mmcv.bgr2rgb(item['img'])
    src_image = item['img'].copy()
    intermediates_images = []

    # get intermediates images through pipelines
    if args.mode in ['transformed', 'concat', 'pipeline']:
        for pipeline in pipelines.values():
            item = pipeline(item)
            trans_image = copy.deepcopy(item['img'])
            trans_image = np.ascontiguousarray(trans_image, dtype=np.uint8)
            intermediates_images.append(trans_image)

    # concat all the images to show, depandding on 'mode'
    if args.mode == 'original':
        image = src_image
    elif args.mode == 'transformed':
        image = intermediates_images[-1]
    elif args.mode == 'concat':
        steps = ['src', 'transformed']
        image = concat_imgs([src_image, intermediates_images[-1]], steps)
    elif args.mode == 'pipeline':
        steps = ['src'] + list(pipelines.keys())
        image = concat_imgs([src_image] + intermediates_images, steps)

    # if src image is too large or too small, it will make the text information
    #  difficult to confirm, so here add adaptive adjustment.
    if args.adaptive:
        image = adaptive_size(image, args.min_edge_length,
                              args.max_edge_length, src_image.shape)
    return image


def main():
    args = parse_args()
    wind_w, wind_h = args.window_size.split('*')
    wind_w, wind_h = int(wind_w), int(wind_h) # showing windows size
    cfg = retrieve_data_cfg(args.config, args.skip_type, args.cfg_options,
                            args.phase)

    dataset, pipelines = build_dataset_pipelines(cfg, args.phase)
    CLASSES = dataset.CLASSES
    display_number = min(args.number, len(dataset))
    progressBar = ProgressBar(display_number)

    with vis.ImshowInfosContextManager(fig_size=(wind_w, wind_h)) as manager:
        for i, item in enumerate(itertools.islice(dataset, display_number)):
            image = get_display_img(args, item, pipelines) 

            # dist_path is None as default, means not saving pictures
            dist_path = None
            if args.output_dir:
                # some datasets don't have filenames, such as cifar
                src_path = item.get('filename', '{}.jpg'.format(i))
                dist_path = os.path.join(args.output_dir, Path(src_path).name)

            infos = dict(label=CLASSES[item['gt_label']])

            ret, _ = manager.put_img_infos(
                image,
                infos,
                font_size=20,
                out_file=dist_path,
                show=args.show,
                **args.show_options)

            progressBar.update()

            if ret == 1:
                print('\nMannualy interrupted.')
                break


if __name__ == '__main__':
    main()
