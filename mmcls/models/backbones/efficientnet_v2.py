# Copyright (c) OpenMMLab. All rights reserved.
import math
from functools import partial
from typing import Callable, List, Optional, Tuple

import torch
import torch.nn as nn
import torch.utils.checkpoint as cp
from mmcv.cnn.bricks import DropPath, ConvModule
from mmengine.model import BaseModule, Sequential
from torch import Tensor

from mmcls.models.backbones.base_backbone import BaseBackbone
from mmcls.models.utils import InvertedResidual, SELayer, make_divisible
from mmcls.registry import MODELS


# copy from efficientnetv1
class EdgeResidual(BaseModule):
    """Edge Residual Block.

    Args:
        in_channels (int): The input channels of this module.
        out_channels (int): The output channels of this module.
        mid_channels (int): The input channels of the second convolution.
        kernel_size (int): The kernel size of the first convolution.
            Defaults to 3.
        stride (int): The stride of the first convolution. Defaults to 1.
        se_cfg (dict, optional): Config dict for se layer. Defaults to None,
            which means no se layer.
        with_residual (bool): Use residual connection. Defaults to True.
        conv_cfg (dict, optional): Config dict for convolution layer.
            Defaults to None, which means using conv2d.
        norm_cfg (dict): Config dict for normalization layer.
            Defaults to ``dict(type='BN')``.
        act_cfg (dict): Config dict for activation layer.
            Defaults to ``dict(type='ReLU')``.
        drop_path_rate (float): stochastic depth rate. Defaults to 0.
        with_cp (bool): Use checkpoint or not. Using checkpoint will save some
            memory while slowing down the training speed. Defaults to False.
        init_cfg (dict | list[dict], optional): Initialization config dict.
    """

    def __init__(self,
                 in_channels,
                 out_channels,
                 mid_channels,
                 kernel_size=3,
                 stride=1,
                 se_cfg=None,
                 with_residual=True,
                 conv_cfg=None,
                 norm_cfg=dict(type='BN'),
                 act_cfg=dict(type='ReLU'),
                 drop_path_rate=0.,
                 with_cp=False,
                 init_cfg=None):
        super(EdgeResidual, self).__init__(init_cfg=init_cfg)
        assert stride in [1, 2]
        self.with_cp = with_cp
        self.drop_path = DropPath(
            drop_path_rate) if drop_path_rate > 0 else nn.Identity()
        self.with_se = se_cfg is not None
        self.with_residual = (
                stride == 1 and in_channels == out_channels and with_residual)

        if self.with_se:
            assert isinstance(se_cfg, dict)

        self.conv1 = ConvModule(
            in_channels=in_channels,
            out_channels=mid_channels,
            kernel_size=kernel_size,
            stride=1,
            padding=kernel_size // 2,
            conv_cfg=conv_cfg,
            norm_cfg=norm_cfg,
            act_cfg=act_cfg)

        if self.with_se:
            self.se = SELayer(**se_cfg)

        self.conv2 = ConvModule(
            in_channels=mid_channels,
            out_channels=out_channels,
            kernel_size=1,
            stride=stride,
            padding=0,
            conv_cfg=conv_cfg,
            norm_cfg=norm_cfg,
            act_cfg=None)

    def forward(self, x):

        def _inner_forward(x):
            out = x
            out = self.conv1(out)

            if self.with_se:
                out = self.se(out)

            out = self.conv2(out)

            if self.with_residual:
                return x + self.drop_path(out)
            else:
                return out

        if self.with_cp and x.requires_grad:
            out = cp.checkpoint(_inner_forward, x)
        else:
            out = _inner_forward(x)

        return out


class ConvWSkip(BaseModule):
    def __init__(self,
                 in_channels,
                 out_channels,
                 kernel_size,
                 stride=1,
                 skip=True,
                 drop_path_rate=0.,
                 conv_cfg=dict(type='Conv2dAdaptivePadding'),
                 norm_cfg=dict(type='BN', eps=1e-3, momentum=0.1),
                 act_cfg=dict(type='Swish')):
        self.conv = ConvModule(
            in_channels=in_channels,
            out_channels=out_channels,
            kernel_size=kernel_size,
            stride=stride,
            conv_cfg=conv_cfg,
            norm_cfg=norm_cfg,
            act_cfg=act_cfg)
        self.has_skip = skip and stride == 1 and in_channels == out_channels
        self.drop_path = DropPath(drop_path_rate) if drop_path_rate else nn.Identity()

    def forward(self, x):
        shortcut = x
        x = self.conv(x)
        if self.has_skip:
            x = self.drop_path(x) + shortcut
        return x


