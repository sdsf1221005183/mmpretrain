_base_ = [
    '../_base_/models/eva02/eva02_base.py',
    '../_base_/datasets/imagenet_bs16_eva_448.py',
    '../_base_/schedules/imagenet_bs2048_AdamW.py',
    '../_base_/default_runtime.py'
]
