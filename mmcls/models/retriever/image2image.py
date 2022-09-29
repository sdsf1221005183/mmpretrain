# Copyright (c) OpenMMLab. All rights reserved.
from typing import Callable, List, Optional, Union

import torch
import torch.distributed as dist
from mmengine.dist import get_dist_info
from mmengine.runner import Runner
from torch.utils.data import DataLoader

from mmcls.registry import MODELS
from mmcls.structures import ClsDataSample
from .base import BaseRetriever


@MODELS.register_module()
class ImageToImageRetriever(BaseRetriever):
    """Image To Image Retriever for supervised retrieval task.

    Args:
        image_encoder (Union[dict, List[dict]]): Encoder for extracting
            features.
        head (dict, optional): The head module to calculate loss from
            processed features. See :mod:`mmcls.models.heads`. Notice
            that if the head is not set, `loss` method cannot be used.
            Defaults to None.
        pretrained (str, optional): The pretrained checkpoint path,
            support local path and remote path. Defaults to None.
        similarity_fn (Union[str, Callable]): The way that the similarity
            is calculated. If `similarity` is callable, it is used directly
            as the measure function. If it is a string, the appropriate
            method will be used.
            Defaults to "cosine_similarity".
        train_cfg (dict, optional): The training setting. The acceptable
            fields are:

            - augments (List[dict]): The batch augmentation methods to use.
              More details can be found in :mod:`mmcls.model.utils.augment`.

            Defaults to None.
        data_preprocessor (dict, optional): The config for preprocessing input
            data. If None or no specified type, it will use
            "ClsDataPreprocessor" as type. See :class:`ClsDataPreprocessor` for
            more details. Defaults to None.
        topk (int): Return the topk of the retrieval result. `-1` means
            return all.
            Defaults to -1.
        prototype (Union[DataLoader, dict, str, torch.Tensor]): Database to be
            retrieved. The following four types are supported.

            - DataLoader: The original dataloader serves as the prototype.
            - dict: The configuration to construct Dataloader.
            - str: The path of the saved vector.
            - torch.Tensor: The saved tensor whose dimension should be dim.

        init_cfg (dict, optional): the config to control the initialization.
            Defaults to None.
    """

    def __init__(self,
                 image_encoder: Union[dict, List[dict]],
                 head: Optional[dict] = None,
                 pretrained: Optional[str] = None,
                 similarity_fn: Union[str, Callable] = 'cosine_similarity',
                 train_cfg: Optional[dict] = None,
                 data_preprocessor: Optional[dict] = None,
                 topk: int = -1,
                 prototype: Union[DataLoader, dict, str, torch.Tensor] = None,
                 init_cfg: Optional[dict] = None):

        if pretrained is not None:
            init_cfg = dict(type='Pretrained', checkpoint=pretrained)

        if data_preprocessor is None:
            data_preprocessor = {}
        # The build process is in MMEngine, so we need to add scope here.
        data_preprocessor.setdefault('type', 'mmcls.ClsDataPreprocessor')

        if train_cfg is not None and 'augments' in train_cfg:
            # Set batch augmentations by `train_cfg`
            data_preprocessor['batch_augments'] = train_cfg

        super(ImageToImageRetriever, self).__init__(
            init_cfg=init_cfg, data_preprocessor=data_preprocessor)

        self.image_encoder = MODELS.build(image_encoder)

        if head is not None:
            self.head = MODELS.build(head)
        else:
            self.head = None

        self.similarity = similarity_fn

        self.prototype = prototype
        self.prototype_inited = False
        self.prototype_vecs = None
        self.topk = topk

    @property
    def similarity_fn(self):
        """Returns a function that calculates the similarity."""
        # If self.similarity_way is callable, return it directly
        if isinstance(self.similarity, Callable):
            return self.similarity

        if self.similarity == 'cosine_similarity':
            # a is a tensor with shape (N, C)
            # b is a tensor with shape (M, C)
            # "cosine_similarity" will get the matrix of similarity
            # with shape (N, M)
            return lambda a, b: torch.cosine_similarity(
                a.unsqueeze(1), b.unsqueeze(0), dim=-1)
        else:
            raise RuntimeError(f'Invalid function "{self.similarity_way}".')

    def forward(self,
                inputs: torch.Tensor,
                data_samples: Optional[List[ClsDataSample]] = None,
                mode: str = 'tensor'):
        """The unified entry for a forward process in both training and test.

        The method should accept three modes: "tensor", "predict" and "loss":

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
        if mode == 'tensor':
            return self.extract_feat(inputs)
        elif mode == 'loss':
            return self.loss(inputs, data_samples)
        elif mode == 'predict':
            return self.predict(inputs, data_samples)
        else:
            raise RuntimeError(f'Invalid mode "{mode}".')

    def extract_feat(self, inputs):
        """Extract features from the input tensor with shape (N, C, ...).

        Args:
            inputs (Tensor): A batch of inputs. The shape of it should be
                ``(num_samples, num_channels, *img_shape)``.
        Returns:
            Tensor: The output of encoder.
        """

        feat = self.image_encoder(inputs)
        return feat

    def loss(self, inputs: torch.Tensor,
             data_samples: List[ClsDataSample]) -> dict:
        """Calculate losses from a batch of inputs and data samples.

        Args:
            inputs (torch.Tensor): The input tensor with shape
                (N, C, ...) in general.
            data_samples (List[ClsDataSample]): The annotation data of
                every samples.

        Returns:
            dict[str, Tensor]: a dictionary of loss components
        """
        feats = self.extract_feat(inputs)
        return self.head.loss(feats, data_samples)

    def matching(self,
                 inputs: torch.Tensor,
                 data_samples: Optional[List[ClsDataSample]] = None):
        """Compare the prototype and calculate the similarity.

        Args:
            inputs (torch.Tensor): The input tensor with shape (N, C).
            data_samples (List[BaseDataElement], optional): The annotation
                data of every samples. Defaults to None.
        Returns:
            dict: a dictionary of score and prediction label based on fn.
        """
        sim, indices = torch.sort(
            self.similarity_fn(inputs, self.prototype_vecs),
            descending=True,
            dim=-1,
        )
        predictions = {'score': sim, 'pred_label': indices}
        return predictions

    def predict(self,
                inputs: tuple,
                data_samples: Optional[List[ClsDataSample]] = None,
                **kwargs) -> List[ClsDataSample]:
        """Predict results from the extracted features.

        Args:
            inputs (tuple): The features extracted from the backbone.
            data_samples (List[ClsDataSample], optional): The annotation
                data of every samples. Defaults to None.
            **kwargs: Other keyword arguments accepted by the ``predict``
                method of :attr:`head`.
        Returns:
            List[ClsDataSample]: the raw data_samples with
                the predicted results
        """
        if not self.prototype_inited:
            self.prepare_prototype()

        feats = self.extract_feat(inputs)
        if isinstance(feats, tuple):
            feats = feats[-1]

        # Matching of similarity
        result = self.matching(feats)

        pred_scores = result['score']
        pred_labels = result['pred_label']
        if data_samples is not None:
            for data_sample, score, label in zip(data_samples, pred_scores,
                                                 pred_labels):
                data_sample.set_pred_score(score).set_pred_label(label)
        else:
            data_samples = []
            for score, label in zip(pred_scores, pred_labels):
                data_samples.append(ClsDataSample().set_pred_score(
                    score).set_pred_label(label))
        self.post_process(data_samples)
        return data_samples

    def _get_prototype_from_dataloader(self, device):
        data_loader = self.prototype
        num = len(data_loader.dataset)

        self.prototype_vecs = None
        for data_batch in data_loader:
            batch_num = len(data_batch['inputs'])
            data = self.data_preprocessor(data_batch, False)
            feat = self.extract_feat(data['inputs'])
            if isinstance(feat, tuple):
                feat = feat[-1]
            if self.prototype_vecs is None:
                dim = feat.shape[-1]
                self.prototype_vecs = torch.zeros(num, dim).to(device)
            for i in range(batch_num):
                sample_idx = data_batch['data_samples'][i].get('sample_idx')
                self.prototype_vecs[sample_idx] = feat[i]

        rank, world_size = get_dist_info()
        if world_size > 1:
            dist.barrier()
            dist.all_reduce(
                self.prototype_vecs, dist.ReduceOp.SUM, async_op=True)

    @torch.no_grad()
    def prepare_prototype(self):
        """Used in meta testing. This function will be called before the meta
        testing. Obtain the vector based on the prototype.

        - torch.Tensor: The prototype vector is the prototype
        - str: The path of the extracted feature path, parse data structure,
            and generate the prototype feature vector set
        - Dataloader or config: Extract and save the feature vectors according
            to the dataloader
        """

        device = next(self.image_encoder.parameters()).device
        if isinstance(self.prototype, torch.Tensor):
            self.prototype_vecs = self.prototype
            self.prototype_vecs = self.prototype_vecs.to(device)
        elif isinstance(self.prototype, str):
            self.prototype_vecs = torch.load(self.prototype).to(device)
        if isinstance(self.prototype, dict):
            self.prototype = Runner.build_dataloader(self.prototype)
        if isinstance(self.prototype, DataLoader):
            self._get_prototype_from_dataloader(device)
        self.prototype_inited = True

    def post_process(self, data_samples):
        """Intercept the topk results."""
        if self.topk == -1:
            return data_samples
        else:
            topk = min(self.topk, data_samples[0].pred_label.score.shape[0])
            for data_sample in data_samples:
                data_sample.set_pred_score(data_sample.pred_label.score[:topk])
                data_sample.set_pred_label(data_sample.pred_label.label[:topk])
            return data_samples

    def dump_prototype(self, path):
        """Save the features extracted from the prototype to the specific path.

        Args:
            path (str): Path to save feature.
        """
        if not self.prototype_inited:
            self.prepare_prototype()
        torch.save(self.prototype_vecs, path)
