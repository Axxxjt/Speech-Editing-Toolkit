import math
import random
from functools import partial
from modules.speech_editing.spec_denoiser.diffusion_utils import *
import numpy as np
import torch
import torch.nn.functional as F
from torch import nn
from tqdm import tqdm

from modules.tts.fs import FastSpeech
from modules.speech_editing.commons.mel_encoder import MelEncoder
from modules.speech_editing.edittts.lstm import LSTM_Seq2Seq
from utils.commons.hparams import hparams


class EditTTS(nn.Module):
    def __init__(self, phone_encoder, out_dims):
        super().__init__()
        self.fs = FastSpeech(len(phone_encoder), hparams)
        self.mel_encoder = MelEncoder()
        # self.fs2.decoder = None
        self.mel_bins = out_dims
        self.decoder = LSTM_Seq2Seq(input_dim=hparams['audio_num_mel_bins'], hidden_size=self.fs.hidden_size)

    def forward(self, txt_tokens, time_mel_masks, mel2ph=None, spk_embed=None,
                ref_mels=None, f0=None, uv=None, energy=None, infer=False):
        b, *_, device = *txt_tokens.shape, txt_tokens.device
        ret = {}
        ret = self.fs(txt_tokens, mel2ph, spk_embed, f0, uv, energy,
                       skip_decoder=True, infer=infer)
        decoder_inp = ret['decoder_inp']
        tgt_nonpadding = (mel2ph > 0).float()[:, :, None]
        decoder_inp += self.mel_encoder(ref_mels*(1-time_mel_masks)) * tgt_nonpadding

        nonpadding = (mel2ph != 0).float().unsqueeze(1).unsqueeze(1) # [B, T]
        framelevel_hidden = decoder_inp.transpose(0, 1)
        ref_mels = ref_mels.transpose(0, 1)
        print(framelevel_hidden.shape)
        if not infer:
            self.decoder(framelevel_hidden, ref_mels, framelevel_hidden.shape[0])
            
        else:
            # still working
            pass
        return ret