import os
import argparse
import subprocess
import random
from tqdm import tqdm
import torch
import modeling
import data_kg as data
from tensorboardX import SummaryWriter
import sys
import json
import time
import database_util as db



SEED = 42
torch.manual_seed(SEED)
torch.cuda.manual_seed_all(SEED)
random.seed(SEED)

MODEL_MAP = {
    'drmmtks_kg': modeling.DrmmTKSKGRanker,
    'pacrr_kg': modeling.PacrrKGRanker,
    'knrm_kg': modeling.KnrmKGRanker
}

METRIC_MAP={
    'ndcg@1':'ndcg',
    'ndcg@3':'ndcg_cut.3',
    'ndcg@5':'ndcg_cut.5',
    'ndcg@10':'ndcg_cut.10',
    'map':'map',
    'recall@3':'recall.3',
    'recall@5':'recall.5',
    'recall@10':'recall.10',
    'precision@1':'P.1',
    'precision@3':'P.3',
    'precision@5':'P.5',
    'precision@10':'P.10'
}

def get_embed(ent_vec_path):
    vecs = []
    row_idx = 0
    with open(ent_vec_path, 'r') as fin:
        for line in fin:
            vec = line.strip().split('\t')
            vec = [float(x) for x in vec]
            if row_idx==0:
                vecs.append([0]*len(vec))
            row_idx+=1
            vecs.append(vec)
    embed = torch.FloatTensor(vecs)
    embed = torch.nn.Embedding.from_pretrained(embed)
    del vecs
    return embed

class Entity():
    def __init__(self,eid,entity):
        self.id = eid
        self.entity = entity

def main(model, toks_dataset, ents_dataset,train_pairs,  valid_run, qrelf, model_out_dir,entity_vec):
    # LR = 0.0001 #arci for 0.0001
    # MAX_EPOCH = 100

    params = [v for k, v in model.named_parameters() if v.requires_grad]
    optimizer = torch.optim.Adam([{'params':params }], lr=LR)

    epoch = 0
    top_valid_score = None
    top_valid_res = None
    top_valid_kv = None
    train_time = 0
    valid_time = 0
    embed = get_embed(entity_vec)
    for epoch in range(MAX_EPOCH):
        start_time = time.clock()
        loss = train_iteration(model, optimizer, toks_dataset,ents_dataset,train_pairs,embed)
        train_time += time.clock()-start_time
        print(f'train epoch={epoch} loss={loss}')
        #writer.add_scalar('train_loss',loss,epoch)
        start_time = time.clock()
        valid_score,valid_res,valid_k_v = validate(model, toks_dataset,ents_dataset, valid_run, qrelf, epoch, model_out_dir,embed)
        if epoch == MAX_EPOCH - 1:
            valid_time = time.clock() - start_time
        print(f'validation epoch={epoch} score={valid_score}')
        if top_valid_score is None or valid_score > top_valid_score:
            top_valid_score = valid_score
            top_valid_res = valid_res
            top_valid_kv = valid_k_v
            print('new top validation score, saving weights')
            model.save(os.path.join(model_out_dir, 'weights.p'))
    print('training time %s, valid time %s'%(train_time,valid_time))
    print('the best running result:%s'%top_valid_res)
    db.insert_result(task_id,model_id, top_valid_kv)


def train_iteration(model, optimizer, toks_dataset,ents_dataset, train_pairs,embed):
    #BATCH_SIZE = 8
    # BATCH_SIZE = 16
    # BATCHES_PER_EPOCH = 32#32
    #BATCHES_PER_EPOCH = 2
    GRAD_ACC_SIZE = 2
    total = 0
    model.train()
    total_loss = 0.
    with tqdm('training', total=BATCH_SIZE * BATCHES_PER_EPOCH, ncols=80, desc='train', leave=False) as pbar:
        for record in data.iter_train_pairs(model, toks_dataset,ents_dataset,train_pairs, GRAD_ACC_SIZE):
            query_entity = embed(record['query_ent'].cpu() + 1).cuda()
            doc_entity = embed(record['doc_ent'].cpu() + 1).cuda()
            scores = model(record['query_tok'],
                           record['doc_tok'],
                           query_entity,
                           doc_entity)
            count = len(record['query_id']) // 2
            scores = scores.reshape(count, 2)
            loss = torch.mean(1. - scores.softmax(dim=1)[:, 0]) # pariwse softmax
            loss.backward()
            total_loss += loss.item()
            total += count
            if total % BATCH_SIZE == 0:
                optimizer.step()
                optimizer.zero_grad()
            pbar.update(count)
            if total >= BATCH_SIZE * BATCHES_PER_EPOCH:
                return total_loss
    


def validate(model, toks_dataset,ents_dataset, run, qrelf, epoch, model_out_dir,embed):
    VALIDATION_METRIC = base_metric#'map'
    runf = os.path.join(model_out_dir, f'{epoch}.run')
    run_model(model, toks_dataset,ents_dataset, run, runf,embed)
    return trec_eval(qrelf, runf, VALIDATION_METRIC,all_metric)


