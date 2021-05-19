# model settings
model = dict(
    type='ImageClassifier',
    backbone=dict(type='MobileNetV3', arch='small'),
    neck=dict(type='GlobalAveragePooling'),
    head=dict(
        type='ConvClsHead',
        num_classes=1000,
        in_channels=576,
        mid_channels=1024,
        dropout_rate=0.2,
        loss=dict(type='CrossEntropyLoss', loss_weight=1.0),
        topk=(1, 5)))
