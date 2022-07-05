# dataset settings
dataset_type = 'StanfordCar'
img_norm_cfg = dict(
    mean=[123.675, 116.28, 103.53], std=[58.395, 57.12, 57.375], to_rgb=True)
train_pipeline = [
    dict(type='LoadImageFromFile'),
    dict(type='Resize', size=600),
    dict(type='RandomCrop', size=448),
    dict(type='RandomFlip', flip_prob=0.5, direction='horizontal'),
    dict(type='Normalize', **img_norm_cfg),
    dict(type='ImageToTensor', keys=['img']),
    dict(type='ToTensor', keys=['gt_label']),
    dict(type='Collect', keys=['img', 'gt_label'])
]
test_pipeline = [
    dict(type='LoadImageFromFile'),
    dict(type='Resize', size=600),
    dict(type='CenterCrop', crop_size=448),
    dict(type='Normalize', **img_norm_cfg),
    dict(type='ImageToTensor', keys=['img']),
    dict(type='Collect', keys=['img'])
]

data = dict(
    samples_per_gpu=8,
    workers_per_gpu=2,
    train=dict(
        type=dataset_type,
        data_prefix='cars_train',
        ann_file='devkit/cars_train_annos.mat',
        pipeline=train_pipeline),
    val=dict(
        type=dataset_type,
        data_prefix='cars_test',
        ann_file='devkit/cars_train_test.mat',
        test_mode=True,
        pipeline=test_pipeline),
    test=dict(
        type=dataset_type,
        data_prefix='cars_test',
        ann_file='devkit/cars_train_test.mat',
        test_mode=True,
        pipeline=test_pipeline))

evaluation = dict(
    interval=1, metric='accuracy',
    save_best='auto')  # save the checkpoint with highest accuracy
