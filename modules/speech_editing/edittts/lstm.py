import numpy as np
import random
import os, errno
import sys
from tqdm import trange

import torch
import torch.nn as nn
from torch import optim
import torch.nn.functional as F


class lstm_encoder(nn.Module):
    ''' Encodes time-series sequence '''

    def __init__(self, input_dim, hidden_size, num_layers = 1):
        
        '''
        : param input_dim:     the number of features in the input X
        : param hidden_size:    the number of features in the hidden state h
        : param num_layers:     number of recurrent layers (i.e., 2 means there are
        :                       2 stacked LSTMs)
        '''
        
        super(lstm_encoder, self).__init__()
        self.input_dim = input_dim
        self.hidden_size = hidden_size
        self.num_layers = num_layers

        # define LSTM layer
        self.lstm = nn.LSTM(input_size = input_dim, hidden_size = hidden_size,
                            num_layers = num_layers)

    def forward(self, x_input):
        
        '''
        : param x_input:               input of shape (seq_len, # in batch, input_dim)
        : return lstm_out, hidden:     lstm_out gives all the hidden states in the sequence;
        :                              hidden gives the hidden state and cell state for the last
        :                              element in the sequence 
        '''
        
        lstm_out, self.hidden = self.lstm(x_input.view(x_input.shape[0], x_input.shape[1], self.input_dim))
        
        return lstm_out, self.hidden     
    
    def init_hidden(self, batch_size, device):
        
        '''
        initialize hidden state
        : param batch_size:    x_input.shape[1]
        : return:              zeroed hidden state and cell state 
        '''
        
        return (torch.zeros(self.num_layers, batch_size, self.hidden_size).to(device),
                torch.zeros(self.num_layers, batch_size, self.hidden_size).to(device))


class lstm_decoder(nn.Module):
    ''' Decodes hidden state output by encoder '''
    
    def __init__(self, input_dim, hidden_size, num_layers = 1):

        '''
        : param input_dim:     the number of features in the input X
        : param hidden_size:    the number of features in the hidden state h
        : param num_layers:     number of recurrent layers (i.e., 2 means there are
        :                       2 stacked LSTMs)
        '''
        
        super(lstm_decoder, self).__init__()
        self.input_dim = input_dim
        self.hidden_size = hidden_size
        self.num_layers = num_layers

        self.lstm = nn.LSTM(input_size = input_dim, hidden_size = hidden_size,
                            num_layers = num_layers)
        self.linear = nn.Linear(hidden_size, input_dim)           

    def forward(self, x_input, encoder_hidden_states):
        
        '''        
        : param x_input:                    should be 2D (batch_size, input_dim)
        : param encoder_hidden_states:      hidden states
        : return output, hidden:            output gives all the hidden states in the sequence;
        :                                   hidden gives the hidden state and cell state for the last
        :                                   element in the sequence 
 
        '''
        
        lstm_out, self.hidden = self.lstm(x_input.unsqueeze(0), encoder_hidden_states)
        output = self.linear(lstm_out.squeeze(0))     
        
        return output, self.hidden

    def init_hidden(self, batch_size, device):
        
        '''
        initialize hidden state
        : param batch_size:    x_input.shape[1]
        : return:              zeroed hidden state and cell state 
        '''
        
        return (torch.zeros(self.num_layers, batch_size, self.hidden_size).to(device),
                torch.zeros(self.num_layers, batch_size, self.hidden_size).to(device))

class LSTM_Seq2Seq(nn.Module):
    ''' train LSTM encoder-decoder and make predictions '''
    
    def __init__(self, input_dim, hidden_size, training_prediction = 'teacher_forcing', teacher_forcing_ratio = 1.0):

        '''
        : param input_dim:     the number of expected features in the input X
        : param hidden_size:    the number of features in the hidden state h
                : param training_prediction:       type of prediction to make during training ('recursive', 'teacher_forcing', or
        :                                  'mixed_teacher_forcing'); default is 'recursive'
        : param teacher_forcing_ratio:     float [0, 1) indicating how much teacher forcing to use when
        :                                  training_prediction = 'teacher_forcing.' For each batch in training, we generate a random
        :                                  number. If the random number is less than teacher_forcing_ratio, we use teacher forcing.
        :                                  Otherwise, we predict recursively. If teacher_forcing_ratio = 1, we train only using
        :                                  teacher forcing.
        '''

        super(LSTM_Seq2Seq, self).__init__()

        self.training_prediction = training_prediction
        self.teacher_forcing_ratio = teacher_forcing_ratio

        self.input_dim = input_dim
        self.hidden_size = hidden_size

        self.decoder_in = nn.Linear(self.hidden_size, self.input_dim)
        self.forward_decoder = lstm_decoder(input_dim = input_dim, hidden_size = hidden_size)
        self.backward_decoder = lstm_decoder(input_dim = input_dim, hidden_size = hidden_size)


    def forward(self, input_tensor, target_tensor, target_len):
        
        '''
        train lstm encoder-decoder
        
        : param input_tensor:              input data with shape (seq_len, # in batch, number features); PyTorch tensor    
        : param target_tensor:             target data with shape (seq_len, # in batch, number features); PyTorch tensor
        : param target_len:                number of values to predict 
        '''
        input_tensor = self.decoder_in(input_tensor)
        batch_size = input_tensor.size(1)

        # outputs tensor
        forward_outputs = torch.zeros(target_len, batch_size, input_tensor.shape[2])
        backward_outputs = torch.zeros(target_len, batch_size, input_tensor.shape[2])

        # initialize hidden state
        forward_decoder_hidden = self.forward_decoder.init_hidden(batch_size, input_tensor.device)
        backward_decoder_hidden = self.backward_decoder.init_hidden(batch_size, input_tensor.device)

        # decoder with teacher forcing
        forward_decoder_input = input_tensor[-1, :, :]   # shape: (batch_size, input_dim)
        backward_decoder_input = input_tensor[-1, :, :]   # shape: (batch_size, input_dim)

        for t in range(target_len): 
            forward_decoder_output, forward_decoder_hidden = self.forward_decoder(forward_decoder_input, forward_decoder_hidden)
            backward_decoder_output, backward_decoder_hidden = self.backward_decoder(backward_decoder_input, backward_decoder_hidden)
            forward_outputs[t] = forward_decoder_output
            backward_outputs[t] = backward_decoder_output
            forward_decoder_input = target_tensor[t, :, :]
            backward_decoder_input = target_tensor[t, :, :]
        import sys
        sys.exit(0)

        return outputs

    def predict(self, input_tensor, target_len):
        
        '''
        : param input_tensor:      input data (seq_len, input_dim); PyTorch tensor 
        : param target_len:        number of target values to predict 
        : return np_outputs:       np.array containing predicted values; prediction done recursively 
        '''

        # encode input_tensor
        input_tensor = input_tensor.unsqueeze(1)     # add in batch size of 1
        encoder_output, encoder_hidden = self.encoder(input_tensor)

        # initialize tensor for predictions
        outputs = torch.zeros(target_len, input_tensor.shape[2])

        # decode input_tensor
        decoder_input = input_tensor[-1, :, :]
        decoder_hidden = encoder_hidden
        
        for t in range(target_len):
            decoder_output, decoder_hidden = self.decoder(decoder_input, decoder_hidden)
            outputs[t] = decoder_output.squeeze(0)
            decoder_input = decoder_output
            
        np_outputs = outputs.detach().numpy()
        
        return np_outputs