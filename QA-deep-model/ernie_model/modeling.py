from pytools import memoize_method
import torch
import torch.nn.functional as F
import pytorch_pretrained_bert
import modeling_util
from knowledge_bert import BertTokenizer
import json
import sys
import os


class BertRanker(torch.nn.Module):
    def __init__(self,config):
        super().__init__()
        #self.BERT_MODEL = 'bert-base-uncased'
        self.config = config
        self.BERT_MODEL = os.path.abspath(sys.argv[0] + '/../bert_base')
        self.KNOW_BERT_MODEL = os.path.abspath(sys.argv[0] + '/../knowledge_bert_base')
        # self.BERT_MODEL = 'bert_base'
        # self.KNOW_BERT_MODEL = 'knowledge_bert_base'
        self.CHANNELS = 12 + 1 # from bert-base-uncased
        self.BERT_SIZE = 768 # from bert-base-uncased
        self.bert = CustomBertModel.from_pretrained(self.BERT_MODEL)
        self.tokenizer = BertTokenizer.from_pretrained(self.KNOW_BERT_MODEL)
        self.entity2id = modeling_util.get_entid(self.config["kg_path"]+'/entity2id.txt')
        
        

    def forward(self, **inputs):
        raise NotImplementedError

    def save(self, path):
        state = self.state_dict(keep_vars=True)
        for key in list(state):
            if state[key].requires_grad:
                state[key] = state[key].data
            else:
                del state[key]
        torch.save(state, path)

    def load(self, path):
        self.load_state_dict(torch.load(path), strict=False)

    def tok_to_text(self):
        idx_to_tok = {}
        for tok,idx in self.tokenizer.vocab.items():
            idx_to_tok[idx] = tok
        return idx_to_tok

    @memoize_method
    def tokenize(self, text,ents):#,ents
        '''text_ann = tagme.annotate(text)
        if text_ann:
            ents = modeling_util.get_ents(text_ann,ent_map)
        else:
            print('request error!')
            ents = []'''
        #print(type(ents))
        tokens, entities = self.tokenizer.tokenize(text, ents)
        toks = [self.tokenizer.vocab[t] for t in tokens]
        input_ent = []
        for ent in entities:
            if ent != "UNK" and ent in self.entity2id:
                input_ent.append(self.entity2id[ent])
            else:
                input_ent.append(-1)
        
        return toks,input_ent
    


    def encode_bert(self, query_tok, query_mask, doc_tok, doc_mask):
        
        BATCH, QLEN = query_tok.shape
        DIFF = 3 # = [CLS] and 2x[SEP]        
        maxlen = self.bert.config.max_position_embeddings
        MAX_DOC_TOK_LEN = maxlen - QLEN - DIFF

        doc_toks, sbcount = modeling_util.subbatch(doc_tok, MAX_DOC_TOK_LEN)
        doc_mask, _ = modeling_util.subbatch(doc_mask, MAX_DOC_TOK_LEN)

        query_toks = torch.cat([query_tok] * sbcount, dim=0)
        query_mask = torch.cat([query_mask] * sbcount, dim=0)

        CLSS = torch.full_like(query_toks[:, :1], self.tokenizer.vocab['[CLS]'])
        SEPS = torch.full_like(query_toks[:, :1], self.tokenizer.vocab['[SEP]'])
        ONES = torch.ones_like(query_mask[:, :1])
        NILS = torch.zeros_like(query_mask[:, :1])

        # build BERT input sequences
        toks = torch.cat([CLSS, query_toks, SEPS, doc_toks, SEPS], dim=1)
        mask = torch.cat([ONES, query_mask, ONES, doc_mask, ONES], dim=1)
        segment_ids = torch.cat([NILS] * (2 + QLEN) + [ONES] * (1 + doc_toks.shape[1]), dim=1)
        toks[toks == -1] = 0 # remove padding (will be masked anyway)

        # execute BERT model
        result = self.bert(toks, segment_ids.long(), mask)

        # extract relevant subsequences for query and doc
        query_results = [r[:BATCH, 1:QLEN+1] for r in result]
        doc_results = [r[:, QLEN+2:-1] for r in result]
        doc_results = [modeling_util.un_subbatch(r, doc_tok, MAX_DOC_TOK_LEN) for r in doc_results]

        # build CLS representation
        cls_results = []
        for layer in result:
            cls_output = layer[:, 0]
            cls_result = []
            for i in range(cls_output.shape[0] // BATCH):
                cls_result.append(cls_output[i*BATCH:(i+1)*BATCH])
            cls_result = torch.stack(cls_result, dim=2).mean(dim=2)
            cls_results.append(cls_result)

        return cls_results, query_results, doc_results
    
class SciBertRanker(torch.nn.Module):
    def __init__(self,config):
        super().__init__()
        self.config = config
        self.BERT_MODEL = os.path.abspath(sys.argv[0] + '/../sci_bert_base')
        self.KNOW_BERT_MODEL = os.path.abspath(sys.argv[0] + '/../sci_knowledge_bert_base')
        self.CHANNELS = 12 + 1 # from bert-base-uncased
        self.BERT_SIZE = 768 # from bert-base-uncased
        self.bert = CustomBertModel.from_pretrained(self.BERT_MODEL)
        self.tokenizer = BertTokenizer.from_pretrained(self.KNOW_BERT_MODEL)
        self.entity2id = modeling_util.get_entid(self.config["kg_path"] + '/entity2id.txt')
        
        

    def forward(self, **inputs):
        raise NotImplementedError

    def save(self, path):
        state = self.state_dict(keep_vars=True)
        for key in list(state):
            if state[key].requires_grad:
                state[key] = state[key].data
            else:
                del state[key]
        torch.save(state, path)

    def load(self, path):
        self.load_state_dict(torch.load(path), strict=False)
        
    def tok_to_text(self):
        idx_to_tok = {}
        for tok,idx in self.tokenizer.vocab.items():
            idx_to_tok[idx] = tok
        return idx_to_tok

    @memoize_method
    def tokenize(self, text,ents):#,ents
        '''text_ann = tagme.annotate(text)
        if text_ann:
            ents = modeling_util.get_ents(text_ann,ent_map)
        else:
            print('request error!')
            ents = []'''
        #print(type(ents))
        tokens, entities = self.tokenizer.tokenize(text, ents)
        toks = [self.tokenizer.vocab[t] for t in tokens]
        input_ent = []
        for ent in entities:
            if ent != "UNK" and ent in self.entity2id:
                input_ent.append(self.entity2id[ent])
            else:
                input_ent.append(-1)
        
        return toks,input_ent
    


    def encode_bert(self, query_tok, query_mask, doc_tok, doc_mask):
        
        BATCH, QLEN = query_tok.shape
        DIFF = 3 # = [CLS] and 2x[SEP]        
        maxlen = self.bert.config.max_position_embeddings
        MAX_DOC_TOK_LEN = maxlen - QLEN - DIFF

        doc_toks, sbcount = modeling_util.subbatch(doc_tok, MAX_DOC_TOK_LEN)
        doc_mask, _ = modeling_util.subbatch(doc_mask, MAX_DOC_TOK_LEN)

        query_toks = torch.cat([query_tok] * sbcount, dim=0)
        query_mask = torch.cat([query_mask] * sbcount, dim=0)

        CLSS = torch.full_like(query_toks[:, :1], self.tokenizer.vocab['[CLS]'])
        SEPS = torch.full_like(query_toks[:, :1], self.tokenizer.vocab['[SEP]'])
        ONES = torch.ones_like(query_mask[:, :1])
        NILS = torch.zeros_like(query_mask[:, :1])

        # build BERT input sequences
        toks = torch.cat([CLSS, query_toks, SEPS, doc_toks, SEPS], dim=1)
        mask = torch.cat([ONES, query_mask, ONES, doc_mask, ONES], dim=1)
        segment_ids = torch.cat([NILS] * (2 + QLEN) + [ONES] * (1 + doc_toks.shape[1]), dim=1)
        toks[toks == -1] = 0 # remove padding (will be masked anyway)

        # execute BERT model
        result = self.bert(toks, segment_ids.long(), mask)

        # extract relevant subsequences for query and doc
        query_results = [r[:BATCH, 1:QLEN+1] for r in result]
        doc_results = [r[:, QLEN+2:-1] for r in result]
        doc_results = [modeling_util.un_subbatch(r, doc_tok, MAX_DOC_TOK_LEN) for r in doc_results]

        # build CLS representation
        cls_results = []
        for layer in result:
            cls_output = layer[:, 0]
            cls_result = []
            for i in range(cls_output.shape[0] // BATCH):
                cls_result.append(cls_output[i*BATCH:(i+1)*BATCH])
            cls_result = torch.stack(cls_result, dim=2).mean(dim=2)
            cls_results.append(cls_result)

        return cls_results, query_results, doc_results    

class BertTransformRankder(BertRanker):
    def __init__(self,config):
        super().__init__(config)
        # self.ATTEN_SIZE = 500
        # self.ENTITY_SIZE = 100
        self.ATTEN_SIZE = config["atten_dim"]
        self.ENTITY_SIZE = config["entity_dim"]
        self.transform = torch.nn.Linear(self.BERT_SIZE,self.ATTEN_SIZE)
        self.transform_ent = torch.nn.Linear(self.ENTITY_SIZE,self.ATTEN_SIZE)
        
    def transform_embed(self,query_reps,doc_reps,query_entity,doc_entity):
        query_trans_reps = []
        doc_trans_reps = []
        query_entity = self.transform_ent(query_entity)#batch*q_len*atten_size
        doc_entity = self.transform_ent(doc_entity)
        for query_embed,doc_embed in zip(query_reps,doc_reps):
            
            query_embed = self.transform(query_embed)
            doc_embed = self.transform(doc_embed)
            

            query_reps =  torch.relu(query_embed+query_entity)#batch*q_len*dim
            doc_reps =  torch.relu(doc_embed+doc_entity)
            
            query_trans_reps.append(query_reps)
            doc_trans_reps.append(doc_reps)
            
        return query_trans_reps,doc_trans_reps    

    
class SciBertTransformRankder(SciBertRanker):
    def __init__(self,config):
        super().__init__(config)
        # self.ATTEN_SIZE = 500
        # self.ENTITY_SIZE = 100
        self.ATTEN_SIZE = config["atten_dim"]
        self.ENTITY_SIZE = config["entity_dim"]
        self.transform = torch.nn.Linear(self.BERT_SIZE,self.ATTEN_SIZE)
        self.transform_ent = torch.nn.Linear(self.ENTITY_SIZE,self.ATTEN_SIZE)
        
    def transform_embed(self,query_reps,doc_reps,query_entity,doc_entity):
        query_trans_reps = []
        doc_trans_reps = []
        query_entity = self.transform_ent(query_entity)#batch*q_len*atten_size
        doc_entity = self.transform_ent(doc_entity)
        for query_embed,doc_embed in zip(query_reps,doc_reps):
            
            query_embed = self.transform(query_embed)
            doc_embed = self.transform(doc_embed)
            

            query_reps =  torch.relu(query_embed+query_entity)#batch*q_len*dim
            doc_reps =  torch.relu(doc_embed+doc_entity)
            
            query_trans_reps.append(query_reps)
            doc_trans_reps.append(doc_reps)
            
        return query_trans_reps,doc_trans_reps     

class CedrPacrrTransformRanker(BertTransformRankder):
    def __init__(self,config):
        super().__init__(config)
        # QLEN = 10
        QLEN = config["text1_maxlen"]
        KMAX = 2
        NFILTERS = 32
        MINGRAM = 1
        MAXGRAM = 3
        self.simmat = modeling_util.SimmatModule()
        self.ngrams = torch.nn.ModuleList()
        self.rbf_bank = None
        for ng in range(MINGRAM, MAXGRAM+1):
            ng = modeling_util.PACRRConvMax2dModule(ng, NFILTERS, k=KMAX, channels=self.CHANNELS)
            self.ngrams.append(ng)
        qvalue_size = len(self.ngrams) * KMAX
        self.linear1 = torch.nn.Linear(self.BERT_SIZE + QLEN * qvalue_size, 32)
        #self.linear1 = torch.nn.Linear(QLEN * qvalue_size, 32)
        self.linear2 = torch.nn.Linear(32, 32)
        self.linear3 = torch.nn.Linear(32, 1)



    def forward(self, query_tok, query_mask, doc_tok, doc_mask,query_entity,doc_entity):
        cls_reps, query_reps, doc_reps = self.encode_bert(query_tok, query_mask, doc_tok, doc_mask)

        query_trans_reps,doc_trans_reps = self.transform_embed(query_reps,doc_reps,query_entity,doc_entity)

        simmat = self.simmat(query_trans_reps, doc_trans_reps, query_tok, doc_tok)
        scores = [ng(simmat) for ng in self.ngrams]
        scores = torch.cat(scores, dim=2)
        scores = scores.reshape(scores.shape[0], scores.shape[1] * scores.shape[2])
        scores = torch.cat([scores, cls_reps[-1]], dim=1)
        rel = F.relu(self.linear1(scores))
        rel = F.relu(self.linear2(rel))
        rel = self.linear3(rel)


        return rel
    
class SciCedrPacrrTransformRanker(SciBertTransformRankder):
    def __init__(self,config):
        super().__init__(config)
        # QLEN = 10
        QLEN = config["text1_maxlen"]
        KMAX = 2
        NFILTERS = 32
        MINGRAM = 1
        MAXGRAM = 3
        self.simmat = modeling_util.SimmatModule()
        self.ngrams = torch.nn.ModuleList()
        self.rbf_bank = None
        for ng in range(MINGRAM, MAXGRAM+1):
            ng = modeling_util.PACRRConvMax2dModule(ng, NFILTERS, k=KMAX, channels=self.CHANNELS)
            self.ngrams.append(ng)
        qvalue_size = len(self.ngrams) * KMAX
        self.linear1 = torch.nn.Linear(self.BERT_SIZE + QLEN * qvalue_size, 32)
        #self.linear1 = torch.nn.Linear(QLEN * qvalue_size, 32)
        self.linear2 = torch.nn.Linear(32, 32)
        self.linear3 = torch.nn.Linear(32, 1)
        
        

    def forward(self, query_tok, query_mask, doc_tok, doc_mask,query_entity,doc_entity):
        cls_reps, query_reps, doc_reps = self.encode_bert(query_tok, query_mask, doc_tok, doc_mask)
        
        query_trans_reps,doc_trans_reps = self.transform_embed(query_reps,doc_reps,query_entity,doc_entity)        
        
        simmat = self.simmat(query_trans_reps, doc_trans_reps, query_tok, doc_tok)
        scores = [ng(simmat) for ng in self.ngrams]
        scores = torch.cat(scores, dim=2)
        scores = scores.reshape(scores.shape[0], scores.shape[1] * scores.shape[2])
        scores = torch.cat([scores, cls_reps[-1]], dim=1)
        rel = F.relu(self.linear1(scores))
        rel = F.relu(self.linear2(rel))
        rel = self.linear3(rel)
        return rel      
    
class CedrKnrmTransformRanker(BertTransformRankder):
    def __init__(self,config):
        super().__init__(config)
        
        MUS,SIGMAS = modeling_util.init_kernels(21)
        
        #MUS = [-0.9, -0.7, -0.5, -0.3, -0.1, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0]
        #SIGMAS = [0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.001]      
        self.simmat = modeling_util.SimmatModule()
        
        
        self.kernels = modeling_util.KNRMRbfKernelBank(MUS, SIGMAS)
        self.combine = torch.nn.Linear(self.kernels.count() * self.CHANNELS + self.BERT_SIZE, 1)#

    def forward(self, query_tok, query_mask, doc_tok, doc_mask,query_entity,doc_entity):#
        cls_reps, query_reps, doc_reps = self.encode_bert(query_tok, query_mask, doc_tok, doc_mask)        
        
        query_trans_reps,doc_trans_reps = self.transform_embed(query_reps,doc_reps,query_entity,doc_entity) 
        
        simmat = self.simmat(query_trans_reps, doc_trans_reps, query_tok, doc_tok)
        kernels = self.kernels(simmat)
        BATCH, KERNELS, VIEWS, QLEN, DLEN = kernels.shape
        kernels = kernels.reshape(BATCH, KERNELS * VIEWS, QLEN, DLEN)
        simmat = simmat.reshape(BATCH, 1, VIEWS, QLEN, DLEN) \
                       .expand(BATCH, KERNELS, VIEWS, QLEN, DLEN) \
                       .reshape(BATCH, KERNELS * VIEWS, QLEN, DLEN)
        result = kernels.sum(dim=3) # sum over document
        mask = (simmat.sum(dim=3) != 0.) # which query terms are not padding?
        result = torch.where(mask, (result + 1e-6).log(), mask.float())
        result = result.sum(dim=2) # sum over query terms
        result = torch.cat([result, cls_reps[-1]], dim=1)#
        scores = self.combine(result) # linear combination over kernels
        return scores  

class SciCedrKnrmTransformRanker(SciBertTransformRankder):
    def __init__(self,config):
        super().__init__(config)
        
        MUS,SIGMAS = modeling_util.init_kernels(21)
        
        #MUS = [-0.9, -0.7, -0.5, -0.3, -0.1, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0]
        #SIGMAS = [0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.001]
        self.simmat = modeling_util.SimmatModule()
        
        
        self.kernels = modeling_util.KNRMRbfKernelBank(MUS, SIGMAS)
        self.combine = torch.nn.Linear(self.kernels.count() * self.CHANNELS + self.BERT_SIZE, 1)#

    def forward(self, query_tok, query_mask, doc_tok, doc_mask,query_entity,doc_entity):#
        cls_reps, query_reps, doc_reps = self.encode_bert(query_tok, query_mask, doc_tok, doc_mask)        
        
        query_trans_reps,doc_trans_reps = self.transform_embed(query_reps,doc_reps,query_entity,doc_entity) 
        
        simmat = self.simmat(query_trans_reps, doc_trans_reps, query_tok, doc_tok)
        kernels = self.kernels(simmat)
        BATCH, KERNELS, VIEWS, QLEN, DLEN = kernels.shape
        kernels = kernels.reshape(BATCH, KERNELS * VIEWS, QLEN, DLEN)
        simmat = simmat.reshape(BATCH, 1, VIEWS, QLEN, DLEN) \
                       .expand(BATCH, KERNELS, VIEWS, QLEN, DLEN) \
                       .reshape(BATCH, KERNELS * VIEWS, QLEN, DLEN)
        result = kernels.sum(dim=3) # sum over document
        mask = (simmat.sum(dim=3) != 0.) # which query terms are not padding?
        result = torch.where(mask, (result + 1e-6).log(), mask.float())
        result = result.sum(dim=2) # sum over query terms
        result = torch.cat([result, cls_reps[-1]], dim=1)#
        scores = self.combine(result) # linear combination over kernels
        return scores    
    
# class CedrKnrmMeanRanker(BertRanker):
#     def __init__(self):
#         super().__init__()
#
#         #MUS,SIGMAS = modeling_util.init_kernels(21)
#
#         MUS = [-0.9, -0.7, -0.5, -0.3, -0.1, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0]
#         SIGMAS = [0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.001]
#         self.bert_ranker = VanillaBertRanker()
#         self.simmat = modeling_util.SimmatModule()
#
#         self.ENTITY_SIZE = 200
#         self.kernels = modeling_util.KNRMRbfKernelBank(MUS, SIGMAS)
#         self.combine = torch.nn.Linear(self.kernels.count() * self.CHANNELS + self.BERT_SIZE+self.ENTITY_SIZE*2, 1)#
#
#     def forward(self, query_tok, query_mask, doc_tok, doc_mask,query_entity,doc_entity):#
#         cls_reps, query_reps, doc_reps = self.encode_bert(query_tok, query_mask, doc_tok, doc_mask)
#
#         query_ent = query_entity.mean(dim=1)
#         doc_ent = doc_entity.mean(dim=1)
#         #query_trans_reps,doc_trans_reps = self.transform_embed(query_reps,doc_reps,query_entity,doc_entity)
#
#         simmat = self.simmat(query_reps, doc_reps, query_tok, doc_tok)
#         kernels = self.kernels(simmat)
#         BATCH, KERNELS, VIEWS, QLEN, DLEN = kernels.shape
#         kernels = kernels.reshape(BATCH, KERNELS * VIEWS, QLEN, DLEN)
#         simmat = simmat.reshape(BATCH, 1, VIEWS, QLEN, DLEN) \
#                        .expand(BATCH, KERNELS, VIEWS, QLEN, DLEN) \
#                        .reshape(BATCH, KERNELS * VIEWS, QLEN, DLEN)
#         result = kernels.sum(dim=3) # sum over document
#         mask = (simmat.sum(dim=3) != 0.) # which query terms are not padding?
#         result = torch.where(mask, (result + 1e-6).log(), mask.float())
#         result = result.sum(dim=2) # sum over query terms
#         result = torch.cat([result, cls_reps[-1],query_ent,doc_ent], dim=1)#
#         scores = self.combine(result) # linear combination over kernels
#         return scores
#
# class CedrConvKnrmRanker(BertRanker):
#     def __init__(self):
#         super().__init__()
#
#         MUS,SIGMAS = modeling_util.init_kernels(11)
#         self.max_gram = 3
#         #MUS = [-0.9, -0.7, -0.5, -0.3, -0.1, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0]
#         #SIGMAS = [0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.001]
#         self.bert_ranker = VanillaBertRanker()
#         self.q_convs,self.d_convs = modeling_util.init_KnrmConvModule(self.max_gram,768,128)
#
#         #self.simmat = modeling_util.SimmatModule()
#         self.kernels = modeling_util.KNRMRbfKernelBank(MUS, SIGMAS)
#         self.combine = torch.nn.Linear(self.kernels.count() * self.CHANNELS *(self.max_gram*self.max_gram)+ self.BERT_SIZE, 1)
#
#     def forward(self, query_tok, query_mask, doc_tok, doc_mask):
#         cls_reps, query_reps, doc_reps = self.encode_bert(query_tok, query_mask, doc_tok, doc_mask)
#
#         all_layers_result = []
#         for q_embed,d_embed in zip(query_reps,doc_reps):
#             q_embed = q_embed.transpose(1,2)#batch*dim*q_len
#             d_embed = d_embed.transpose(1,2)#batch*dim*d_len
#
#             q_convs = []
#             d_convs = []
#             for q_conv,d_conv in zip(self.q_convs,self.d_convs):
#                 q_convs.append(q_conv(q_embed).transpose(1,2))#batch*q_len*filters
#                 d_convs.append(d_conv(d_embed).transpose(1,2))
#
#             KM = []
#             for qi in range(self.max_gram):
#                 for di in range(self.max_gram):
#                     simmat = torch.einsum('bld,brd->blr',
#                     F.normalize(q_convs[qi],p=2,dim=-1),
#                     F.normalize(d_convs[di],p=2,dim=-1))
#                     kernels = self.kernels(simmat)
#
#                     BATCH, KERNELS,  QLEN, DLEN = kernels.shape
#                     # sum over document and query terms
#                     KM.append(kernels.sum(dim=3).sum(dim=2))
#                     #batch*kernels
#             layer_result = torch.stack(KM,dim=1)#batch*(gram*gram)*kernels
#             layer_result = torch.flatten(layer_result,start_dim=1)#batch*all_dim
#             all_layers_result.append(layer_result)
#         result = torch.stack(all_layers_result,dim=1)#batch*layers*all_dim
#         result = torch.flatten(result,start_dim=1)#batch*(layers*all_dim)
#         result = torch.cat([result, cls_reps[-1]], dim=1)
#         scores = self.combine(result) # linear combination over kernels
#         return scores


# class CedrDrmmRanker(BertRanker):
#     def __init__(self):
#         super().__init__()
#         NBINS = 11
#         HIDDEN = 5
#         self.ENTITY_SIZE = 100
#         #self.bert_ranker = VanillaBertRanker()
#         self.simmat = modeling_util.SimmatModule()
#         #self.transform = torch.nn.Linear(self.BERT_SIZE+self.ENTITY_SIZE,self.BERT_SIZE+self.ENTITY_SIZE)
#         self.histogram = modeling_util.DRMMLogCountHistogram(NBINS)
#         #self.hidden_1 = torch.nn.Linear(NBINS * self.CHANNELS + self.BERT_SIZE , HIDDEN)
#         self.hidden_1 = torch.nn.Linear(NBINS * self.CHANNELS + self.BERT_SIZE + self.ENTITY_SIZE*2, HIDDEN)
#         self.hidden_2 = torch.nn.Linear(HIDDEN, 1)
#
#     def forward(self, query_tok, query_mask, doc_tok, doc_mask,query_entity,doc_entity):
#         cls_reps, query_reps, doc_reps = self.encode_bert(query_tok, query_mask, doc_tok, doc_mask)
#
#         query_ent = query_entity.mean(dim=1)
#         doc_ent = doc_entity.mean(dim=1)
#
#         simmat = self.simmat(query_reps, doc_reps, query_tok, doc_tok)
#         histogram = self.histogram(simmat, doc_tok, query_tok)
#         BATCH, CHANNELS, QLEN, BINS = histogram.shape
#         histogram = histogram.permute(0, 2, 3, 1)
#         output = histogram.reshape(BATCH * QLEN, BINS * CHANNELS)
#         # repeat cls representation for each query token
#         cls_rep = cls_reps[-1].reshape(BATCH, 1, -1).expand(BATCH, QLEN, -1).reshape(BATCH * QLEN, -1)
#         query_ent = query_ent[-1].reshape(BATCH, 1, -1).expand(BATCH, QLEN, -1).reshape(BATCH * QLEN, -1)
#         doc_ent = doc_ent[-1].reshape(BATCH, 1, -1).expand(BATCH, QLEN, -1).reshape(BATCH * QLEN, -1)
#
#         output = torch.cat([output, cls_rep,query_ent,doc_ent], dim=1)
#         term_scores = self.hidden_2(torch.relu(self.hidden_1(output))).reshape(BATCH, QLEN)
#         return term_scores.sum(dim=1)
#
# class CedrDrmmCombineRanker(BertRanker):
#     def __init__(self):
#         super().__init__()
#         NBINS = 11
#         HIDDEN = 5
#         self.ENTITY_SIZE = 100
#         #self.bert_ranker = VanillaBertRanker()
#         self.simmat = modeling_util.SimmatModule()
#         self.transform = torch.nn.Linear(self.BERT_SIZE+self.ENTITY_SIZE,self.BERT_SIZE+self.ENTITY_SIZE)
#         self.histogram = modeling_util.DRMMLogCountHistogram(NBINS)
#         self.hidden_1 = torch.nn.Linear(NBINS * self.CHANNELS + self.BERT_SIZE , HIDDEN)
#         #self.hidden_1 = torch.nn.Linear(NBINS * self.CHANNELS + self.BERT_SIZE + self.ENTITY_SIZE*2, HIDDEN)
#         self.hidden_2 = torch.nn.Linear(HIDDEN, 1)
#
#     def forward(self, query_tok, query_mask, doc_tok, doc_mask,query_entity,doc_entity):
#         cls_reps, query_reps, doc_reps = self.encode_bert(query_tok, query_mask, doc_tok, doc_mask)
#
#         #query_ent = query_entity.mean(dim=1)
#         #doc_ent = doc_entity.mean(dim=1)
#         query_trans_reps = []
#         doc_trans_reps = []
#         for query_embed,doc_embed in zip(query_reps,doc_reps):
#             query_embed = torch.cat([query_embed,query_entity],dim=-1)#batch*q_len*dim
#             doc_embed = torch.cat([doc_embed,doc_entity],dim=-1)
#
#             query_reps =  F.relu(self.transform(query_embed))#batch*q_len*dim
#             doc_reps =  F.relu(self.transform(doc_embed))
#
#             query_trans_reps.append(query_reps)
#             doc_trans_reps.append(doc_reps)
#
#         simmat = self.simmat(query_trans_reps, doc_trans_reps, query_tok, doc_tok)
#         histogram = self.histogram(simmat, doc_tok, query_tok)
#         BATCH, CHANNELS, QLEN, BINS = histogram.shape
#         histogram = histogram.permute(0, 2, 3, 1)
#         output = histogram.reshape(BATCH * QLEN, BINS * CHANNELS)
#         # repeat cls representation for each query token
#         cls_rep = cls_reps[-1].reshape(BATCH, 1, -1).expand(BATCH, QLEN, -1).reshape(BATCH * QLEN, -1)
#
#         output = torch.cat([output, cls_rep], dim=1)
#         term_scores = self.hidden_2(torch.relu(self.hidden_1(output))).reshape(BATCH, QLEN)
#         return term_scores.sum(dim=1)
    
# class CedrDrmmTransformRanker(BertTransformRankder):
#     def __init__(self):
#         super().__init__()
#         NBINS = 11
#         HIDDEN = 5
#         #self.bert_ranker = VanillaBertRanker()
#         self.simmat = modeling_util.SimmatModule()
#
#         self.histogram = modeling_util.DRMMLogCountHistogram(NBINS)
#         self.hidden_1 = torch.nn.Linear(NBINS * self.CHANNELS + self.BERT_SIZE , HIDDEN)
#         #self.hidden_1 = torch.nn.Linear(NBINS * self.CHANNELS + self.BERT_SIZE + self.ENTITY_SIZE*2, HIDDEN)
#         self.hidden_2 = torch.nn.Linear(HIDDEN, 1)
#
#     def forward(self, query_tok, query_mask, doc_tok, doc_mask,query_entity,doc_entity):
#         cls_reps, query_reps, doc_reps = self.encode_bert(query_tok, query_mask, doc_tok, doc_mask)
#
#         query_trans_reps,doc_trans_reps = self.transform_embed(query_reps,doc_reps,query_entity,doc_entity)
#
#         simmat = self.simmat(query_trans_reps, doc_trans_reps, query_tok, doc_tok)
#         histogram = self.histogram(simmat, doc_tok, query_tok)
#         BATCH, CHANNELS, QLEN, BINS = histogram.shape
#         histogram = histogram.permute(0, 2, 3, 1)
#         output = histogram.reshape(BATCH * QLEN, BINS * CHANNELS)
#         # repeat cls representation for each query token
#         cls_rep = cls_reps[-1].reshape(BATCH, 1, -1).expand(BATCH, QLEN, -1).reshape(BATCH * QLEN, -1)
#
#         output = torch.cat([output, cls_rep], dim=1)
#         term_scores = self.hidden_2(torch.relu(self.hidden_1(output))).reshape(BATCH, QLEN)
#         return term_scores.sum(dim=1)
#
# class CedrDrmmTKSRanker(BertRanker):
#     def __init__(self):
#         super().__init__()
#
#         #self.bert_ranker = VanillaBertRanker()
#         self.topk = 20
#         self.BERT_SIZE = 768
#
#         self.ENTITY_SIZE = 100
#
#         #self.attention = modeling_util.Attention(self.BERT_SIZE+self.ENTITY_SIZE)#combine+transform
#         self.attention = modeling_util.Attention(self.BERT_SIZE)
#         #self.transform = torch.nn.Linear(self.BERT_SIZE+self.ENTITY_SIZE,self.BERT_SIZE+self.ENTITY_SIZE)#combine+transform
#         self.linear = torch.nn.Linear(self.topk,1)
#         self.out = torch.nn.Linear(self.BERT_SIZE+13+self.ENTITY_SIZE*2,1)
#         #self.out = torch.nn.Linear(self.BERT_SIZE+13,1)# combine+transform
#
#
#     def forward(self, query_tok, query_mask, doc_tok, doc_mask,query_entity,doc_entity):
#         cls_reps, query_reps, doc_reps = self.encode_bert(query_tok, query_mask, doc_tok, doc_mask)
#
#         query_ent = query_entity.mean(dim=1)
#         doc_ent = doc_entity.mean(dim=1)
#
#         concat_all_layers = []
#         for query_embed,doc_embed in zip(query_reps,doc_reps):
#             #combine+transform
#             #query_embed = torch.cat([query_embed,query_entity],dim=-1)#batch*q_len*dim
#             #doc_embed = torch.cat([doc_embed,doc_entity],dim=-1)
#
#             #combine+transform
#             #query_embed =  F.relu(self.transform(query_embed))#batch*q_len*dim
#             #doc_embed =  F.relu(self.transform(doc_embed))
#
#             matching_matrix = torch.einsum('bld,brd->blr',F.normalize(query_embed,p=2,dim=-1),F.normalize(doc_embed,p=2,dim=-1))#batch*q_len*d_len
#
#             matching_top_k = torch.topk(matching_matrix,k=self.topk,dim=-1,sorted=True)[0]#batch*q_len*topk
#             attention_probs = self.attention(query_embed)#batch*q_len
#
#             dense_output = self.linear(matching_top_k).squeeze(dim=-1)#batch*q_len
#
#             embed_flat = torch.einsum('bl,bl->b', dense_output, attention_probs).unsqueeze(dim=-1)#batch*1
#
#             concat_all_layers.append(embed_flat)
#
#         combine_score = torch.stack(concat_all_layers,dim=1).squeeze(dim=-1)#batch*layer_num
#         combine_score = torch.cat([combine_score,cls_reps[-1],query_ent,doc_ent],dim=1)
#         #combine_score = torch.cat([combine_score,cls_reps[-1]],dim=1)#batch*(layer_num+dim)#combine+transform
#
#         res = self.out(combine_score)
#         return res
    
class CedrDrmmTKSTransformRanker(BertRanker):
    def __init__(self,config):
        super().__init__(config)
        
        #self.bert_ranker = VanillaBertRanker()
        self.topk = 20
        self.BERT_SIZE = 768        
        # self.ENTITY_SIZE = 100
        # self.ATTEN_SIZE = 500
        self.ENTITY_SIZE = config["entity_dim"]
        self.ATTEN_SIZE = config["atten_dim"]
        
        self.attention = modeling_util.Attention(self.ATTEN_SIZE)#combine+transform
        self.transform = torch.nn.Linear(self.BERT_SIZE,self.ATTEN_SIZE)#combine+transform
        self.transform_ent = torch.nn.Linear(self.ENTITY_SIZE,self.ATTEN_SIZE)#combine+transform
        self.linear = torch.nn.Linear(self.topk,1)
        self.out = torch.nn.Linear(self.BERT_SIZE+13,1)
        #self.out = torch.nn.Linear(self.BERT_SIZE+13,1)# combine+transform
        

    def forward(self, query_tok, query_mask, doc_tok, doc_mask,query_entity,doc_entity,flag=False):
        cls_reps, query_reps, doc_reps = self.encode_bert(query_tok, query_mask, doc_tok, doc_mask)
        
        cur_query_entity = self.transform_ent(query_entity)
        cur_doc_entity = self.transform_ent(doc_entity)
        
        concat_all_layers = []
        for query_embed,doc_embed in zip(query_reps,doc_reps):
            #combine+transform
            query_embed = self.transform(query_embed)
            doc_embed = self.transform(doc_embed)
                        
            query_embed = torch.relu(query_embed+cur_query_entity)
            doc_embed = torch.relu(doc_embed+cur_doc_entity)
            #query_embed = torch.cat([query_embed,query_entity],dim=-1)#batch*q_len*dim
            #doc_embed = torch.cat([doc_embed,doc_entity],dim=-1)
            
            #combine+transform
            #query_embed =  F.relu(self.transform(query_embed))#batch*q_len*dim
            #doc_embed =  F.relu(self.transform(doc_embed))
            
            matching_matrix = torch.einsum('bld,brd->blr',F.normalize(query_embed,p=2,dim=-1),F.normalize(doc_embed,p=2,dim=-1))#batch*q_len*d_len
            
            matching_top_k = torch.topk(matching_matrix,k=self.topk,dim=-1,sorted=True)[0]#batch*q_len*topk
            attention_probs = self.attention(query_embed)#batch*q_len
            
            dense_output = self.linear(matching_top_k).squeeze(dim=-1)#batch*q_len
            
            embed_flat = torch.einsum('bl,bl->b', dense_output, attention_probs).unsqueeze(dim=-1)#batch*1
            
            concat_all_layers.append(embed_flat)
        
        combine_score = torch.stack(concat_all_layers,dim=1).squeeze(dim=-1)#batch*layer_num   
        combine_score = torch.cat([combine_score,cls_reps[-1]],dim=1)
        #combine_score = torch.cat([combine_score,cls_reps[-1]],dim=1)#batch*(layer_num+dim)#combine+transform

        res = self.out(combine_score)

        if flag:
            return res,attention_probs,matching_matrix
        return res    

class SciCedrDrmmTKSTransformRanker(SciBertTransformRankder):
    def __init__(self,config):
        super().__init__(config)
        
        #self.bert_ranker = VanillaBertRanker()
        self.topk = 20
        # self.BERT_SIZE = 768
        # self.ATTEN_SIZE = 500
        
        self.attention = modeling_util.Attention(self.ATTEN_SIZE)#combine+transform
        self.linear = torch.nn.Linear(self.topk,1)
        self.out = torch.nn.Linear(self.BERT_SIZE+13,1)
        #self.out = torch.nn.Linear(self.BERT_SIZE+13,1)# combine+transform
        

    def forward(self, query_tok, query_mask, doc_tok, doc_mask,query_entity,doc_entity,flag=False):
        cls_reps, query_reps, doc_reps = self.encode_bert(query_tok, query_mask, doc_tok, doc_mask)
        
        query_reps,doc_reps = self.transform_embed(query_reps,doc_reps,query_entity,doc_entity)
        
        concat_all_layers = []
        for query_embed,doc_embed in zip(query_reps,doc_reps):
            #combine+transform        
            matching_matrix = torch.einsum('bld,brd->blr',F.normalize(query_embed,p=2,dim=-1),F.normalize(doc_embed,p=2,dim=-1))#batch*q_len*d_len
            
            matching_top_k = torch.topk(matching_matrix,k=self.topk,dim=-1,sorted=True)[0]#batch*q_len*topk
            attention_probs = self.attention(query_embed)#batch*q_len
            
            dense_output = self.linear(matching_top_k).squeeze(dim=-1)#batch*q_len
            
            embed_flat = torch.einsum('bl,bl->b', dense_output, attention_probs).unsqueeze(dim=-1)#batch*1
            
            concat_all_layers.append(embed_flat)
        
        combine_score = torch.stack(concat_all_layers,dim=1).squeeze(dim=-1)#batch*layer_num   
        combine_score = torch.cat([combine_score,cls_reps[-1]],dim=1)
        #combine_score = torch.cat([combine_score,cls_reps[-1]],dim=1)#batch*(layer_num+dim)#combine+transform
        
        res = self.out(combine_score)

        if flag:
            return res,attention_probs,matching_matrix

        return res    
    
class CedrDrmmTKSCombineRanker(BertRanker):
    def __init__(self,config):
        super().__init__(config)

        #self.bert_ranker = VanillaBertRanker()
        self.topk = 20
        self.BERT_SIZE = 768

        self.ENTITY_SIZE = 100

        self.attention = modeling_util.Attention(self.BERT_SIZE+self.ENTITY_SIZE)
        self.transform = torch.nn.Linear(self.BERT_SIZE+self.ENTITY_SIZE,self.BERT_SIZE+self.ENTITY_SIZE)
        self.linear = torch.nn.Linear(self.topk,1)
        self.dropout = torch.nn.Dropout(0.1)
        self.out = torch.nn.Linear(self.BERT_SIZE+13,1)# combine+transform


    def forward(self, query_tok, query_mask, doc_tok, doc_mask,query_entity,doc_entity):
        cls_reps, query_reps, doc_reps = self.encode_bert(query_tok, query_mask, doc_tok, doc_mask)


        concat_all_layers = []
        for query_embed,doc_embed in zip(query_reps,doc_reps):
            #combine
            query_embed = torch.cat([query_embed,query_entity],dim=-1)#batch*q_len*dim
            doc_embed = torch.cat([doc_embed,doc_entity],dim=-1)

            query_embed = F.relu(self.dropout(self.transform(query_embed)))
            doc_embed = F.relu(self.dropout(self.transform(doc_embed)))

            matching_matrix = torch.einsum('bld,brd->blr',F.normalize(query_embed,p=2,dim=-1),F.normalize(doc_embed,p=2,dim=-1))#batch*q_len*d_len

            matching_top_k = torch.topk(matching_matrix,k=self.topk,dim=-1,sorted=True)[0]#batch*q_len*topk
            attention_probs = self.attention(query_embed)#batch*q_len

            dense_output = self.linear(matching_top_k).squeeze(dim=-1)#batch*q_len

            embed_flat = torch.einsum('bl,bl->b', dense_output, attention_probs).unsqueeze(dim=-1)#batch*1

            concat_all_layers.append(embed_flat)

        combine_score = torch.stack(concat_all_layers,dim=1).squeeze(dim=-1)#batch*layer_num
        combine_score = torch.cat([combine_score,cls_reps[-1]],dim=1)#batch*(layer_num+dim)#combine

        res = self.out(combine_score)
        return res

class CustomBertModel(pytorch_pretrained_bert.BertModel):
    """
    Based on pytorch_pretrained_bert.BertModel, but also outputs un-contextualized embeddings.
    """
    def forward(self, input_ids, token_type_ids, attention_mask):
        """
        Based on pytorch_pretrained_bert.BertModel
        """
        embedding_output = self.embeddings(input_ids, token_type_ids)

        extended_attention_mask = attention_mask.unsqueeze(1).unsqueeze(2)
        extended_attention_mask = extended_attention_mask.to(dtype=next(self.parameters()).dtype) # fp16 compatibility
        extended_attention_mask = (1.0 - extended_attention_mask) * -10000.0

        encoded_layers = self.encoder(embedding_output, extended_attention_mask, output_all_encoded_layers=True)

        return [embedding_output] + encoded_layers

if __name__ == '__main__'    :
    '''text = "Jim Henson was a puppeteer ."
    text_ann = tagme.annotate(text)
    if text_ann:
        ents = modeling_util.get_ents(text_ann,ent_map)
        print(ents)
    else:
        print('request error!')
        ents = []'''