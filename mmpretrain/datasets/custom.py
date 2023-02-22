# Copyright (c) OpenMMLab. All rights reserved.
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

from mmengine.fileio import (BaseStorageBackend, get_file_backend,
                             list_from_file)
from mmengine.logging import MMLogger

from mmpretrain.registry import DATASETS
from .base_dataset import BaseDataset


def find_folders(
    root: str,
    backend: Optional[BaseStorageBackend] = None
) -> Tuple[List[str], Dict[str, int]]:
    """Find classes by folders under a root.

    Args:
        root (string): root directory of folders
        backend (BaseStorageBackend | None): The file backend of the root.
            If None, auto infer backend from the root path. Defaults to None.

    Returns:
        Tuple[List[str], Dict[str, int]]:

        - folders: The name of sub folders under the root.
        - folder_to_idx: The map from folder name to class idx.
    """
    # Pre-build file backend to prevent verbose file backend inference.
    backend = backend or get_file_backend(root, enable_singleton=True)
    folders = list(
        backend.list_dir_or_file(
            root,
            list_dir=True,
            list_file=False,
            recursive=False,
        ))
    folders.sort()
    folder_to_idx = {folders[i]: i for i in range(len(folders))}
    return folders, folder_to_idx


def get_samples(
    root: str,
    folder_to_idx: Dict[str, int],
    is_valid_file: Callable,
    backend: Optional[BaseStorageBackend] = None,
):
    """Make dataset by walking all images under a root.

    Args:
        root (string): root directory of folders
        folder_to_idx (dict): the map from class name to class idx
        is_valid_file (Callable): A function that takes path of a file
            and check if the file is a valid sample file.
        backend (BaseStorageBackend | None): The file backend of the root.
            If None, auto infer backend from the root path. Defaults to None.

    Returns:
        Tuple[list, set]:

        - samples: a list of tuple where each element is (image, class_idx)
        - empty_folders: The folders don't have any valid files.
    """
    samples = []
    available_classes = set()
    # Pre-build file backend to prevent verbose file backend inference.
    backend = backend or get_file_backend(root, enable_singleton=True)

    for folder_name in sorted(list(folder_to_idx.keys())):
        _dir = backend.join_path(root, folder_name)
        files = backend.list_dir_or_file(
            _dir,
            list_dir=False,
            list_file=True,
            recursive=True,
        )
        for file in sorted(list(files)):
            if is_valid_file(file):
                path = backend.join_path(folder_name, file)
                item = (path, folder_to_idx[folder_name])
                samples.append(item)
                available_classes.add(folder_name)

    empty_folders = set(folder_to_idx.keys()) - available_classes

    return samples, empty_folders


