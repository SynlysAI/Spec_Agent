import os

import numpy as np
import pandas as pd
import torch
from rdkit import Chem

from analysis.raman.beam_search import beam_search
from analysis.raman.greedy_search import greedy_decode, preprocess_spectrum, mol_to_image
from analysis.raman.greedy_search import load_net_state
from analysis.raman.models.Transformer import make_model
from analysis.raman.retrieval import retrieval
from config import GLOBAL_CONFIG

PARENT_PATH = os.path.dirname(os.path.realpath(__file__))
RAMAN_RESOURCES = GLOBAL_CONFIG["resources"]
IR_CHECKPOINT = os.path.join(RAMAN_RESOURCES["raman_checkpoints_root"], "ir_generation.pth")
RAMAN_CHECKPOINT = os.path.join(RAMAN_RESOURCES["raman_checkpoints_root"], "raman_generation.pth")
IR_RETRIEVAL_CHECKPOINT = os.path.join(RAMAN_RESOURCES["raman_checkpoints_root"], "ir_retrieval.pth")
IR_FG_CHECKPOINT = os.path.join(RAMAN_RESOURCES["raman_checkpoints_root"], "ir_fg.pth")
RAMAN_RETRIEVAL_CHECKPOINT = os.path.join(RAMAN_RESOURCES["raman_checkpoints_root"], "raman_retrieval.pth")


def seed_everything(seed):
    import random
    import os
    random.seed(seed)
    os.environ['PYTHONHASHSEED'] = str(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.backends.cudnn.deterministic = True


@torch.no_grad()
def main(spectrum, x0, x1, device, spectype='raman', mode='greedy_decode', k=3, transmittance=False):
    '''
    **Arguments**
    ``spectrum``: 1024-d array / list
    ``x0 & x1``: start and end of input spectrum
    ``spectype``: 'ir' or 'raman'
    ``mode``: 'function_groups', 'greedy_decode' or 'beam_search'
    ``k``: The number of candidates of beam search or retrieval. Default = 3
    ``transmittance``: only for ir, set 'True' to convert to absorbance. Default = False

    '''

    spectrum = preprocess_spectrum(x0, x1, spectrum, spectype=spectype, transmittance=transmittance)
    if not isinstance(spectrum, torch.Tensor):
        spectrum = torch.tensor(spectrum)
    spectrum = spectrum.to(device)

    if mode == 'greedy_decode':
        model, src_length = make_model(181, depth=4, d_model=512, mode=mode)
        if spectype == 'raman':
            checkpoint = ''
        if spectype == 'ir':
            checkpoint = IR_CHECKPOINT
        model = load_net_state(model, torch.load(checkpoint, map_location=device, weights_only=True)['model_state']).to(device)
        output = greedy_decode(spectrum, src_length, model, device)

    elif mode == 'beam_search':
        model, src_length = make_model(181, depth=4, d_model=512, mode=mode)
        if spectype == 'raman':
            checkpoint = RAMAN_CHECKPOINT
        if spectype == 'ir':
            checkpoint = IR_CHECKPOINT
        model = load_net_state(model, torch.load(checkpoint, map_location=device, weights_only=True)['model_state']).to(device)
        output = beam_search(model,
                            spectrum,
                            beam_size=k,
                            device=device,
                            max_len=70,
                            length_penalty=0,
                            temperature=1,
                            stochastic=0)
    elif mode == 'retrieval':
        model, src_length = make_model(181, depth=4, d_model=512, mode=mode)
        if spectype == 'raman':
            checkpoint = RAMAN_RETRIEVAL_CHECKPOINT
        if spectype == 'ir':
            checkpoint = IR_RETRIEVAL_CHECKPOINT
        model = load_net_state(model, torch.load(checkpoint, map_location=device, weights_only=True)['model_state']).to(device)
        db_path = os.path.join(RAMAN_RESOURCES["raman_database_root"], f"{spectype}_db.pkl")
        db = torch.load(db_path, weights_only=0)
        output = retrieval(spectrum, db, model, device, k)

    elif mode == 'function_groups':
        from analysis.raman.models.MLPMixer import resnet
        from analysis.raman.models.fgs import fg_list
        model_params = {
            'depth': 1, 'hidden_size': 1024, 'block_size': 1, 'input_dim': 1024, 'in_channels': 256,
        }
        model = resnet(**model_params).eval()
        if spectype == 'ir':
            checkpoint = IR_FG_CHECKPOINT
            model = load_net_state(model, torch.load(checkpoint, map_location=device, weights_only=True)).to(device)
            output = model(spectrum.float())
            output = output.greater_equal(0.5).squeeze()
            output = [fg_list[i] for i in range(len(output)) if output[i]]
        else:
            output = []
    else:
        output = []
    return output


if __name__ == '__main__':
    seed_everything(2026)
    df = pd.read_pickle(r'E:\github_project\spec2mol\data\test.pkl')
    spectrum = df['spectrum'].values[66]#torch.randn(1024)
    print(df['smiles'].values[66] )
    #
    x0, x1 = 400, 4000
    # # 导出为 x, y 两列的 txt 文件
    # output_dir = r'E:\github_project\Spec_Agent'
    # output_file = os.path.join(output_dir, 'spectrum_test2.txt')
    # x_values = np.linspace(x1, x0, len(spectrum))
    # data_to_save = np.column_stack((x_values, spectrum))
    # np.savetxt(output_file, data_to_save, fmt='%.6f', delimiter='\t')
    # print(f"已导出谱图数据到: {output_file}")
    # print(f"数据点数量: {len(spectrum)}")

    device = torch.device('cpu')
    result = main(spectrum, x0=x0, x1=x1, device=device, spectype='ir', mode='function_groups',)
    print(result, 111)


    # 生成图片
    if type(result) == dict:
        mols = [Chem.MolFromSmiles(s) for s in result['structure']]
        legends = [f'{result['structure'][i]}: {result['score'][i]:.4f}' for i in range(len(result['structure']))]
    elif type(result) == list:
        mols = [Chem.MolFromSmarts(i) for i in result]
        legends = [None]*len(result)
    else:
        result = [result]
        mols = [Chem.MolFromSmiles(s) for s in result]
        legends = result
    result = pd.DataFrame({
        'structure': [mol_to_image(m) for m in mols], # 分子结构的图片
        'legend:': legends, # 作为分子图片的配字
    })
    # # 保存分子为图片：
    # i = 1
    # for m in result['structure'].values:
    #     if m: m.save(f'{i}mol.png')
    #     i += 1
