# # model settings
# model = dict(
#     type='ImageClassifier',
#     backbone=dict(type='MobileNetV2', widen_factor=1.0),
#     neck=dict(type='GlobalAveragePooling'),
#     head=dict(
#         type='LinearClsHead',
#         num_classes=10,
#         in_channels=1280,
#         loss=dict(type='CrossEntropyLoss', use_soft=True, loss_weight=1.0),
#         topk=(1, 5),
#     ),
#     mixup=8
#     )

# model settings
model = dict(
    type='ImageClassifier',
    backbone=dict(
        type='ResNet_CIFAR',
        depth=50,
        num_stages=4,
        out_indices=(3, ),
        style='pytorch'),
    neck=dict(type='GlobalAveragePooling'),
    head=dict(
        type='MultiLabelLinearClsHead',
        num_classes=10,
        in_channels=2048,
        loss=dict(type='CrossEntropyLoss', loss_weight=1.0, use_soft=True)),
    mixup=0.2)
