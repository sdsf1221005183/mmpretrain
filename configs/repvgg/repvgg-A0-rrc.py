_base_ = [
    '../_base_/models/repvgg-A0_in1k.py',
    '../_base_/datasets/imagenet_bs32_pil_resize.py',
    '../_base_/schedules/imagenet_bs256_coslr.py',
    '../_base_/default_runtime.py'
]

# schedule settings
optim_wrapper = dict(
    paramwise_cfg=dict(
        bias_decay_mult=0.0,
        custom_keys={
            'branch_3x3.norm': dict(decay_mult=0.0),
            'branch_1x1.norm': dict(decay_mult=0.0),
            'branch_norm.bias': dict(decay_mult=0.0),
        }))

# schedule settings
param_scheduler = dict(
    type='CosineAnnealingLR',
    T_max=120,
    by_epoch=True,
    begin=0,
    end=120,
    convert_to_iter_based=True)

train_cfg = dict(by_epoch=True, max_epochs=120)

train_pipeline = [
    dict(type='LoadImageFromFile'),
    dict(type='VisionRRC', scale=224),
    dict(type='RandomFlip', prob=0.5, direction='horizontal'),
    dict(type='PackClsInputs'),
]

default_hooks = dict(
    checkpoint=dict(type='CheckpointHook', interval=1, max_keep_ckpts=3))

train_dataloader = dict(dataset=dict(pipeline=train_pipeline), )
