import torch
import torch.nn as nn
import pandas as pd

# Load CSV
df = pd.read_csv("rollerset_gaps_by_roll.csv")

# Convert "[1,3,3,7]" strings to lists
df["rollerset1gap"] = df["rollerset1gap"].apply(eval)

# Flatten into 4 columns
df[["rs1_thousands","rs1_hundreds","rs1_tens","rs1_ones"]] = pd.DataFrame(df["rollerset1gap"].tolist())

# Build dataset
X = df[["rs1_thousands","rs1_hundreds","rs1_tens","rs1_ones"]].values
y = X[1:]   # next-step prediction
X = X[:-1]

# Torch dataset
X_tensor = torch.tensor(X, dtype=torch.float32)
y_tensor = torch.tensor(y, dtype=torch.float32)

# Simple LSTM model
class GapModel(nn.Module):
    def __init__(self, input_dim=4, hidden_dim=32, output_dim=4):
        super().__init__()
        self.lstm = nn.LSTM(input_dim, hidden_dim, batch_first=True)
        self.fc = nn.Linear(hidden_dim, output_dim)
    def forward(self, x):
        out, _ = self.lstm(x)
        out = self.fc(out[:,-1,:])
        return out

model = GapModel()
loss_fn = nn.MSELoss()
optimizer = torch.optim.Adam(model.parameters(), lr=0.001)

# Training loop
for epoch in range(50):
    optimizer.zero_grad()
    pred = model(X_tensor.unsqueeze(1))  # add sequence dimension
    loss = loss_fn(pred, y_tensor)
    loss.backward()
    optimizer.step()
    print(f"Epoch {epoch}, Loss {loss.item():.4f}")
