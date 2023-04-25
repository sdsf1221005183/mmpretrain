# Copyright (c) OpenMMLab. All rights reserved.
from mmcv.transforms.loading import LoadImageFromFile
from mmcv.transforms.processing import RandomFlip
from mmengine.dataset.sampler import DefaultSampler

from mmpretrain.datasets.imagenet import ImageNet
from mmpretrain.datasets.transforms.formatting import PackInputs
from mmpretrain.datasets.transforms.processing import RandomResizedCrop
from mmpretrain.models.utils.data_preprocessor import SelfSupDataPreprocessor

# dataset settings
dataset_type = 'ImageNet'
data_root = 'data/imagenet/'
data_preprocessor = dict(
    type=SelfSupDataPreprocessor,
    mean=[123.675, 116.28, 103.53],
    std=[58.395, 57.12, 57.375],
    to_rgb=True)

train_pipeline = [
    dict(type=LoadImageFromFile),
    dict(
        type=RandomResizedCrop,
        scale=224,
        crop_ratio_range=(0.2, 1.0),
        backend='pillow',
        interpolation='bicubic'),
    dict(type=RandomFlip, prob=0.5),
    dict(type=PackInputs)
]

train_dataloader = dict(
    batch_size=512,
    num_workers=8,
    persistent_workers=True,
    sampler=dict(type=DefaultSampler, shuffle=True),
    collate_fn=dict(type='default_collate'),
    dataset=dict(
        type=ImageNet,
        data_root=data_root,
        # ann_file='meta/train.txt',
        data_prefix=dict(img_path='train/'),
        pipeline=train_pipeline))
