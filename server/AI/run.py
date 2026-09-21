import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
import numpy as np

# Prepare sequences
T = len(ts)            # total days
N = len(ts.columns)    # 10,000 numbers
X_seq = ts.values      # shape (T, N)
# Normalize per number
X_norm = (X_seq - X_seq.mean(axis=0, keepdims=True)) / (X_seq.std(axis=0, keepdims=True) + 1e-6)

seq_len = 30  # use last 30 days to predict next day
X_list, y_list = [], []
for t in range(seq_len, T-1):
    X_list.append(X_norm[t-seq_len:t, :])  # (seq_len, N)
    y_list.append((X_seq[t+1, :] > 0).astype(np.float32))  # next-day hit (binary)

X_arr = np.stack(X_list)  # (samples, seq_len, N)
y_arr = np.stack(y_list)  # (samples, N)

class HitsDataset(Dataset):
    def __init__(self, X, y):
        self.X = torch.tensor(X, dtype=torch.float32)
        self.y = torch.tensor(y, dtype=torch.float32)
    def __len__(self):
        return self.X.shape[0]
    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]

split = int(0.8 * len(X_arr))
train_ds = HitsDataset(X_arr[:split], y_arr[:split])
test_ds  = HitsDataset(X_arr[split:], y_arr[split:])
train_dl = DataLoader(train_ds, batch_size=32, shuffle=True)
test_dl  = DataLoader(test_ds, batch_size=32, shuffle=False)

class GlobalLSTM(nn.Module):
    def __init__(self, n_numbers, hidden=128):
        super().__init__()
        self.lstm = nn.LSTM(input_size=n_numbers, hidden_size=hidden, batch_first=True)
        self.fc = nn.Linear(hidden, n_numbers)
        self.sig = nn.Sigmoid()
    def forward(self, x):
        out, _ = self.lstm(x)           # (B, seq_len, hidden)
        out = out[:, -1, :]             # last step
        out = self.fc(out)              # (B, N)
        return self.sig(out)

model = GlobalLSTM(n_numbers=N, hidden=128)
opt = torch.optim.Adam(model.parameters(), lr=1e-3)
loss_fn = nn.BCELoss()

# Train
for epoch in range(10):
    model.train()
    total = 0
    for xb, yb in train_dl:
        opt.zero_grad()
        pred = model(xb)
        loss = loss_fn(pred, yb)
        loss.backward()
        opt.step()
        total += loss.item() * xb.size(0)
    print(f"Epoch {epoch} Train BCE: {total/len(train_ds):.4f}")

# Evaluate (AUC per number is heavy; compute simple accuracy thresholded at 0.5)
model.eval()
with torch.no_grad():
    accs = []
    for xb, yb in test_dl:
        pred = model(xb)
        yhat = (pred >= 0.5).float()
        acc = (yhat == yb).float().mean().item()
        accs.append(acc)
    print(f"Test mean accuracy: {np.mean(accs):.4f}")

# Next-day probabilities snapshot
last_seq = torch.tensor(X_norm[-seq_len:, :][None, ...], dtype=torch.float32)  # (1, seq_len, N)
with torch.no_grad():
    next_probs = model(last_seq).numpy().flatten()
snap_df = pd.DataFrame({"number": ts.columns, "next_day_hit_prob": next_probs})
snap_df.sort_values("next_day_hit_prob", ascending=False).to_csv("next_day_probabilities_lstm.csv", index=False)
