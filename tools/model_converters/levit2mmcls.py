import argparse
import os.path as osp
from collections import OrderedDict

import mmengine
import torch
from mmengine.runner import load_checkpoint


def convert_levit(args, ckpt):

    new_ckpt = OrderedDict()

    for k, v in list(ckpt.items()):
        new_v = v
        if k.startswith('head_dist'):
            k = k.replace('.l.','.linear.')
            new_k = k.replace('head_dist.', 'head.head_dist.')
            new_ckpt[new_k] = new_v
            continue
        elif k.startswith('head'):
            new_k = k.replace('head.l.', 'head.head.')
            new_ckpt[new_k] = new_v
            continue
        elif k.startswith('patch_embed'):
            strs = k.split('.')
            new_k = "%s.%s.%s.%s" % (strs[0], strs[0], strs[1], strs[-1])
        elif k.startswith('blocks'):
            strs = k.split('.')
            k = k.replace('blocks', 'stages')
            nums = int(strs[1])
            # new_k = "%s.%s.%s.%s.%s" % strs(nums//)
            # if ('attention' not in k) or ('qkv' not in k) or ('proj' not in k):


            # Union
            if 'mlp.fc1' in k:
                new_k = k.replace('mlp.fc1', 'ffn.layers.0.0')
            elif 'mlp.fc2' in k:
                new_k = k.replace('mlp.fc2', 'ffn.layers.1')

            else:
                new_k = k
            new_k = new_k.replace('blocks.', 'layers.')
        elif k.startswith('pos_block'):
            new_k = k.replace('pos_block', 'position_encodings')
            if 'proj.0.' in new_k:
                new_k = new_k.replace('proj.0.', 'proj.')
        elif k.startswith('norm'):
            new_k = k.replace('norm', 'norm_after_stage3')
        else:
            new_k = k
        new_k = 'backbone.' + new_k
        new_ckpt[new_k] = new_v
    return new_ckpt


def main():
    parser = argparse.ArgumentParser(
        description='Convert keys in timm pretrained vit models to '
        'MMClassification style.')
    parser.add_argument('src', help='src model path or url')
    # The dst path must be a full path of the new checkpoint.
    parser.add_argument('dst', help='save path')
    args = parser.parse_args()

    checkpoint = load_checkpoint(args.src, map_location='cpu')

    if 'state_dict' in checkpoint:
        # timm checkpoint
        state_dict = checkpoint['state_dict']
    else:
        state_dict = checkpoint

    weight = convert_levit(args, state_dict)
    mmengine.mkdir_or_exist(osp.dirname(args.dst))
    torch.save(weight, args.dst)


if __name__ == '__main__':
    main()

