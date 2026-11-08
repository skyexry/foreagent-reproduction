import numpy as np
import pandas as pd
import json
import os
from sklearn.model_selection import KFold, train_test_split
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import warnings

warnings.filterwarnings("ignore")

# Set random seeds for reproducibility
np.random.seed(42)
torch.manual_seed(42)
if torch.cuda.is_available():
    torch.cuda.manual_seed(42)
    torch.backends.cudnn.deterministic = True

# Load data - JSON Lines format (each line is a JSON object)
train_data = []
with open("./input/train.json", "r") as f:
    for line in f:
        if line.strip():
            train_data.append(json.loads(line))

test_data = []
with open("./input/test.json", "r") as f:
    for line in f:
        if line.strip():
            test_data.append(json.loads(line))

# Convert to DataFrames
train_df = pd.DataFrame(train_data)
test_df = pd.DataFrame(test_data)

# Define target columns
target_cols = ["reactivity", "deg_Mg_pH10", "deg_pH10", "deg_Mg_50C", "deg_50C"]
scored_targets = ["reactivity", "deg_Mg_pH10", "deg_Mg_50C"]  # for MCRMSE calculation

# Sequence length parameters
SEQ_LEN = 107
SCORED_LEN = 68


# Preprocess function to extract features
def preprocess_sequence(seq):
    """Convert RNA sequence to one-hot encoding"""
    mapping = {"A": 0, "C": 1, "G": 2, "U": 3}
    one_hot = np.zeros((len(seq), 4))
    for i, nucleotide in enumerate(seq):
        if nucleotide in mapping:
            one_hot[i, mapping[nucleotide]] = 1
    return one_hot


def preprocess_structure(struct):
    """Convert structure to numeric encoding"""
    mapping = {".": 0, "(": 1, ")": 2}
    encoded = np.zeros((len(struct), 3))
    for i, char in enumerate(struct):
        if char in mapping:
            encoded[i, mapping[char]] = 1
    return encoded


def preprocess_loop_type(loop):
    """Convert predicted loop type to one-hot"""
    mapping = {"S": 0, "M": 1, "I": 2, "B": 3, "H": 4, "E": 5, "X": 6}
    encoded = np.zeros((len(loop), 7))
    for i, char in enumerate(loop):
        if char in mapping:
            encoded[i, mapping[char]] = 1
    return encoded


def get_features(df_row):
    """Extract features from a row"""
    seq = df_row["sequence"][:SEQ_LEN].ljust(SEQ_LEN, "N")
    struct = df_row["structure"][:SEQ_LEN].ljust(SEQ_LEN, ".")
    loop = df_row["predicted_loop_type"][:SEQ_LEN].ljust(SEQ_LEN, "S")

    seq_feat = preprocess_sequence(seq)
    struct_feat = preprocess_structure(struct)
    loop_feat = preprocess_loop_type(loop)

    # Combine features
    features = np.concatenate([seq_feat, struct_feat, loop_feat], axis=1)

    # Add positional encoding (simple sinusoidal)
    pos = np.arange(SEQ_LEN).reshape(-1, 1)
    pos_sin = np.sin(pos / (10000 ** (np.arange(4) / 4)))
    pos_cos = np.cos(pos / (10000 ** (np.arange(4) / 4)))
    pos_feat = np.concatenate([pos_sin, pos_cos], axis=1)

    features = np.concatenate([features, pos_feat], axis=1)
    return features


# Prepare training data
X_train = []
y_train = []

for idx, row in train_df.iterrows():
    features = get_features(row)
    X_train.append(features)

    # Get targets for first 68 positions
    targets = []
    for col in target_cols:
        target_vals = row[col]
        # Pad to SEQ_LEN if needed
        if len(target_vals) < SEQ_LEN:
            target_vals = list(target_vals) + [0] * (SEQ_LEN - len(target_vals))
        targets.append(target_vals[:SEQ_LEN])
    y_train.append(np.array(targets).T)  # Shape: (SEQ_LEN, 5)

X_train = np.array(X_train)  # Shape: (n_samples, SEQ_LEN, n_features)
y_train = np.array(y_train)  # Shape: (n_samples, SEQ_LEN, 5)

