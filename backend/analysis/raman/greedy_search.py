import os

import json
import numpy as np
import torch
import torch.nn.functional as F
from rdkit.Chem import Draw
from torch.autograd import Variable
from transformers import AutoTokenizer

from analysis.raman.models.Transformer import make_model
from app.core.logging import get_logger
from config import GLOBAL_CONFIG

logger = get_logger("spec_agent.analysis.raman.greedy_search")
PARENT_PATH = os.path.dirname(os.path.realpath(__file__))
TOKENIZER_PATH = str(GLOBAL_CONFIG["resources"]["raman_tokenizer_root"])
VOCAB_PATH = os.path.join(TOKENIZER_PATH, 'vocab.json')

def get_smiles(label):
    with open(VOCAB_PATH, 'r', encoding='utf-8') as f:
        tokens = {val: key for key, val in json.load(f).items()}
    smiles = ''
    if type(label) == torch.Tensor: label = label.cpu().detach()
    for l in label:
        smiles += tokens[l.data.item()]
    smiles = smiles.replace('</s>', '')
    smiles = smiles.replace('<s>', '')
    smiles = smiles.replace('<unk>', '')
    smiles = smiles.replace('<pad>', '')
    return smiles


def mol_to_image(mol):
    try:
        img = Draw.MolToImage(mol)
    except:
        img = None
    return img


def collate_fn(batch):
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_PATH)
    x = [item[0] for item in batch]
    x = torch.nn.utils.rnn.pad_sequence(x, batch_first=True, padding_value=1).unsqueeze(1)
    y = [item[1] for item in batch]
    y = tokenizer(y, padding=True, truncation=True, return_tensors="pt")
    return x, y


def load_net_state(net, state_dict):
    '''check the keys and load the weight'''
    net_keys = net.state_dict().keys()
    state_dict_keys = state_dict.keys()
    for key in net_keys:
        if key in state_dict_keys:
            # load the weight
            net.state_dict()[key].copy_(state_dict[key])
        else:
            logger.warning("模型权重缺失: %s", key)
    net.load_state_dict(net.state_dict())
    return net


def preprocess_spectrum(x0, x1, intensities,
                        target_range=(400, 4000),
                        target_points=1024,
                        spectype='ir',
                        transmittance=False):
    """
    将输入谱图裁剪到有效范围后重采样为模型所需的固定倒序点列。

    Args:
        x0: 输入谱图第一行对应的 x 值。
        x1: 输入谱图最后一行对应的 x 值。
        intensities: 输入谱图 y 值序列。
        target_range: 算法固定使用的有效 x 范围。
        target_points: 模型要求的固定采样点数。
        spectype: 光谱类型，支持 ``ir`` 或 ``raman``。
        transmittance: IR 模式下是否先将透射率转换为吸光度。

    Returns:
        形状为 ``(1, 1, target_points)`` 的倒序光谱张量。
    """
    intensities = np.asarray(intensities, dtype=np.float32).reshape(-1)
    if intensities.size == 0:
        logger.warning("输入光谱强度不能为空")
        raise ValueError("输入光谱强度不能为空")

    # 把透射率转换为吸光度
    if spectype == 'ir' and transmittance:
        intensities = -np.log10(np.clip(intensities, 0.01, 100) / 100)  # 设置最小0.01%透射率
    max_intensity = np.max(intensities)
    if max_intensity > 0:
        intensities = intensities / max_intensity
    target_min, target_max = target_range
    wavenumbers = np.linspace(x0, x1, intensities.shape[-1])

    # 1. 截断：只保留目标范围内的数据
    mask = (wavenumbers >= target_min) & (wavenumbers <= target_max)
    wavenumbers_clipped = wavenumbers[mask]
    intensities_clipped = intensities[mask]

    if len(wavenumbers_clipped) == 0:
        logger.warning("输入光谱在目标范围 %s 内没有数据", target_range)
        raise ValueError(f"输入光谱在目标范围 {target_range} 内没有数据")

    # 2. 插值前统一为升序，保证 np.interp 的输入单调递增。
    if wavenumbers_clipped[0] > wavenumbers_clipped[-1]:
        wavenumbers_clipped = wavenumbers_clipped[::-1]
        intensities_clipped = intensities_clipped[::-1]

    if len(wavenumbers_clipped) < 2:
        output = np.zeros(target_points, dtype=np.float32)
    else:
        # 3. 创建升序目标波数轴，范围外自动补 0。
        new_wavenumbers = np.linspace(target_min, target_max, target_points)
        output = np.interp(
            new_wavenumbers,
            wavenumbers_clipped,
            intensities_clipped,
            left=0.0,
            right=0.0,
        )

    # 4. 模型固定要求倒序输入，即 4000 -> 400。
    output = output[::-1].copy()
    output = torch.FloatTensor(output)
    output = output.reshape(1, 1, output.shape[-1]) if output.dim() != 3 else output
    return output


