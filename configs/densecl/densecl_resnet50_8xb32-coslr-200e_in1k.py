_base_ = [
    '../_base_/datasets/imagenet_mocov2.py',
    '../_base_/schedules/sgd_coslr-200e_in1k.py',
    '../_base_/default_runtime.py',
]

# model settings
model = dict(
    type='DenseCL',
    queue_len=65536,
    feat_dim=128,
    momentum=0.999,
    loss_lambda=0.5,
    data_preprocessor=dict(
        mean=(123.675, 116.28, 103.53),
        std=(58.395, 57.12, 57.375),
        bgr_to_rgb=True),
    backbone=dict(
        type='ResNet',
        depth=50,
        in_channels=3,
        out_indices=[4],  # 0: conv-1, x: stage-x
        norm_cfg=dict(type='BN')),
    neck=dict(
        type='DenseCLNeck',
        in_channels=2048,
        hid_channels=2048,
        out_channels=128,
        num_grid=None),
    head=dict(
        type='ContrastiveHead',
        loss=dict(type='CrossEntropyLoss'),
        temperature=0.2),
)
find_unused_parameters = True

# runtime settings
default_hooks = dict(
    # only keeps the latest 3 checkpoints
    checkpoint=dict(type='CheckpointHook', interval=10, max_keep_ckpts=3))

# NOTE: `auto_scale_lr` is for automatically scaling LR
# based on the actual training batch size.
auto_scale_lr = dict(base_batch_size=256)
