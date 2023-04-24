# Copyright (c) OpenMMLab. All rights reserved.
from typing import List

from mmengine import get_file_backend, list_from_file

from mmpretrain.registry import DATASETS
from .base_dataset import BaseDataset
from .categories import FOOD101_CATEGORIES


@DATASETS.register_module()
class Food101(BaseDataset):
    """The Food101 Dataset.

    Support the `Food101 Dataset <https://data.vision.ee.ethz.ch/cvl/datasets_extra/food-101/>`_ Dataset.
    After downloading and decompression, the dataset directory structure is as follows.

    Food101 dataset directory: ::

        food-101 (data_root)/
        ├── images
        │   ├── class_x
        │   │   ├── xx1.jpg
        │   │   ├── xx2.jpg
        │   │   └── ...
        │   ├── class_y
        │   │   ├── yy1.jpg
        │   │   ├── yy2.jpg
        │   │   └── ...
        │   └── ...
        ├── meta
        │   ├── train.txt
        │   └── test.txt
        └── ....

    Args:
        data_root (str): The root directory for Food101 dataset.
        split (str, optional): The dataset split, supports "train" and "test".
            Default to "train".

    Examples:
        >>> from mmpretrain.datasets import Food101
        >>> train_cfg = dict(data_root='data/food-101', split='train')
        >>> train = Food101(**train_cfg)
        >>> train
        Dataset Food101
            Number of samples:  75750
            Number of categories:       101
            Root of dataset:    data/food-101
        >>> test_cfg = dict(data_root='data/food-101', split='test')
        >>> test = Food101(**test_cfg)
        >>> test
        Dataset Food101
            Number of samples:  25250
            Number of categories:       101
            Root of dataset:    data/food-101
    """  # noqa: E501

    METAINFO = {'classes': FOOD101_CATEGORIES}

    def __init__(self, data_root: str, split: str = 'train', **kwargs):

        splits = ['train', 'test']
        if split == 'train':
            ann_file = 'meta/train.txt'
        elif split == 'test':
            ann_file = 'meta/test.txt'
        else:
            raise ValueError(
                f'Split {split} is not in default splits {splits}')
        self.split = split

        test_mode = split == 'test'
        data_prefix = 'images'

        self.backend = get_file_backend(data_root, enable_singleton=True)

        super(Food101, self).__init__(
            ann_file=ann_file,
            data_root=data_root,
            test_mode=test_mode,
            data_prefix=data_prefix,
            **kwargs)

    def load_data_list(self):
        """Load images and ground truth labels."""

        pairs = list_from_file(self.ann_file)
        data_list = []
        for pair in pairs:
            class_name, img_name = pair.split('/')
            img_name = f'{img_name}.jpg'
            img_path = self.backend.join_path(self.img_prefix, class_name,
                                              img_name)
            gt_label = self.METAINFO['classes'].index(class_name)
            info = dict(img_path=img_path, gt_label=gt_label)
            data_list.append(info)
        return data_list

    def extra_repr(self) -> List[str]:
        """The extra repr information of the dataset."""
        body = [
            f'Root of dataset: \t{self.data_root}',
        ]
        return body
