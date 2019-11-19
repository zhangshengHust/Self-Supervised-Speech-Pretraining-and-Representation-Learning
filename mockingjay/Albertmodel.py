import torch 
import numpy as np 
from model import MockingjayLayerNorm,MockingjayInputRepresentations, /
    MockingjayIntermediate,MockingjayLayer,MockingjayOutput, /
    MockingjaySelfAttention,MockingjaySpecPredictionHead, MockingjayInitModel, /
    MockingjayEncoder /


def gelu(x):
    """Implementation of the gelu activation function.
        For information: OpenAI GPT's gelu is slightly different (and gives slightly different results):
        0.5 * x * (1 + torch.tanh(math.sqrt(2 / math.pi) * (x + 0.044715 * torch.pow(x, 3))))
        Also see https://arxiv.org/abs/1606.08415
    """
    return x * 0.5 * (1.0 + torch.erf(x / math.sqrt(2.0)))

def swish(x):
    return x * torch.sigmoid(x)

ACT2FN = {"gelu": gelu, "relu": torch.nn.functional.relu, "swish": swish}

try:
    from apex.normalization.fused_layer_norm import FusedLayerNorm as MockingjayLayerNorm
except ImportError:
    print("Better speed can be achieved with apex installed from https://www.github.com/nvidia/apex .")
    class MockingjayLayerNorm(nn.Module):
        def __init__(self, hidden_size, eps=1e-12):
            """Construct a layernorm module in the TF style (epsilon inside the square root).
            """
            super(MockingjayLayerNorm, self).__init__()
            self.weight = nn.Parameter(torch.ones(hidden_size))
            self.bias = nn.Parameter(torch.zeros(hidden_size))
            self.variance_epsilon = eps

        def forward(self, x):
            u = x.mean(-1, keepdim=True)
            s = (x - u).pow(2).mean(-1, keepdim=True)
            x = (x - u) / torch.sqrt(s + self.variance_epsilon)
            return self.weight * x + self.bias

class AlbertMockingjayIntermediate(nn.Module):
    def __init__(self, config):
        super(MockingjayIntermediate, self).__init__()
        self.dense = nn.Linear(config.hidden_size, config.intermediate_size)
        if isinstance(config.hidden_act, str) or (sys.version_info[0] == 2 and isinstance(config.hidden_act, unicode)):
            self.intermediate_act_fn = ACT2FN[config.hidden_act]
        else:
            self.intermediate_act_fn = config.hidden_act

    def forward(self, hidden_states):
        hidden_states = self.dense(hidden_states)
        hidden_states = self.intermediate_act_fn(hidden_states)
        return hidden_states

class AlbertMockingJayLayer(nn.Module):
    def __init__(self,config, output_attentions=False,keep_multihead_output=False):
        super(AlbertMockingJayLayer,self).__init__():
        self.output_attentions = output_attentions
        self.attention = MockingjayAttention(config, output_attentions=output_attentions,
                                               keep_multihead_output=keep_multihead_output)
        self.intermediate = MockingjayIntermediate(config)
        self.output = MockingjayOutput(config)

    def forward(self, hidden_states, attention_mask, head_mask=None):
        attention_output = self.attention(hidden_states, attention_mask, head_mask)
        if self.output_attentions:
            attentions, attention_output = attention_output
        intermediate_output = self.intermediate(attention_output)
        layer_output = self.output(intermediate_output, attention_output)
        if self.output_attentions:
            return attentions, layer_output
        return layer_output