print(f"Training data shape: X={X_train.shape}, y={y_train.shape}")

# Prepare test data
X_test = []
test_ids = []

for idx, row in test_df.iterrows():
    features = get_features(row)
    X_test.append(features)
    test_ids.append(row["id"])

X_test = np.array(X_test)
print(f"Test data shape: X={X_test.shape}")


# Define dataset class at module level to avoid pickling issues
class RNADataset(Dataset):
    def __init__(self, X, y=None):
        self.X = torch.FloatTensor(X)
        self.y = torch.FloatTensor(y) if y is not None else None

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx):
        if self.y is not None:
            return self.X[idx], self.y[idx]
        return self.X[idx]


# Define model
class RNAModel(nn.Module):
    def __init__(self, input_dim=18, hidden_dim=128, output_dim=5):
        super(RNAModel, self).__init__()

        self.conv1 = nn.Conv1d(input_dim, hidden_dim, kernel_size=5, padding=2)
        self.bn1 = nn.BatchNorm1d(hidden_dim)
        self.conv2 = nn.Conv1d(hidden_dim, hidden_dim, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm1d(hidden_dim)

        self.lstm = nn.LSTM(
            hidden_dim, hidden_dim, batch_first=True, bidirectional=True
        )

        self.fc1 = nn.Linear(hidden_dim * 2, hidden_dim)
        self.dropout = nn.Dropout(0.3)
        self.fc2 = nn.Linear(hidden_dim, output_dim)

        self.relu = nn.ReLU()

    def forward(self, x):
        # x shape: (batch, seq_len, input_dim)
        x = x.transpose(1, 2)  # (batch, input_dim, seq_len)

        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)

        x = self.conv2(x)
        x = self.bn2(x)
        x = self.relu(x)

        x = x.transpose(1, 2)  # (batch, seq_len, hidden_dim)

        x, _ = self.lstm(x)

        x = self.fc1(x)
        x = self.relu(x)
        x = self.dropout(x)

        x = self.fc2(x)
        return x


# MCRMSE loss function
def mcrmse_loss(preds, targets, scored_indices=[0, 1, 3]):
    """Compute MCRMSE for scored targets only"""
    loss = 0
    for idx in scored_indices:
        mse = torch.mean((preds[:, :, idx] - targets[:, :, idx]) ** 2)
        loss += torch.sqrt(mse)
    return loss / len(scored_indices)


# Training function
def train_model(model, train_loader, val_loader, epochs=30, lr=0.001):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)

    optimizer = optim.Adam(model.parameters(), lr=lr)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", patience=3, factor=0.5
    )

    best_val_loss = float("inf")

    for epoch in range(epochs):
        model.train()
        train_loss = 0

        for batch_X, batch_y in train_loader:
            batch_X, batch_y = batch_X.to(device), batch_y.to(device)

            optimizer.zero_grad()
            preds = model(batch_X)
            loss = mcrmse_loss(preds, batch_y)

            loss.backward()
            optimizer.step()

            train_loss += loss.item()

        # Validation
        model.eval()
        val_loss = 0
        with torch.no_grad():
            for batch_X, batch_y in val_loader:
                batch_X, batch_y = batch_X.to(device), batch_y.to(device)
                preds = model(batch_X)
                loss = mcrmse_loss(preds, batch_y)
                val_loss += loss.item()

        avg_train_loss = train_loss / len(train_loader)
        avg_val_loss = val_loss / len(val_loader)

        scheduler.step(avg_val_loss)

        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            torch.save(model.state_dict(), "./working/best_model.pth")

        if (epoch + 1) % 5 == 0:
            print(
                f"Epoch {epoch+1}/{epochs}, Train Loss: {avg_train_loss:.4f}, Val Loss: {avg_val_loss:.4f}"
            )

    return best_val_loss


# 5-fold cross-validation with num_workers=0 to avoid multiprocessing issues
n_splits = 5
kf = KFold(n_splits=n_splits, shuffle=True, random_state=42)
fold_scores = []