# def collate_spectrum(input, start, end, x0=400, x1=4000, dim_target=1024):
#     x_target = np.linspace(x0, x1, dim_target)
#     unit_target = (x1-x0) / (dim_target-1)
#     input = np.array(input)
#     unit_input = (end-start) / (input.shape[-1]-1)

#     if start == x0 and end == x1:
#         if input.shape(-1) == 1024:
#             output = input
#         else:
#             f = interp1d(np.linspace(start, end, unit_input), input, kind='slinear')
#             output = f(x_target)
#     else:
#         if start != x0:
#             num_pad_start = int((x0-start) / unit_input)

#     output = torch.FloatTensor(output)
#     output = output.reshape(1, 1, output.shape[-1]) if output.dim() != 3 else output

def greedy_decode(spectrum, spectrum_length, model, device, bos=0, eos=2, pad_idx=1, max_len=70,
                  repetition_penalty=None):
    if type(model) == torch.nn.parallel.DistributedDataParallel:
        model = model.module
    else:
        model = model
    spectrum_mask = Variable(torch.ones(spectrum.shape[0], 1, spectrum_length, device=device))
    ys = torch.ones(spectrum.shape[0], 1, device=device, dtype=torch.long).fill_(bos)
    memory = model.encode(spectrum, spectrum_mask)
    output = torch.zeros(spectrum.shape[0], max_len, device=device)
    for i in range(max_len - 1):
        tgt_mask = torch.ones_like(ys, device=device)
        out = model.decode(memory, spectrum_mask,
                           Variable(ys),
                           Variable(tgt_mask))
        out = out['decoder_output']
        logits = model.generator(out[:, -1])

        if repetition_penalty is not None:
            tok_seen = list(set(ys[0].tolist()))
            for tok in tok_seen:
                logits[:, tok] /= repetition_penalty
        prob = F.softmax(logits, dim=-1)
        _, next_word = torch.max(prob, dim=-1)
        # next_word = next_word.masked_fill(ys[:, -1]==eos, pad_idx)
        ys = torch.cat([ys, next_word.unsqueeze(1)], dim=1)
        for j in range(len(ys)):
            pad_size = max_len - i - 2
            if ys[j][-1] == eos and not output[j].all():
                if pad_size > 0:
                    output[j] = torch.hstack(
                        [ys[j], torch.ones(pad_size, device=device, dtype=torch.long).fill_(pad_idx)])
                else:
                    output[j] = ys[j]
        # ys = ys.masked_fill(ys==eos, pad_idx)
        if not (output[:, 1:] == torch.zeros(max_len - 1, device=device, dtype=torch.long)).any():
            break
    output = [get_smiles(y) for y in output]
    return output


if __name__ == "__main__":
    spec = torch.randn(1024)  ### input spectrum: 长度1024，波数范围400-4000
    vocab_size = 181
    model, spectrum_length = make_model(vocab_size, N=4, d_model=512)
    beam_size = 10
    checkpoint = 'spec2mol_1/checkpoints/checkpoint.pth'
    device = torch.device('cpu')
    model = load_net_state(model, torch.load(checkpoint, map_location=device, weights_only=True)['model_state']).to(
        device)

    pred = greedy_decode(model,
                         spec,
                         spectrum_length)
    print(pred)