class AlbertMockingJayEncoder(nn.Module):
    def __init__(self, config, output_attentions=False, keep_multihead_output=False):
        super(MockingjayEncoder, self).__init__()
        self.output_attentions = output_attentions
        layer = MockingjayLayer(config, output_attentions=output_attentions,
                                  keep_multihead_output=keep_multihead_output)
        self.layer = layer
        self.config_hidden_num = config.num_hidden_layers


    def forward(self, hidden_states, attention_mask, output_all_encoded_layers=True, head_mask=None):
        all_encoder_layers = []
        all_attentions = []
        for i, in range(self.config_hidden_num):
            hidden_states = self.layer(hidden_states, attention_mask, head_mask[i])
            if self.output_attentions:
                attentions, hidden_states = hidden_states
                all_attentions.append(attentions)
            if output_all_encoded_layers:
                all_encoder_layers.append(hidden_states)
        if not output_all_encoded_layers:
            all_encoder_layers.append(hidden_states)
        if self.output_attentions:
            return all_attentions, all_encoder_layers
        return all_encoder_layers

class ALbertMockingjayInitModel(nn.Module):
    """ An abstract class to handle weights initialization."""
    def __init__(self, config, *inputs, **kwargs):
        super(ALbertMockingjayInitModel, self).__init__()
        self.config = config

    def init_Mockingjay_weights(self, module):
        """ Initialize the weights.
        """
        if isinstance(module, (nn.Linear, nn.Embedding)):
            # Slightly different from the TF version which uses truncated_normal for initialization
            # cf https://github.com/pytorch/pytorch/pull/5617
            module.weight.data.normal_(mean=0.0, std=self.config.initializer_range)
        elif isinstance(module, MockingjayLayerNorm):
            module.bias.data.zero_()
            module.weight.data.fill_(1.0)
        if isinstance(module, nn.Linear) and module.bias is not None:
            module.bias.data.zero_()