print("Starting 5-fold cross-validation...")
for fold, (train_idx, val_idx) in enumerate(kf.split(X_train)):
    print(f"\nFold {fold + 1}/{n_splits}")

    X_fold_train, X_fold_val = X_train[train_idx], X_train[val_idx]
    y_fold_train, y_fold_val = y_train[train_idx], y_train[val_idx]

    train_dataset = RNADataset(X_fold_train, y_fold_train)
    val_dataset = RNADataset(X_fold_val, y_fold_val)

    train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_dataset, batch_size=32, shuffle=False, num_workers=0)

    model = RNAModel(input_dim=X_train.shape[2])
    fold_score = train_model(model, train_loader, val_loader, epochs=30, lr=0.001)
    fold_scores.append(fold_score)

    print(f"Fold {fold + 1} MCRMSE: {fold_score:.4f}")

print(f"\n5-fold CV MCRMSE scores: {fold_scores}")
print(f"Mean MCRMSE: {np.mean(fold_scores):.4f} ± {np.std(fold_scores):.4f}")

# Train final model on all training data
print("\nTraining final model on all training data...")

# Create validation set from 20% of training data for monitoring
X_train_final, X_val_final, y_train_final, y_val_final = train_test_split(
    X_train, y_train, test_size=0.2, random_state=42
)

train_dataset_final = RNADataset(X_train_final, y_train_final)
val_dataset_final = RNADataset(X_val_final, y_val_final)

train_loader_final = DataLoader(
    train_dataset_final, batch_size=32, shuffle=True, num_workers=0
)
val_loader_final = DataLoader(
    val_dataset_final, batch_size=32, shuffle=False, num_workers=0
)

final_model = RNAModel(input_dim=X_train.shape[2])
final_score = train_model(
    final_model, train_loader_final, val_loader_final, epochs=40, lr=0.001
)
print(f"Final model validation MCRMSE: {final_score:.4f}")

# Load best model
final_model.load_state_dict(torch.load("./working/best_model.pth"))

# Generate predictions on test set
print("\nGenerating test predictions...")
test_dataset = RNADataset(X_test)
test_loader = DataLoader(test_dataset, batch_size=32, shuffle=False, num_workers=0)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
final_model.to(device)
final_model.eval()

all_test_preds = []
with torch.no_grad():
    for batch_X in test_loader:
        batch_X = batch_X.to(device)
        preds = final_model(batch_X)
        all_test_preds.append(preds.cpu().numpy())

test_preds = np.concatenate(all_test_preds, axis=0)  # Shape: (n_test, SEQ_LEN, 5)

# Prepare submission
print("Preparing submission file...")
submission_rows = []

for i, test_id in enumerate(test_ids):
    seq_length = test_df.iloc[i]["seq_length"]
    seq_scored = test_df.iloc[i]["seq_scored"]

    # Get predictions for this sample
    sample_preds = test_preds[i]  # Shape: (SEQ_LEN, 5)

    for pos in range(SEQ_LEN):
        seqpos_id = f"{test_id}_{pos}"
        pred_values = sample_preds[pos]

        # Clip predictions to reasonable range based on training data
        pred_values = np.clip(pred_values, -2, 2)

        submission_rows.append(
            {
                "id_seqpos": seqpos_id,
                "reactivity": float(pred_values[0]),
                "deg_Mg_pH10": float(pred_values[1]),
                "deg_pH10": float(pred_values[2]),
                "deg_Mg_50C": float(pred_values[3]),
                "deg_50C": float(pred_values[4]),
            }
        )

# Create submission DataFrame
submission_df = pd.DataFrame(submission_rows)

# Ensure the submission directory exists
os.makedirs("./submission", exist_ok=True)

# Save submission
submission_path = "./submission/submission.csv"
submission_df.to_csv(submission_path, index=False)
print(f"Submission saved to {submission_path}")
print(f"Submission shape: {submission_df.shape}")

# Print some sample predictions
print("\nSample predictions:")
print(submission_df.head(10))

# Also save validation score for reference
with open("./working/validation_score.txt", "w") as f:
    f.write(
        f"5-fold CV Mean MCRMSE: {np.mean(fold_scores):.4f} ± {np.std(fold_scores):.4f}\n"
    )
    f.write(f"Final model validation MCRMSE: {final_score:.4f}\n")

print(f"\nValidation score saved to ./working/validation_score.txt")
print(f"Mean CV MCRMSE: {np.mean(fold_scores):.4f}")
