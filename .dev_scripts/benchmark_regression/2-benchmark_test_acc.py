import argparse
import os
import os.path as osp
from collections import OrderedDict
from pathlib import Path

import mmcv
from mmcv import Config
from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table

console = Console()
MMCLS_ROOT = Path(__file__).absolute().parents[2]
METRICS_MAP = {
    'Top 1 Accuracy': 'accuracy_top-1',
    'Top 5 Accuracy': 'accuracy_top-5'
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Test all models' accuracy in model-index.yml")
    parser.add_argument(
        'partition', type=str, help='Cluster partition to use.')
    parser.add_argument('checkpoint_root', help='Checkpoint file root path.')
    parser.add_argument(
        '--job-name',
        type=str,
        default='cls-test-benchmark',
        help='Slurm job name prefix')
    parser.add_argument('--port', type=int, default=29666, help='dist port')
    parser.add_argument(
        '--models', nargs='+', type=str, help='Specify model names to run.')
    parser.add_argument(
        '--work-dir',
        default='work_dirs/benchmark_test',
        help='the dir to save metric')
    parser.add_argument(
        '--run', action='store_true', help='run script directly')
    parser.add_argument(
        '--local',
        action='store_true',
        help='run at local instead of cluster.')
    parser.add_argument(
        '--mail', type=str, help='Mail address to watch test status.')
    parser.add_argument(
        '--mail-type',
        nargs='+',
        default=['BEGIN'],
        choices=['NONE', 'BEGIN', 'END', 'FAIL', 'REQUEUE', 'ALL'],
        help='Mail address to watch test status.')
    parser.add_argument(
        '--summary',
        action='store_true',
        help='Summarize benchmark test results.')

    args = parser.parse_args()
    return args


def create_test_job_batch(commands, model_info, args, port, script_name):

    fname = model_info.Name

    config = Path(model_info.Config)
    assert config.exists(), f'{fname}: {config} not found.'

    http_prefix = 'https://download.openmmlab.com/mmclassification/'
    checkpoint_root = Path(args.checkpoint_root)
    checkpoint = checkpoint_root / model_info.Weights[len(http_prefix):]
    assert checkpoint.exists(), f'{fname}: {checkpoint} not found.'

    job_name = f'{args.job_name}_{fname}'
    work_dir = Path(args.work_dir) / fname
    work_dir.mkdir(parents=True, exist_ok=True)

    if args.mail is not None and 'NONE' not in args.mail_type:
        mail_cfg = (f'#SBATCH --mail {args.mail}\n'
                    f'#SBATCH --mail-type {args.mail_type}\n')
    else:
        mail_cfg = ''

    launcher = 'none' if args.local else 'slurm'

    job_script = (f'#!/bin/bash\n'
                  f'#SBATCH --output {work_dir}/job.%j.out\n'
                  f'#SBATCH --partition={args.partition}\n'
                  f'#SBATCH --job-name {job_name}\n'
                  f'#SBATCH --gres=gpu:8\n'
                  f'{mail_cfg}'
                  f'#SBATCH --ntasks-per-node=8\n'
                  f'#SBATCH --ntasks=8\n'
                  f'#SBATCH --cpus-per-task=5\n\n'
                  f'python -u {script_name} {config} {checkpoint} '
                  f'--out={work_dir / "result.pkl"} --metrics accuracy '
                  f'--cfg-option dist_params.port={port} '
                  f'--launcher={launcher}\n')

    with open(work_dir / 'job.sh', 'w') as f:
        f.write(job_script)

    commands.append(f'echo "{config}"')
    if args.local:
        commands.append(f'bash {work_dir}/job.sh')
    else:
        commands.append(f'sbatch {work_dir}/job.sh')

    return work_dir / 'job.sh'


def test(args):
    # parse model-index.yml
    model_index_file = MMCLS_ROOT / 'model-index.yml'
    model_index = Config.fromfile(model_index_file)
    models = OrderedDict()
    for file in model_index.Import:
        metafile = Config.fromfile(MMCLS_ROOT / file)
        models.update({model.Name: model for model in metafile.Models})

    script_name = osp.join('tools', 'test.py')
    port = args.port

    commands = []
    if args.models:
        filter_models = {k: v for k, v in models.items() if k in args.models}
        if len(filter_models) == 0:
            print('No model found, please specify models in:')
            print('\n'.join(models.keys()))
            return
        models = filter_models

    for model_info in models.values():
        script_path = create_test_job_batch(commands, model_info, args, port,
                                            script_name)
        port += 1

    command_str = '\n'.join(commands)

    preview = Table()
    preview.add_column(str(script_path))
    preview.add_column('Shell command preview')
    preview.add_row(
        Syntax.from_path(
            script_path,
            background_color='default',
            line_numbers=True,
            word_wrap=True),
        Syntax(
            command_str,
            'bash',
            background_color='default',
            line_numbers=True,
            word_wrap=True))
    console.print(preview)

    if args.run:
        os.system(command_str)
    else:
        console.print('Please set "--run" to start the job')


def save_summary(summary_data, models_map, work_dir):
    summary_path = work_dir / 'test_benchmark_summary.md'
    file = open(summary_path, 'w')
    headers = [
        'Model', 'Top-1 Expected(%)', 'Top-1 (%)', 'Top-5 Expected (%)',
        'Top-5 (%)', 'Config'
    ]
    file.write('# Test Benchmark Regression Summary\n')
    file.write('| ' + ' | '.join(headers) + ' |\n')
    file.write('|:' + ':|:'.join(['---'] * len(headers)) + ':|\n')
    for model_name, summary in summary_data.items():
        row = [model_name]
        if 'Top 1 Accuracy' in summary:
            metric = summary['Top 1 Accuracy']
            row.append(f"{metric['expect']:.2f}")
            row.append(f"{metric['result']:.2f}")
        else:
            row.extend([''] * 2)
        if 'Top 5 Accuracy' in summary:
            metric = summary['Top 5 Accuracy']
            row.append(f"{metric['expect']:.2f}")
            row.append(f"{metric['result']:.2f}")
        else:
            row.extend([''] * 2)

        model_info = models_map[model_name]
        row.append(model_info.Config)
        file.write('| ' + ' | '.join(row) + ' |\n')
    file.close()
    print('Summary file saved at ' + str(summary_path))


def show_summary(summary_data):
    table = Table(title='Test Benchmark Regression Summary')
    table.add_column('Model')
    for metric in METRICS_MAP:
        table.add_column(f'{metric} (expect)')
        table.add_column(f'{metric}')

    def set_color(value, expect):
        if value >= expect - 0.01:
            return 'green'
        else:
            return 'red'

    for model_name, summary in summary_data.items():
        row = [model_name]
        for metric_key in METRICS_MAP:
            if metric_key in summary:
                metric = summary[metric_key]
                expect = metric['expect']
                result = metric['result']
                color = set_color(result, expect)
                row.append(f'{expect:.2f}')
                row.append(f'[{color}]{result:.2f}[/{color}]')
            else:
                row.extend([''] * 2)
        table.add_row(*row)

    console.print(table)


def summary(args):
    model_index_file = MMCLS_ROOT / 'model-index.yml'
    model_index = Config.fromfile(model_index_file)
    models = OrderedDict()

    for file in model_index.Import:
        metafile = Config.fromfile(MMCLS_ROOT / file)
        models.update({model.Name: model for model in metafile.Models})

    work_dir = Path(args.work_dir)

    summary_data = {}
    for model_name, model_info in models.items():

        if args.models and model_name not in args.models:
            continue

        # Skip if not found result file.
        result_file = work_dir / model_name / 'result.pkl'
        if not result_file.exists():
            continue

        results = mmcv.load(result_file)

        expect_metrics = model_info.Results[0].Metrics

        # extract metrics
        summary = {}
        for key_yml, key_res in METRICS_MAP.items():
            if key_yml in expect_metrics:
                assert key_res in results, \
                    f'{model_name}: No metric "{key_res}"'
                expect_result = float(expect_metrics[key_yml])
                result = float(results[key_res])
                summary[key_yml] = dict(expect=expect_result, result=result)

        summary_data[model_name] = summary

    show_summary(summary_data)
    save_summary(summary_data, models, work_dir)


def main():
    args = parse_args()

    if args.summary:
        summary(args)
    else:
        test(args)


if __name__ == '__main__':
    main()