class AlbertMockingjayModel(AlbertMockingjayInitModel):
    """Mockingjay model ("Bidirectional Embedding Representations from a Transformer").

    Params:
        `config`: a MockingjayConfig class instance with the configuration to build a new model
        `intput_dim`: int,  input dimension of model    
        `output_attentions`: If True, also output attentions weights computed by the model at each layer. Default: False
        `keep_multihead_output`: If True, saves output of the multi-head attention module with its gradient.
            This can be used to compute head importance metrics. Default: False

    Inputs:
        `spec_input`: a torch.LongTensor of shape [batch_size, sequence_length, feature_dimension]
            with the selected frames processed as masked frames during training,
            generated by the `process_MAM_data()` function in `solver.py`.
        `pos_enc`: a torch.LongTensor of shape [batch_size, sequence_length, hidden_size],
            generated by the `position_encoding()` function in `solver.py`.
        `attention_mask`: an optional torch.LongTensor of shape [batch_size, sequence_length] with indices
            selected in [0, 1]. It's a mask to be used if the input sequence length is smaller than the max
            input sequence length in the current batch. It's the mask that we typically use for attention when
            a batch has varying length sentences.
        `output_all_encoded_layers`: boolean which controls the content of the `encoded_layers` output as described below. Default: `True`.
        `head_mask`: an optional torch.Tensor of shape [num_heads] or [num_layers, num_heads] with indices between 0 and 1.
            It's a mask to be used to nullify some heads of the transformer. 1.0 => head is fully masked, 0.0 => head is not masked.


    Outputs: Tuple of (encoded_layers, pooled_output)
        `encoded_layers`: controled by `output_all_encoded_layers` argument:
            - `output_all_encoded_layers=True`: outputs a list of the full sequences of encoded-hidden-states
                at the end of each attention block, each encoded-hidden-state is a torch.FloatTensor
                of size [batch_size, sequence_length, hidden_size], i.e [num_hidden_layers, batch_size, sequence_length, hidden_size]
            - `output_all_encoded_layers=False`: outputs only the full sequence of hidden-states corresponding
                to the last attention block of shape [batch_size, sequence_length, hidden_size].


    Example usage:
    ```python
    spec_input = torch.LongTensor(spec_frames)
    pos_enc = torch.LongTensor(position_encoding(seq_len=len(spec_frames)))

    config = MockingjayConfig(hidden_size=768,
             num_hidden_layers=12, num_attention_heads=12, intermediate_size=3072)

    model = MockingjayForMaskedLM(config)
    masked_spec_logits = model(spec_input, pos_enc)
    ```
    """
    def __init__(self, config, input_dim, output_attentions=False, keep_multihead_output=False):
        super(AlbertMockingjayModel, self).__init__(config)
        self.output_attentions = output_attentions
        self.input_representations = MockingjayInputRepresentations(config, input_dim)
        self.encoder = MockingjayEncoder(config, output_attentions=output_attentions,
                                           keep_multihead_output=keep_multihead_output)
        self.apply(self.init_Mockingjay_weights)

    def prune_heads(self, heads_to_prune):
        """ Prunes heads of the model.
            heads_to_prune: dict of {layer_num: list of heads to prune in this layer}
        """
        for layer, heads in heads_to_prune.items():
            self.encoder.layer[layer].attention.prune_heads(heads)

    def get_multihead_outputs(self):
        """ Gather all multi-head outputs.
            Return: list (layers) of multihead module outputs with gradients
        """
        return [layer.attention.self.multihead_output for layer in self.encoder.layer]

    def forward(self, spec_input, pos_enc, attention_mask=None, output_all_encoded_layers=True, head_mask=None):
        if attention_mask is None:
            attention_mask = torch.ones_like(spec_input)

        # We create a 3D attention mask from a 2D tensor mask.
        # Sizes are [batch_size, 1, 1, to_seq_length]
        # So we can broadcast to [batch_size, num_heads, from_seq_length, to_seq_length]
        # this attention mask is more simple than the triangular masking of causal attention
        # used in OpenAI GPT, we just need to prepare the broadcast dimension here.
        extended_attention_mask = attention_mask.unsqueeze(1).unsqueeze(2)

        # Since attention_mask is 1.0 for positions we want to attend and 0.0 for
        # masked positions, this operation will create a tensor which is 0.0 for
        # positions we want to attend and -10000.0 for masked positions.
        # Since we are adding it to the raw scores before the softmax, this is
        # effectively the same as removing these entirely.
        extended_attention_mask = extended_attention_mask.to(dtype=next(self.parameters()).dtype) # fp16 compatibility
        extended_attention_mask = (1.0 - extended_attention_mask) * -10000.0

        # Prepare head mask if needed
        # 1.0 in head_mask indicate we keep the head
        # attention_probs has shape bsz x n_heads x N x N
        # input head_mask has shape [num_heads] or [num_hidden_layers x num_heads]
        # and head_mask is converted to shape [num_hidden_layers x batch x num_heads x seq_length x seq_length]
        if head_mask is not None:
            if head_mask.dim() == 1:
                head_mask = head_mask.unsqueeze(0).unsqueeze(0).unsqueeze(-1).unsqueeze(-1)
                head_mask = head_mask.expand_as(self.config.num_hidden_layers, -1, -1, -1, -1)
            elif head_mask.dim() == 2:
                head_mask = head_mask.unsqueeze(1).unsqueeze(-1).unsqueeze(-1)  # We can specify head_mask for each layer
            head_mask = head_mask.to(dtype=next(self.parameters()).dtype) # switch to fload if need + fp16 compatibility
        else:
            head_mask = [None] * self.config.num_hidden_layers

        input_representations = self.input_representations(spec_input, pos_enc)
        encoded_layers = self.encoder(input_representations,
                                      extended_attention_mask,
                                      output_all_encoded_layers=output_all_encoded_layers,
                                      head_mask=head_mask)
        if self.output_attentions:
            all_attentions, encoded_layers = encoded_layers
        if not output_all_encoded_layers:
            encoded_layers = encoded_layers[-1]
        if self.output_attentions:
            return all_attentions, encoded_layers
        return encoded_layers