@MODELS.register_module()
class EfficientNetV2(BaseBackbone):
    # repeat, kernel, stride, expansion, in_c, out_c, se_ratio, operator
    # b0 is same as base
    arch_settings = {
        'base': [[1, 3, 1, 1, 32, 16, 0, 0], [2, 3, 2, 4, 16, 32, 0, 0],
                 [2, 3, 2, 4, 32, 48, 0, 0], [3, 3, 2, 4, 48, 96, 0.25, 1],
                 [5, 3, 1, 6, 96, 112, 0.25, 1],
                 [8, 3, 2, 6, 112, 192, 0.25, 1]],
        's': [[2, 3, 1, 1, 24, 24, 0, 0], [4, 3, 2, 4, 24, 48, 0, 0],
              [4, 3, 2, 4, 48, 64, 0, 0], [6, 3, 2, 4, 64, 128, 0.25, 1],
              [9, 3, 1, 6, 128, 160, 0.25, 1],
              [15, 3, 2, 6, 160, 256, 0.25, 1]],
        'm': [[3, 3, 1, 1, 24, 24, 0, 0], [5, 3, 2, 4, 24, 48, 0, 0],
              [5, 3, 2, 4, 48, 80, 0, 0], [7, 3, 2, 4, 80, 160, 0.25, 1],
              [14, 3, 1, 6, 160, 176, 0.25, 1],
              [18, 3, 2, 6, 176, 304, 0.25, 1],
              [5, 3, 1, 6, 304, 512, 0.25, 1]],
        'l': [[4, 3, 1, 1, 32, 32, 0, 0], [7, 3, 2, 4, 32, 64, 0, 0],
              [7, 3, 2, 4, 64, 96, 0, 0], [10, 3, 2, 4, 96, 192, 0.25, 1],
              [19, 3, 1, 6, 192, 224, 0.25, 1],
              [25, 3, 2, 6, 224, 384, 0.25, 1],
              [7, 3, 1, 6, 384, 640, 0.25, 1]],
        'xl': [[4, 3, 1, 1, 32, 32, 0, 0], [8, 3, 2, 4, 32, 64, 0, 0],
               [8, 3, 2, 4, 64, 96, 0, 0], [16, 3, 2, 4, 96, 192, 0.25, 1],
               [24, 3, 1, 6, 192, 256, 0.25, 1],
               [32, 3, 2, 6, 256, 512, 0.25, 1],
               [8, 3, 1, 6, 512, 640, 0.25, 1]],
        'b0': [[1, 3, 1, 1, 32, 16, 0, 0], [2, 3, 2, 4, 16, 32, 0, 0],
               [2, 3, 2, 4, 32, 48, 0, 0], [3, 3, 2, 4, 48, 96, 0.25, 1],
               [5, 3, 1, 6, 96, 112, 0.25, 1],
               [8, 3, 2, 6, 112, 192, 0.25, 1]],
        'b1': [[2, 3, 1, 1, 32, 16, 0, 0], [3, 3, 2, 4, 16, 32, 0, 0],
               [3, 3, 2, 4, 32, 48, 0, 0], [4, 3, 2, 4, 48, 96, 0.25, 1],
               [6, 3, 1, 6, 96, 112, 0.25, 1],
               [9, 3, 2, 6, 112, 192, 0.25, 1]],
        'b2': [[2, 3, 1, 1, 32, 16, 0, 0], [3, 3, 2, 4, 16, 32, 0, 0],
               [3, 3, 2, 4, 32, 56, 0, 0], [4, 3, 2, 4, 56, 104, 0.25, 1],
               [6, 3, 1, 6, 104, 120, 0.25, 1],
               [10, 3, 2, 6, 120, 208, 0.25, 1]],
        'b3': [[2, 3, 1, 1, 40, 16, 0, 0], [3, 3, 2, 4, 16, 40, 0, 0],
               [3, 3, 2, 4, 40, 56, 0, 0], [5, 3, 2, 4, 56, 112, 0.25, 1],
               [7, 3, 1, 6, 112, 136, 0.25, 1],
               [12, 3, 2, 6, 136, 232, 0.25, 1]]
    }

    def __init__(self,
<<<<<<< HEAD
                 model_cnf: str = 's',
<<<<<<< HEAD
<<<<<<< HEAD
=======
                 arch: str = 's',
<<<<<<< HEAD
>>>>>>> 54e3689... add config file and modify arch
                 num_features: int = 1280,
<<<<<<< HEAD
<<<<<<< HEAD
                 drop_connect_rate: float = 0.0,
<<<<<<< HEAD
=======
=======
                 num_features: int = 1280,
>>>>>>> 317303a... update model file
                 drop_connect_rate: float = 0.2,
>>>>>>> 8ba74dd... update model file
=======
                 drop_connect_rate: float = 0.2,
>>>>>>> 4a4058c... update config file
=======
                 drop_connect_rate: float = 0.0,
>>>>>>> 6ed2461... update model file
=======
=======
                 out_channels: int = 1280,
>>>>>>> 73d03c1... update efficientnetv2 model file with mmcls style
                 out_indices=(6,),
>>>>>>> 54e3689... add config file and modify arch
                 frozen_stages: int = 0,
                 conv_cfg=dict(type='Conv2dAdaptivePadding'),
                 norm_cfg=dict(type='BN', eps=1e-3, momentum=0.1),
                 act_cfg=dict(type='Swish'),
                 norm_eval: bool = False,
                 with_cp: bool = False,
                 init_cfg=[
                     dict(type='Kaiming', layer='Conv2d'),
                     dict(
                         type='Constant',
                         layer=['_BatchNorm', 'GroupNorm'],
                         val=1)
                 ]):
        super(EfficientNetV2, self).__init__(init_cfg)
        assert arch in self.arch_settings, \
            f'"{arch}" is not one of the arch_settings ' \
            f'({", ".join(self.arch_settings.keys())})'
        self.arch = self.arch_settings[arch]
        self.out_indices = out_indices
        self.frozen_stages = frozen_stages
        self.norm_eval = norm_eval
        self.with_cp = with_cp

        self.layers = nn.ModuleList()
        self.in_channels = arch[0][4]
        self.out_channels = out_channels
        self.conv_cfg = conv_cfg
        self.norm_cfg = norm_cfg
        self.act_cfg = act_cfg
        self.layers.append(
            ConvModule(
                in_channels=3,
                out_channels=self.in_channels,
                kernel_size=3,
                stride=2,
                conv_cfg=self.conv_cfg,
                norm_cfg=self.norm_cfg,
                act_cfg=self.act_cfg))  # the first conv not in arch
        self.make_layer()
        self.layers.append(
            ConvModule(
                in_channels=self.in_channels,
                out_channels=self.out_channels,
                kernel_size=1,
                stride=1,
                conv_cfg=self.conv_cfg,
                norm_cfg=self.norm_cfg,
                act_cfg=self.act_cfg))  # the last conv not in arch

    def make_layer(self):
        layer_setting = self.arch

        total_num_blocks = sum([x[0] for x in layer_setting])
        block_idx = 0
        dpr = [
            x.item()
            for x in torch.linspace(0, self.drop_path_rate, total_num_blocks)
        ]  # stochastic depth decay rule

        for layer_cfg in layer_setting:
            layer = []
            (repeat, kernel_size, stride, expand_ratio, _, out_channels,
             se_ratio, block_type) = layer_cfg
            for i in range(repeat):
                stride = stride if i == 0 else 1
                if expand_ratio == 1 and block_type == 0:
                    layer.append(ConvWSkip
                        (in_channels=self.in_channels,
                         out_channels=out_channels,
                         kernel_size=kernel_size,
                         stride=stride,
                         skip=True,
                         drop_path_rate=dpr[block_idx],
                         conv_cfg=self.conv_cfg,
                         norm_cfg=self.norm_cfg,
                         act_cfg=self.act_cfg))
                    self.in_channels = out_channels
                else:
                    mid_channels = int(self.in_channels * expand_ratio)
                    if se_ratio <= 0:
                        se_cfg = None
                    else:
                        se_cfg = dict(
                            channels=mid_channels,
                            ratio=expand_ratio * (1.0/se_ratio),
                            divisor=1,
                            act_cfg=(self.act_cfg, dict(type='Sigmoid')))
                    if block_type == 0:
                        se_cfg = None
                        block = EdgeResidual
                    else:
                        block = InvertedResidual
                    layer.append(
                        block(
                            in_channels=self.in_channels,
                            out_channels=out_channels,
                            mid_channels=mid_channels,
                            kernel_size=kernel_size,
                            stride=stride,
                            se_cfg=se_cfg,
                            conv_cfg=self.conv_cfg,
                            norm_cfg=self.norm_cfg,
                            act_cfg=self.act_cfg,
                            drop_path_rate=dpr[block_idx],
                            with_cp=self.with_cp))
                    self.in_channels = out_channels
                block_idx += 1
            self.layers.append(Sequential(*layer))

    def forward(self, x: Tensor) -> Tensor:
        outs = []
        for i, layer in enumerate(self.layers):
            x = layer(x)
        outs.append(x)
        return tuple(outs)

    def _freeze_stages(self):
        for i in range(self.frozen_stages):
            m = self.layers[i]
            m.eval()
            for param in m.parameters():
                param.requires_grad = False

    def train(self, mode=True):
        super(EfficientNetV2, self).train(mode)
        self._freeze_stages()
        if mode and self.norm_eval:
            for m in self.modules():
                if isinstance(m, nn.BatchNorm2d):
                    m.eval()
