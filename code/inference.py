import wandb
import numpy as np
import torch
import torch.nn as nn
import pandas as pd
from torch.utils.data import DataLoader
from tqdm import tqdm
from sklearn.metrics import mean_absolute_error, mean_squared_error 

from .model import LSTM, TFModel
from .dataset import create_data_loader, windowDataset, Multi_WindowDataset
from .preprocessing import preprocessing, inference_preprocessing

class RMSELoss(nn.Module):
    def forward(self, y_pred, y_true):
        mse_loss = nn.functional.mse_loss(y_pred, y_true)
        rmse_loss = torch.sqrt(mse_loss)
        return rmse_loss

class MAELoss(nn.Module):
    def forward(self, y_pred, y_true):
        mae_loss = nn.functional.l1_loss(y_pred, y_true)
        return mae_loss



def inference(args):
    
    lr = args.learning_rate
    epoch = args.num_epochs
    iw = args.window_size
    batch_size = args.batch_size
    ow = args.step
    step = args.step
    
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"current device: {device}")

    # 데이터 준비
    df = pd.read_excel(args.train_path, index_col = '월별')

    data_train, data_test = inference_preprocessing(df, args.window_size)
    
    # inference용 zero 데이터 생성
    zero_data = pd.DataFrame(np.zeros((step, len(data_test.columns))), columns = data_test.columns)
    data_test = pd.concat([data_test, zero_data], axis = 0, ignore_index = True)
    

    train_dataset = Multi_WindowDataset(data_train, input_window=iw, output_window=ow, stride=1)
    train_loader = DataLoader(train_dataset, batch_size=batch_size)
    
    valid_dataset = Multi_WindowDataset(data_test, input_window=iw, output_window=ow, stride=1)
    valid_loader = DataLoader(valid_dataset, batch_size=1)
    
    
    
    model = TFModel(iw*50, ow, 128, 8, 4, 0.1).to(device)
    # breakpoint()
    criterion = RMSELoss()
    MAE_criterion = MAELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer=optimizer,
                                        lr_lambda=lambda epoch: 0.995 ** epoch,
                                        last_epoch=-1,
                                        verbose=False)
    print('*' * 30)
    print('inference start')
    print(f'epochs : {epoch}')
    print(f'learning rate : {lr}')
    print(f'batch size : {batch_size}')
    print(f'window size : {iw}')
    print('*' * 30)
    model.train()
    progress = tqdm(range(epoch))
    

    
    for i in progress:
        batchloss = 0.0
        loss_back = []
        MAE_loss_back = []
        
        for (inputs, outputs) in train_loader:

            
            optimizer.zero_grad()
            src_mask = model.generate_square_subsequent_mask(inputs.shape[1]).to(device)
            result = model(inputs.float().to(device),  src_mask)
            loss = criterion(result, outputs[:,:,0].float().to(device))
            loss.backward()
            
            
            optimizer.step()
            batchloss += loss
            
            L1loss =  MAE_criterion(result, outputs[:,:,0].float().to(device))
            loss_back.append(loss.item())
            MAE_loss_back.append(L1loss.item())
        scheduler.step()    
            
        # wandb.log({"mean_RMSE": np.mean(loss_back), 'mean_MAE': np.mean(MAE_loss_back),
        #            "epoch": epoch, "learning_rate" : args.learning_rate,
        #             })
        progress.set_description("loss: {:0.6f}".format(batchloss.cpu().item() / len(train_loader)))
    
    device = 'cpu'
    model.to(device)
    model.eval()
    with torch.no_grad():
        for i, (inputs, labels) in enumerate(valid_loader):
            inputs = inputs.to(device)
            labels = labels.to(device)
            # labels = labels.unsqueeze(1).to(device)
            # Forward
            
            src_mask = model.generate_square_subsequent_mask(inputs.shape[1]).to(device)
            result = model(inputs.float().to(device),  src_mask)

            print(result)
            # breakpoint()
            for i in range(args.step):
                val_pred = result[0][i]

                real_pred = float(val_pred)

                print(f'{i+1} 개월 예측 : {real_pred}명')