@DATASETS.register_module()
class CustomDataset(BaseDataset):
    """Custom dataset for classification.

    For ``classification`` task, the dataset supports two kinds of annotation
    format.

    1. An annotation file is provided, and each line indicates a sample:

       The sample files: ::

           data_prefix/
           ├── folder_1
           │   ├── xxx.png
           │   ├── xxy.png
           │   └── ...
           └── folder_2
               ├── 123.png
               ├── nsdf3.png
               └── ...

       The annotation file (the first column is the image path and the second
       column is the index of category): ::

            folder_1/xxx.png 0
            folder_1/xxy.png 1
            folder_2/123.png 5
            folder_2/nsdf3.png 3
            ...

       Please specify the name of categories by the argument ``classes``
       or ``metainfo``.

    2. The samples are arranged in the specific way: ::

           data_prefix/
           ├── class_x
           │   ├── xxx.png
           │   ├── xxy.png
           │   └── ...
           │       └── xxz.png
           └── class_y
               ├── 123.png
               ├── nsdf3.png
               ├── ...
               └── asd932_.png

    For ``self-supervised learning`` task, the dataset supports two kinds of
    annotation format.

    1. An annotation file without label is provided, and each line indicates a
    sample:

       The sample files: ::

            data_prefix/
            ├── folder_1
            │   ├── xxx.png
            │   ├── xxy.png
            │   └── ...
            ├── 123.png
            ├── nsdf3.png
            └── ...

       The annotation file lists the image paths: ::

            folder_1/xxx.png
            folder_1/xxy.png
            123.png
            nsdf3.png
            ...

    2. The samples are arranged in one folder with any structure: ::

            data_prefix/
            ├── folder_1
            │   ├── aaa.png
            │   └── ...
            ├── xxx.png
            ├── xxy.png
            ├── xxz.png
            ├── 123.png
            ├── nsdf3.png
            ├── ...
            └── asd932_.png

    If the ``ann_file`` is specified, the dataset will be generated by the
    first way, otherwise, try the second way.

    Args:
        ann_file (str): Annotation file path. Defaults to ''.
        metainfo (dict, optional): Meta information for dataset, such as class
            information. Defaults to None.
        data_root (str): The root directory for ``data_prefix`` and
            ``ann_file``. Defaults to ''.
        data_prefix (str | dict): Prefix for the data. Defaults to ''.
        extensions (Sequence[str]): A sequence of allowed extensions. Defaults
            to ('.jpg', '.jpeg', '.png', '.ppm', '.bmp', '.pgm', '.tif').
        lazy_init (bool): Whether to load annotation during instantiation.
            In some cases, such as visualization, only the meta information of
            the dataset is needed, which is not necessary to load annotation
            file. ``Basedataset`` can skip load annotations to save time by set
            ``lazy_init=False``. Defaults to False.
        **kwargs: Other keyword arguments in :class:`BaseDataset`.
    """

    def __init__(self,
                 ann_file: str = '',
                 metainfo: Optional[dict] = None,
                 data_root: str = '',
                 data_prefix: Union[str, dict] = '',
                 extensions: Sequence[str] = ('.jpg', '.jpeg', '.png', '.ppm',
                                              '.bmp', '.pgm', '.tif'),
                 lazy_init: bool = False,
                 **kwargs):
        assert (ann_file or data_prefix or data_root), \
            'One of `ann_file`, `data_root` and `data_prefix` must '\
            'be specified.'

        self.extensions = tuple(set([i.lower() for i in extensions]))

        super().__init__(
            # The base class requires string ann_file but this class doesn't
            ann_file=ann_file,
            metainfo=metainfo,
            data_root=data_root,
            data_prefix=data_prefix,
            # Force to lazy_init for some modification before loading data.
            lazy_init=True,
            **kwargs)

        # Full initialize the dataset.
        if not lazy_init:
            self.full_init()

    def _find_samples(self):
        """find samples from ``data_prefix``."""
        classes, folder_to_idx = find_folders(self.img_prefix)
        samples, empty_classes = get_samples(
            self.img_prefix,
            folder_to_idx,
            is_valid_file=self.is_valid_file,
        )

        if len(samples) == 0:
            raise RuntimeError(
                f'Found 0 files in subfolders of: {self.data_prefix}. '
                f'Supported extensions are: {",".join(self.extensions)}')

        if self.CLASSES is not None:
            assert len(self.CLASSES) == len(classes), \
                f"The number of subfolders ({len(classes)}) doesn't match " \
                f'the number of specified classes ({len(self.CLASSES)}). ' \
                'Please check the data folder.'
        else:
            self._metainfo['classes'] = tuple(classes)

        if empty_classes:
            logger = MMLogger.get_current_instance()
            logger.warning(
                'Found no valid file in the folder '
                f'{", ".join(empty_classes)}. '
                f"Supported extensions are: {', '.join(self.extensions)}")

        self.folder_to_idx = folder_to_idx

        return samples

    def load_data_list(self):
        """Load image paths and gt_labels."""
        if not self.ann_file:
            samples = self._find_samples()
        else:
            lines = list_from_file(self.ann_file)
            samples = [x.strip().rsplit(' ', 1) for x in lines]

        # Pre-build file backend to prevent verbose file backend inference.
        backend = get_file_backend(self.img_prefix, enable_singleton=True)
        data_list = []
        for filename, gt_label in samples:
            img_path = backend.join_path(self.img_prefix, filename)
            info = {'img_path': img_path, 'gt_label': int(gt_label)}
            data_list.append(info)
        return data_list

    def is_valid_file(self, filename: str) -> bool:
        """Check if a file is a valid sample."""
        return filename.lower().endswith(self.extensions)
