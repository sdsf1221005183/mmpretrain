import argparse
import warnings

import mmcv
import numpy as np
import onnxruntime as ort
from mmcv import DictAction
from mmcv.parallel import MMDataParallel

from mmcls.apis import single_gpu_test
from mmcls.datasets import build_dataloader, build_dataset
from mmcls.models.classifiers import BaseClassifier


class ONNXRuntimeClassifier(BaseClassifier):
    """Wrapper for classifier's inference with ONNXRuntime."""

    def __init__(self, onnx_file, class_names, device_id):
        super(ONNXRuntimeClassifier, self).__init__()
        # check if the input number is coorect.
        sess = ort.InferenceSession(onnx_file)

        self.sess = sess
        self.CLASSES = class_names
        self.device_id = device_id
        self.io_binding = sess.io_binding()
        self.output_names = [_.name for _ in sess.get_outputs()]

    def simple_test(self, img, img_metas, **kwargs):
        raise NotImplementedError('This method is not implemented.')

    def extract_feat(self, imgs):
        raise NotImplementedError('This method is not implemented.')

    def forward_train(self, imgs, **kwargs):
        raise NotImplementedError('This method is not implemented.')

    def forward_test(self, imgs, img_metas, **kwargs):
        assert ort.get_device() == 'GPU', \
            ('The dataset accuracy verification defaultly uses GPU'
                'for inference. Please install the onnxruntime-gpu model.')
        input_data = imgs
        batch_size = imgs.shape[0]
        # set io binding for inputs/outputs
        self.io_binding.bind_input(
            name='input',
            device_type='cuda',
            device_id=self.device_id,
            element_type=np.float32,
            shape=list(imgs.shape),
            buffer_ptr=input_data.data_ptr())
        for name in self.output_names:
            self.io_binding.bind_output(name)
        # run session to get outputs
        self.sess.run_with_iobinding(self.io_binding)
        result = self.io_binding.copy_outputs_to_cpu()[0]

        results = []
        for i in range(batch_size):
            results.append(result[i])
        return results


def parse_args():
    parser = argparse.ArgumentParser(
        description='Use Dataset to Verify Model Accuracy.')
    parser.add_argument('config', help='test config file path')
    parser.add_argument('model', help='filename of the input ONNX model')
    parser.add_argument(
        '--out', type=str, help='output result file in pickle format')
    parser.add_argument(
        '--cfg-options',
        nargs='+',
        action=DictAction,
        help='override some settings in the used config, the key-value pair '
        'in xxx=yyy format will be merged into config file.')
    parser.add_argument(
        '--metrics',
        type=str,
        nargs='+',
        help='evaluation metrics, which depends on the dataset, e.g., '
        '"accuracy", "precision", "recall", "f1_score", "support" for single '
        'label dataset, and "mAP", "CP", "CR", "CF1", "OP", "OR", "OF1" for '
        'multi-label dataset')
    parser.add_argument(
        '--metric-options',
        nargs='+',
        action=DictAction,
        default={},
        help='custom options for evaluation, the key-value pair in xxx=yyy '
        'format will be parsed as a dict metric_options for dataset.evaluate()'
        ' function.')
    parser.add_argument('--show', action='store_true', help='show results')
    parser.add_argument(
        '--show-dir', help='directory where painted images will be saved')
    args = parser.parse_args()
    return args


def main():
    args = parse_args()

    if args.out is not None and not args.out.endswith(('.pkl', '.pickle')):
        raise ValueError('The output file must be a pkl file.')

    cfg = mmcv.Config.fromfile(args.config)
    if args.cfg_options is not None:
        cfg.merge_from_dict(args.cfg_options)

    # build dataset and dataloader
    dataset = build_dataset(cfg.data.test)
    data_loader = build_dataloader(
        dataset,
        samples_per_gpu=cfg.data.samples_per_gpu,
        workers_per_gpu=cfg.data.workers_per_gpu,
        shuffle=False,
        round_up=False)

    # build onnxruntime model and run inference.
    model = ONNXRuntimeClassifier(
        args.model, class_names=dataset.CLASSES, device_id=0)

    model = MMDataParallel(model, device_ids=[0])
    outputs = single_gpu_test(model, data_loader, args.show, args.show_dir)

    if args.metrics:
        results = dataset.evaluate(outputs, args.metrics, args.metric_options)

        for k, v in results.items():
            print(f'\n{k} : {v:.2f}')
    else:
        warnings.warn('Evaluation metrics are not specified.')
        scores = np.vstack(outputs)
        pred_score = np.max(scores, axis=1)
        pred_label = np.argmax(scores, axis=1)
        pred_class = [dataset.CLASSES[lb] for lb in pred_label]
        results = {
            'pred_score': pred_score,
            'pred_label': pred_label,
            'pred_class': pred_class
        }
        if not args.out:
            print('\nthe predicted result for the first element is '
                  f'pred_score = {pred_score[0]:.2f}, '
                  f'pred_label = {pred_label[0]} '
                  f'and pred_class = {pred_class[0]}. '
                  'Specify --out to save all results to files.')
    if args.out:
        print(f'\nwriting results to {args.out}')
        mmcv.dump(results, args.out)


if __name__ == '__main__':
    main()
