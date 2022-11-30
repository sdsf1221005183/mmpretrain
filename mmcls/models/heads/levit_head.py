import torch
import torch.nn as nn

from mmcv.cnn import Linear
from mmengine.model import BaseModule

from mmcls.models.heads import ClsHead
from mmcls.registry import MODELS


def build_bn_linear(in_feature, out_feature, bias=True, std=0.02):
    bn = nn.BatchNorm1d(in_feature)
    linear = Linear(in_feature, out_feature, bias=bias)
    nn.init.trunc_normal_(linear.weight, std)
    if bias:
        nn.init.constant_(linear.bias, 0)
    w = bn.weight / (bn.running_var + bn.eps) ** 0.5
    b = bn.bias - bn.running_mean * \
        bn.weight / (bn.running_var + bn.eps) ** 0.5
    w = linear.weight * w[None, :]
    if linear.bias is None:
        b = b @ linear.weight.T
    else:
        b = (linear.weight @ b[:, None]).view(-1) + linear.bias
    m = torch.nn.Linear(w.size(1), w.size(0))
    m.weight.data.copy_(w)
    m.bias.data.copy_(b)
    return m

@MODELS.register_module()
class LeViTClsHead(ClsHead):
    def __init__(self, num_classes=1000, distillation=True, in_channels=None):
        super(LeViTClsHead, self).__init__()
        self.num_classes = num_classes
        self.distillation = distillation
        self.head = build_bn_linear(
            in_channels, num_classes) if num_classes > 0 else nn.Identity()
        if distillation:
            self.head_dist = build_bn_linear(
                in_channels, num_classes) if num_classes > 0 else nn.Identity()

    def forward(self, x):
        x = x.mean(1)  # 2 384
        if self.distillation:
            x = self.head(x), self.head_dist(x)  # 2 16 384 -> 2 1000
            if not self.training:
                x = (x[0] + x[1]) / 2
        else:
            x = self.head(x)
        return x