def run_model(model, toks_dataset,ents_dataset, run, runf, embed,desc='valid'):
    BATCH_SIZE = 16
    #BATCH_SIZE = 8
    rerank_run = {}
    with torch.no_grad(), tqdm(total=sum(len(r) for r in run.values()), ncols=80, desc=desc, leave=False) as pbar:
        model.eval()
        for records in data.iter_valid_records(model, toks_dataset,ents_dataset, run, BATCH_SIZE):
            query_entity = embed(records['query_ent'].cpu() + 1).cuda()
            doc_entity = embed(records['doc_ent'].cpu() + 1).cuda()
            scores = model(records['query_tok'],
                           records['doc_tok'],
                           query_entity,
                           doc_entity)
            for qid, did, score in zip(records['query_id'], records['doc_id'], scores):
                rerank_run.setdefault(qid, {})[did] = score.item()
            pbar.update(len(records['query_id']))
    with open(runf, 'wt') as runfile:
        for qid in rerank_run:
            scores = list(sorted(rerank_run[qid].items(), key=lambda x: (x[1], x[0]), reverse=True))
            for i, (did, score) in enumerate(scores):
                runfile.write(f'{qid} 0 {did} {i+1} {score} run\n')


def trec_eval(qrelf, runf, metric,all_metric):
    trec_eval_f = os.path.abspath(sys.argv[0] + '/../../bin/trec_eval')
    output = subprocess.check_output([trec_eval_f, '-m', metric, qrelf, runf]).decode().rstrip()
    output = output.replace('\t', ' ').split('\n')
    assert len(output) == 1
    base_metric_res = float(output[0].split()[2])

    all_output = []
    all_k_v = {}
    for k_metric in all_metric:
        metric = METRIC_MAP[k_metric]
        output = subprocess.check_output([trec_eval_f, '-m', metric, qrelf, runf]).decode().rstrip()
        output = output.replace('\t', ' ').split('\n')
        base_res = output[0].split()[2]
        all_output.append(metric + ' is ' + base_res)
        all_k_v[k_metric]=base_res

    return base_metric_res, '\t'.join(all_output),all_k_v

def main_cli():
    parser = argparse.ArgumentParser('CEDR model training and validation')
    parser.add_argument('--model', choices=MODEL_MAP.keys())
    parser.add_argument('--config', required=True, help='the model config file')
    parser.add_argument('--initial_bert_weights', type=argparse.FileType('rb'))
    parser.add_argument('--task_id', required=True,
                        help='the task id for this training task. help for insert into our database.')
    parser.add_argument('--model_id', required=True,
                        help='the model id for this training task. help for insert into our database.')
    args = parser.parse_args()

    global task_id
    task_id = args.task_id
    global model_id
    model_id = args.model_id

    config = json.load(open(args.config, 'r'))
    data_dir = config["data_dir"]
    tok_ent_data_dir = config["tok_ent_dir"]
    global base_metric
    base_metric = config["base_metric"]
    global all_metric
    all_metric = config["metrics"]
    global LR
    LR = config["learning_rate"]
    global MAX_EPOCH
    MAX_EPOCH = config["MAX_EPOCH"]
    global BATCH_SIZE
    BATCH_SIZE = config["BATCH_SIZE"]
    global BATCHES_PER_EPOCH
    BATCHES_PER_EPOCH = config["BATCHES_PER_EPOCH"]

    args.text1_maxlen = config["text1_maxlen"]
    args.text2_maxlen = config["text2_maxlen"]
    data.init_qd_len(args.text1_maxlen, args.text2_maxlen)

    args.toks_datafiles = open(tok_ent_data_dir+'id2tok.txt', 'r', encoding='utf-8')
    args.ents_datafiles = tok_ent_data_dir+'id2entity.f'
    args.valid_trec = open(data_dir + 'relation_valid_trec.txt', 'r', encoding='utf-8')
    args.train_pairs = open(data_dir + 'relation_train.txt', 'r', encoding='utf-8')
    args.valid_run = open(data_dir + 'relation_valid.txt', 'r', encoding='utf-8')
    args.model_out_dir = config["model_out_dir"]

    model = MODEL_MAP[args.model](args.config).cuda()
    toks_dataset = data.read_toks(args.toks_datafiles)
    ents_dataset = data.read_ents(args.ents_datafiles)
    train_pairs = data.read_qrels_dict(args.train_pairs)
    valid_run = data.read_qrels_dict(args.valid_run)
    if args.initial_bert_weights is not None:
        model.load(args.initial_bert_weights.name)
    os.makedirs(args.model_out_dir, exist_ok=True)
    main(model, toks_dataset,ents_dataset, train_pairs, valid_run, args.valid_trec.name, args.model_out_dir,config["entity_vec"])
            

if __name__ == '__main__':
    main_cli()
    
    
    
    
    
