_base_ = [
    '../_base_/models/vig/pyramid_vig_small.py',
    '../_base_/datasets/imagenet_bs128_vig_224.py'
    '../_base_/schedules/imagenet_bs256.py',
    '../_base_/default_runtime.py',
]
