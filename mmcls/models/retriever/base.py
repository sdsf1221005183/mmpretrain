# Copyright (c) OpenMMLab. All rights reserved.
from abc import ABCMeta, abstractmethod
from typing import List, Optional

import torch
from mmengine.model import BaseModel
from mmengine.structures import BaseDataElement


class BaseRetriever(BaseModel, metaclass=ABCMeta):
    """Base class for retriever.

    Args:
        init_cfg (dict, optional): Initialization config dict.
            Defaults to None.
        data_preprocessor (dict, optional): The config for preprocessing input
            data. If None, it will use "BaseDataPreprocessor" as type, see
            :class:`mmengine.model.BaseDataPreprocessor` for more details.
            Defaults to None.

    Attributes:
        init_cfg (dict): Initialization config dict.
        data_preprocessor (:obj:`mmengine.model.BaseDataPreprocessor`): An
            extra data pre-processing module, which processes data from
            dataloader to the format accepted by :meth:`forward`.
    """

    def __init__(self,
                 init_cfg: Optional[dict] = None,
                 data_preprocessor: Optional[dict] = None):
        super(BaseRetriever, self).__init__(
            init_cfg=init_cfg, data_preprocessor=data_preprocessor)

    @abstractmethod
    def forward(self,
                inputs: torch.Tensor,
                data_samples: Optional[List[BaseDataElement]] = None,
                mode: str = 'loss'):
        """The unified entry for a forward process in both training and test.

        The method should accept three modes: "feat", "predict" and "loss":

        - "tensor": Forward the whole network and return tensor without any
          post-processing, same as a common nn.Module.
        - "predict": Forward and return the predictions, which are fully
          processed to a list of :obj:`ClsDataSample`.
        - "loss": Forward and return a dict of losses according to the given
          inputs and data samples.

        Note that this method doesn't handle neither back propagation nor
        optimizer updating, which are done in the :meth:`train_step`.

        Args:
            inputs (torch.Tensor, tuple): The input tensor with shape
                (N, C, ...) in general.
            data_samples (List[ClsDataSample], optional): The annotation
                data of every samples. It's required if ``mode="loss"``.
                Defaults to None.
            mode (str): Return what kind of value. Defaults to 'tensor'.

        Returns:
            The return type depends on ``mode``.

            - If ``mode="tensor"``, return a tensor.
            - If ``mode="predict"``, return a list of
              :obj:`mmcls.structures.ClsDataSample`.
            - If ``mode="loss"``, return a dict of tensor.
        """
        pass

    def extract_feat(self, inputs):
        """Extract features from the input tensor with shape (N, C, ...).

        The sub-classes are recommended to implement this method to extract
        features from backbone and neck.

        Args:
            inputs (Tensor): A batch of inputs. The shape of it should be
                ``(num_samples, num_channels, *img_shape)``.
        """
        raise NotImplementedError

    def loss(self, inputs: torch.Tensor,
             data_samples: List[BaseDataElement]) -> dict:
        """Calculate losses from a batch of inputs and data samples.

        Args:
            inputs (torch.Tensor): The input tensor with shape
                (N, C, ...) in general.
            data_samples (List[ClsDataSample]): The annotation data of
                every samples.

        Returns:
            dict[str, Tensor]: a dictionary of loss components
        """
        raise NotImplementedError

    def predict(self,
                inputs: tuple,
                data_samples: Optional[List[BaseDataElement]] = None,
                **kwargs) -> List[BaseDataElement]:
        """Predict results from the extracted features.

        Args:
            inputs (tuple): The features extracted from the backbone.
            data_samples (List[BaseDataElement], optional): The annotation
                data of every samples. Defaults to None.
            **kwargs: Other keyword arguments accepted by the ``predict``
                method of :attr:`head`.
        """
        raise NotImplementedError

    @property
    def similarity_fn(self):
        """Returns a function that calculates the similarity."""
        raise NotImplementedError

    def matching(self,
                 inputs: torch.Tensor,
                 data_samples: Optional[List[BaseDataElement]] = None):
        """Compare the prototype and calculate the similarity.

        Args:
            inputs (torch.Tensor): The input tensor with shape (N, C).
            data_samples (List[BaseDataElement], optional): The annotation
                data of every samples. Defaults to None.
        """
        raise NotImplementedError

    def prepare_prototype(self):
        """Preprocessing the prototype before predict."""
        raise NotImplementedError

    def dump_prototype(self, path):
        """Save the features extracted from the prototype.

        Args:
            path (str): Path to save feature.
        """
        raise NotImplementedError