class AlbertMockingjayForMaskedAcousticModel(ALbertMockingjayInitModel):
    """Mockingjay model with the masked acoustic modeling head.
    This module comprises the Mockingjay model followed by the masked acoustic modeling head.

    Params:
        `config`: a MockingjayConfig class instance with the configuration to build a new model
        `intput_dim`: int,  input dimension of model
        `output_dim`: int,  output dimension of model
        `output_attentions`: If True, also output attentions weights computed by the model at each layer. Default: False
        `keep_multihead_output`: If True, saves output of the multi-head attention module with its gradient.
            This can be used to compute head importance metrics. Default: False

    Inputs:
        `spec_input`: a torch.LongTensor of shape [batch_size, sequence_length, feature_dimension]
            with the selected frames processed as masked frames during training,
            generated by the `process_MAM_data()` function in `solver.py`.
        `pos_enc`: a torch.LongTensor of shape [batch_size, sequence_length, hidden_size],
            generated by the `position_encoding()` function in `solver.py`.
        `masked_label`: masked acoustic modeling labels - torch.LongTensor of shape [batch_size, sequence_length]
            with indices selected in [1, 0]. All labels set to -1 are ignored, the loss
            is only computed for the labels set to 1.
        `attention_mask`: an optional torch.LongTensor of shape [batch_size, sequence_length] with indices
            selected in [0, 1]. It's a mask to be used if the input sequence length is smaller than the max
            input sequence length in the current batch. It's the mask that we typically use for attention when
            a batch has varying length sentences.
        `spce_label`: a torch.LongTensor of shape [batch_size, sequence_length, feature_dimension]
            which are the ground truth spectrogram used as reconstruction labels.
        `head_mask`: an optional torch.Tensor of shape [num_heads] or [num_layers, num_heads] with indices between 0 and 1.
            It's a mask to be used to nullify some heads of the transformer. 1.0 => head is fully masked, 0.0 => head is not masked.

    Outputs:
        if `spec_label` and `mask_label` is not `None`:
            Outputs the masked acoustic modeling loss and predicted spectrogram.
        if `spec_label` and `mask_label` is `None`:
            Outputs the masked acoustic modeling predicted spectrogram of shape [batch_size, sequence_length, output_dim * downsample_rate].

    Example usage:
    ```python
    spec_input = torch.LongTensor(spec_frames)
    pos_enc = torch.LongTensor(position_encoding(seq_len=len(spec_frames)))

    config = MockingjayConfig(hidden_size=768,
             num_hidden_layers=12, num_attention_heads=12, intermediate_size=3072)

    model = MockingjayForMaskedLM(config)
    masked_spec_logits = model(spec_input, pos_enc)
    ```
    """
    def __init__(self, config, input_dim, output_dim, output_attentions=False, keep_multihead_output=False):
        super(AlbertMockingjayForMaskedAcousticModel, self).__init__(config)
        self.output_attentions = output_attentions
        self.Mockingjay = AlbertMockingjayModel(config, input_dim, output_attentions=output_attentions,
                                      keep_multihead_output=keep_multihead_output)
        self.SpecHead = MockingjaySpecPredictionHead(config, output_dim if output_dim is not None else input_dim)
        self.apply(self.init_Mockingjay_weights)
        self.loss = nn.L1Loss() 

    def forward(self, spec_input, pos_enc, mask_label=None, attention_mask=None, spec_label=None, head_mask=None):
        outputs = self.Mockingjay(spec_input, pos_enc, attention_mask,
                            output_all_encoded_layers=False,
                            head_mask=head_mask)
        if self.output_attentions:
            all_attentions, sequence_output = outputs
        else:
            sequence_output = outputs
        pred_spec, pred_state = self.SpecHead(sequence_output)

        if spec_label is not None and mask_label is not None:
            masked_spec_loss = self.loss(pred_spec.masked_select(mask_label), spec_label.masked_select(mask_label))
            return masked_spec_loss, pred_spec
        elif self.output_attentions:
            return all_attentions, pred_spec
        return pred_spec, pred_state