import numpy as np
import pandas as pd
import json
import os
from sklearn.model_selection import KFold, train_test_split
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import warnings
from torch_geometric.nn import GCNConv
import torch_geometric

warnings.filterwarnings("ignore")

# Set random seeds for reproducibility
np.random.seed(42)
torch.manual_seed(42)
if torch.cuda.is_available():
    torch.cuda.manual_seed(42)
    torch.backends.cudnn.deterministic = True

# Load data
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
scored_targets = ["reactivity", "deg_Mg_pH10", "deg_Mg_50C"]

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


def build_graph_from_structure(structure):
    """Build graph adjacency from RNA secondary structure string"""
    edges = []
    stack = []

    # Add base-pairing edges (parentheses)
    for i, char in enumerate(structure):
        if char == "(":
            stack.append(i)
        elif char == ")":
            if stack:
                j = stack.pop()
                edges.append((i, j))
                edges.append((j, i))  # undirected

    # Add sequential edges (connect adjacent nucleotides)
    for i in range(len(structure) - 1):
        edges.append((i, i + 1))
        edges.append((i + 1, i))

    # Add self-loops
    for i in range(len(structure)):
        edges.append((i, i))

    return edges


def get_features_and_graph(df_row):
    """Extract features and graph structure from a row"""
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

    # Build graph edges
    edges = build_graph_from_structure(struct)
    edge_index = (
        torch.tensor(edges, dtype=torch.long).t().contiguous()
        if edges
        else torch.empty((2, 0), dtype=torch.long)
    )

    return features, edge_index


# Prepare training data
X_train = []
edge_indices = []
y_train = []

for idx, row in train_df.iterrows():
    features, edge_index = get_features_and_graph(row)
    X_train.append(features)
    edge_indices.append(edge_index)

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
test_edge_indices = []
test_ids = []

for idx, row in test_df.iterrows():
    features, edge_index = get_features_and_graph(row)
    X_test.append(features)
    test_edge_indices.append(edge_index)
    test_ids.append(row["id"])

X_test = np.array(X_test)
print(f"Test data shape: X={X_test.shape}")


# Define dataset class
class RNADataset(Dataset):
    def __init__(self, X, edge_indices, y=None):
        self.X = torch.FloatTensor(X)
        self.edge_indices = edge_indices
        self.y = torch.FloatTensor(y) if y is not None else None

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx):
        if self.y is not None:
            return self.X[idx], self.edge_indices[idx], self.y[idx]
        return self.X[idx], self.edge_indices[idx]


# Simplified CNN block
class SimpleCNN(nn.Module):
    def __init__(self, input_dim, hidden_dim):
        super(SimpleCNN, self).__init__()
        self.conv1 = nn.Conv1d(input_dim, hidden_dim, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm1d(hidden_dim)
        self.conv2 = nn.Conv1d(hidden_dim, hidden_dim, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm1d(hidden_dim)
        self.conv3 = nn.Conv1d(hidden_dim, hidden_dim, kernel_size=3, padding=1)
        self.bn3 = nn.BatchNorm1d(hidden_dim)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(0.2)

    def forward(self, x):
        x = self.relu(self.bn1(self.conv1(x)))
        x = self.dropout(x)
        x = self.relu(self.bn2(self.conv2(x)))
        x = self.dropout(x)
        x = self.relu(self.bn3(self.conv3(x)))
        return x


# Define improved model with proper dimensions
class RNAModel(nn.Module):
    def __init__(self, input_dim=22, hidden_dim=128, gnn_dim=64, output_dim=5):
        super(RNAModel, self).__init__()

        # GNN layers for structure modeling
        self.gcn1 = GCNConv(input_dim, gnn_dim)
        self.gcn2 = GCNConv(gnn_dim, gnn_dim)

        # CNN for feature extraction - input dimension is input_dim + gnn_dim
        self.cnn = SimpleCNN(input_dim + gnn_dim, hidden_dim)

        # LSTM for sequential modeling
        self.lstm = nn.LSTM(
            hidden_dim, hidden_dim, batch_first=True, bidirectional=True
        )

        # Fully connected layers
        self.fc1 = nn.Linear(hidden_dim * 2, hidden_dim)
        self.dropout = nn.Dropout(0.3)
        self.fc2 = nn.Linear(hidden_dim, output_dim)

        self.relu = nn.ReLU()

    def forward(self, x, edge_index, batch=None):
        # x shape: (batch, seq_len, input_dim)
        batch_size, seq_len, feat_dim = x.shape

        # Reshape for GNN: (batch * seq_len, feat_dim)
        x_gnn = x.reshape(-1, feat_dim)

        # Create batch vector for GNN
        if batch is None:
            batch_vector = torch.arange(batch_size, device=x.device).repeat_interleave(
                seq_len
            )
        else:
            batch_vector = batch

        # Apply GNN layers
        x_gnn = self.gcn1(x_gnn, edge_index)
        x_gnn = self.relu(x_gnn)
        x_gnn = self.gcn2(x_gnn, edge_index)
        x_gnn = self.relu(x_gnn)

        # Reshape back: (batch, seq_len, gnn_dim)
        x_gnn = x_gnn.reshape(batch_size, seq_len, -1)

        # Combine original features with GNN features
        x_combined = torch.cat([x, x_gnn], dim=-1)

        # CNN processing
        x_cnn = x_combined.transpose(1, 2)  # (batch, input_dim+gnn_dim, seq_len)
        x_cnn = self.cnn(x_cnn)
        x_cnn = x_cnn.transpose(1, 2)  # (batch, seq_len, hidden_dim)

        # LSTM processing
        x_lstm, _ = self.lstm(x_cnn)

        # Fully connected layers
        x_out = self.fc1(x_lstm)
        x_out = self.relu(x_out)
        x_out = self.dropout(x_out)
        x_out = self.fc2(x_out)

        return x_out


# MCRMSE loss function
def mcrmse_loss(preds, targets, scored_indices=[0, 1, 3]):
    """Compute MCRMSE for scored targets only"""
    loss = 0
    for idx in scored_indices:
        mse = torch.mean((preds[:, :, idx] - targets[:, :, idx]) ** 2)
        loss += torch.sqrt(mse)
    return loss / len(scored_indices)


# Custom collate function for graph data
def collate_fn(batch):
    if len(batch[0]) == 3:  # Training data
        X_batch = torch.stack([item[0] for item in batch])
        edge_indices = [item[1] for item in batch]
        y_batch = torch.stack([item[2] for item in batch])

        # Create batch vector for edge indices
        edge_index_batch = []
        offset = 0
        for i, edge_index in enumerate(edge_indices):
            if edge_index.size(1) > 0:
                edge_index_batch.append(edge_index + offset)
            offset += X_batch.size(1)  # seq_len

        if edge_index_batch:
            edge_index_batch = torch.cat(edge_index_batch, dim=1)
        else:
            edge_index_batch = torch.empty((2, 0), dtype=torch.long)

        return X_batch, edge_index_batch, y_batch
    else:  # Test data
        X_batch = torch.stack([item[0] for item in batch])
        edge_indices = [item[1] for item in batch]

        edge_index_batch = []
        offset = 0
        for i, edge_index in enumerate(edge_indices):
            if edge_index.size(1) > 0:
                edge_index_batch.append(edge_index + offset)
            offset += X_batch.size(1)

        if edge_index_batch:
            edge_index_batch = torch.cat(edge_index_batch, dim=1)
        else:
            edge_index_batch = torch.empty((2, 0), dtype=torch.long)

        return X_batch, edge_index_batch


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

        for batch_X, batch_edge_index, batch_y in train_loader:
            batch_X = batch_X.to(device)
            batch_edge_index = batch_edge_index.to(device)
            batch_y = batch_y.to(device)

            optimizer.zero_grad()
            preds = model(batch_X, batch_edge_index)
            loss = mcrmse_loss(preds, batch_y)

            loss.backward()
            optimizer.step()

            train_loss += loss.item()

        # Validation
        model.eval()
        val_loss = 0
        with torch.no_grad():
            for batch_X, batch_edge_index, batch_y in val_loader:
                batch_X = batch_X.to(device)
                batch_edge_index = batch_edge_index.to(device)
                batch_y = batch_y.to(device)

                preds = model(batch_X, batch_edge_index)
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


# 5-fold cross-validation
n_splits = 5
kf = KFold(n_splits=n_splits, shuffle=True, random_state=42)
fold_scores = []

print("Starting 5-fold cross-validation...")
for fold, (train_idx, val_idx) in enumerate(kf.split(X_train)):
    print(f"\nFold {fold + 1}/{n_splits}")

    X_fold_train, X_fold_val = X_train[train_idx], X_train[val_idx]
    edge_fold_train = [edge_indices[i] for i in train_idx]
    edge_fold_val = [edge_indices[i] for i in val_idx]
    y_fold_train, y_fold_val = y_train[train_idx], y_train[val_idx]

    train_dataset = RNADataset(X_fold_train, edge_fold_train, y_fold_train)
    val_dataset = RNADataset(X_fold_val, edge_fold_val, y_fold_val)

    train_loader = DataLoader(
        train_dataset, batch_size=16, shuffle=True, num_workers=0, collate_fn=collate_fn
    )
    val_loader = DataLoader(
        val_dataset, batch_size=16, shuffle=False, num_workers=0, collate_fn=collate_fn
    )

    model = RNAModel(input_dim=X_train.shape[2])
    fold_score = train_model(model, train_loader, val_loader, epochs=30, lr=0.001)
    fold_scores.append(fold_score)

    print(f"Fold {fold + 1} MCRMSE: {fold_score:.4f}")

print(f"\n5-fold CV MCRMSE scores: {fold_scores}")
print(f"Mean MCRMSE: {np.mean(fold_scores):.4f} ± {np.std(fold_scores):.4f}")

# Train final model on all training data
print("\nTraining final model on all training data...")

# Create validation set from 20% of training data for monitoring
(
    X_train_final,
    X_val_final,
    edge_train_final,
    edge_val_final,
    y_train_final,
    y_val_final,
) = train_test_split(X_train, edge_indices, y_train, test_size=0.2, random_state=42)

train_dataset_final = RNADataset(X_train_final, edge_train_final, y_train_final)
val_dataset_final = RNADataset(X_val_final, edge_val_final, y_val_final)

train_loader_final = DataLoader(
    train_dataset_final,
    batch_size=16,
    shuffle=True,
    num_workers=0,
    collate_fn=collate_fn,
)
val_loader_final = DataLoader(
    val_dataset_final,
    batch_size=16,
    shuffle=False,
    num_workers=0,
    collate_fn=collate_fn,
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
test_dataset = RNADataset(X_test, test_edge_indices)
test_loader = DataLoader(
    test_dataset, batch_size=16, shuffle=False, num_workers=0, collate_fn=collate_fn
)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
final_model.to(device)
final_model.eval()

all_test_preds = []
with torch.no_grad():
    for batch_X, batch_edge_index in test_loader:
        batch_X = batch_X.to(device)
        batch_edge_index = batch_edge_index.to(device)

        preds = final_model(batch_X, batch_edge_index)
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
