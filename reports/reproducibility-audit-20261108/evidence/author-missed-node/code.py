import numpy as np
import pandas as pd
import json
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from sklearn.model_selection import KFold
import os
from tqdm import tqdm
import warnings
import math

warnings.filterwarnings("ignore")

# Set random seeds for reproducibility
torch.manual_seed(42)
np.random.seed(42)

# Check if GPU is available
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")

# Load data
print("Loading data...")
train_data = []
with open("./input/train.json", "r") as f:
    for line in f:
        train_data.append(json.loads(line))

test_data = []
with open("./input/test.json", "r") as f:
    for line in f:
        test_data.append(json.loads(line))

# Convert to DataFrame for easier processing
train_df = pd.DataFrame(train_data)
test_df = pd.DataFrame(test_data)

# Define target columns and error columns as they appear in the JSON
target_cols = ["reactivity", "deg_Mg_pH10", "deg_pH10", "deg_Mg_50C", "deg_50C"]
error_cols = [
    "reactivity_error",
    "deg_error_Mg_pH10",
    "deg_error_pH10",
    "deg_error_Mg_50C",
    "deg_error_50C",
]
scored_targets = ["reactivity", "deg_Mg_pH10", "deg_Mg_50C"]  # Only these are scored
scored_indices = [0, 1, 3]  # Indices of scored targets

# Create mapping for nucleotide encoding
nucleotide_map = {"A": 0, "G": 1, "U": 2, "C": 3}
structure_map = {".": 0, "(": 1, ")": 2}
loop_type_map = {"S": 0, "M": 1, "I": 2, "B": 3, "H": 4, "E": 5, "X": 6}


def encode_sequence(seq, mapping):
    """Encode sequence to indices"""
    return [mapping.get(ch, 0) for ch in seq]


def pad_sequences(sequences, max_len=107, pad_value=0):
    """Pad sequences to max length"""
    padded = np.full((len(sequences), max_len), pad_value, dtype=np.int32)
    for i, seq in enumerate(sequences):
        padded[i, : len(seq)] = seq[:max_len]
    return padded


# Prepare training data
print("Preparing training data...")
train_sequences = [encode_sequence(seq, nucleotide_map) for seq in train_df["sequence"]]
train_structures = [
    encode_sequence(struct, structure_map) for struct in train_df["structure"]
]
train_loop_types = [
    encode_sequence(loop, loop_type_map) for loop in train_df["predicted_loop_type"]
]

# Pad sequences
max_len = 107
train_seq_padded = pad_sequences(train_sequences, max_len)
train_struct_padded = pad_sequences(train_structures, max_len)
train_loop_padded = pad_sequences(train_loop_types, max_len)

# Prepare targets and errors
train_targets = []
train_errors = []

for _, row in train_df.iterrows():
    # Get first 68 positions for each target
    targets = []
    errors = []
    for col in target_cols:
        targets.append(row[col][:68])
    for col in error_cols:
        errors.append(row[col][:68])

    train_targets.append(np.array(targets).T)  # Shape: (68, 5)
    train_errors.append(np.array(errors).T)  # Shape: (68, 5)

# Stack all targets and errors
train_targets_array = np.stack(train_targets)  # Shape: (n_samples, 68, 5)
train_errors_array = np.stack(train_errors)  # Shape: (n_samples, 68, 5)

# Prepare test data
print("Preparing test data...")
test_sequences = [encode_sequence(seq, nucleotide_map) for seq in test_df["sequence"]]
test_structures = [
    encode_sequence(struct, structure_map) for struct in test_df["structure"]
]
test_loop_types = [
    encode_sequence(loop, loop_type_map) for loop in test_df["predicted_loop_type"]
]

test_seq_padded = pad_sequences(test_sequences, max_len)
test_struct_padded = pad_sequences(test_structures, max_len)
test_loop_padded = pad_sequences(test_loop_types, max_len)


# Define dataset class at module level to avoid pickling issues
class RNADataset(Dataset):
    def __init__(self, sequences, structures, loop_types, targets=None, errors=None):
        self.sequences = torch.tensor(sequences, dtype=torch.long)
        self.structures = torch.tensor(structures, dtype=torch.long)
        self.loop_types = torch.tensor(loop_types, dtype=torch.long)
        self.has_targets = targets is not None
        if self.has_targets:
            self.targets = torch.tensor(targets, dtype=torch.float32)
            self.errors = torch.tensor(errors, dtype=torch.float32)

    def __len__(self):
        return len(self.sequences)

    def __getitem__(self, idx):
        if self.has_targets:
            return (
                self.sequences[idx],
                self.structures[idx],
                self.loop_types[idx],
                self.targets[idx],
                self.errors[idx],
            )
        else:
            return (
                self.sequences[idx],
                self.structures[idx],
                self.loop_types[idx],
                torch.zeros(68, 5),  # dummy target for consistency
                torch.ones(68, 5),  # dummy error for consistency
            )


# Enhanced model with multi-scale convolutional feature extraction
class RNAModel(nn.Module):
    def __init__(
        self,
        vocab_size_seq=4,
        vocab_size_struct=3,
        vocab_size_loop=7,
        embed_dim=32,
        hidden_dim=128,
        num_layers=2,
        num_targets=5,
    ):
        super(RNAModel, self).__init__()

        # Embedding layers
        self.seq_embed = nn.Embedding(vocab_size_seq, embed_dim)
        self.struct_embed = nn.Embedding(vocab_size_struct, embed_dim)
        self.loop_embed = nn.Embedding(vocab_size_loop, embed_dim)

        # Combine embeddings
        self.combine = nn.Linear(embed_dim * 3, hidden_dim)

        # Multi-scale convolutional layers
        self.conv3 = nn.Conv1d(hidden_dim, hidden_dim // 4, kernel_size=3, padding=1)
        self.conv5 = nn.Conv1d(hidden_dim, hidden_dim // 4, kernel_size=5, padding=2)
        self.conv7 = nn.Conv1d(hidden_dim, hidden_dim // 4, kernel_size=7, padding=3)

        # Convolutional layer for residual connection
        self.conv_res = nn.Conv1d(hidden_dim, hidden_dim // 4, kernel_size=1)

        # Batch normalization for conv layers
        self.bn3 = nn.BatchNorm1d(hidden_dim // 4)
        self.bn5 = nn.BatchNorm1d(hidden_dim // 4)
        self.bn7 = nn.BatchNorm1d(hidden_dim // 4)
        self.bn_res = nn.BatchNorm1d(hidden_dim // 4)

        # BiLSTM for sequence processing
        self.lstm = nn.LSTM(
            input_size=hidden_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            bidirectional=True,
            batch_first=True,
            dropout=0.2,
        )

        # Output layers
        self.fc1 = nn.Linear(hidden_dim * 2, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, hidden_dim // 2)
        self.fc3 = nn.Linear(hidden_dim // 2, num_targets)

        # Dropout
        self.dropout = nn.Dropout(0.2)

    def forward(self, seq, struct, loop):
        # Embed inputs
        seq_emb = self.seq_embed(seq)  # (batch, seq_len, embed_dim)
        struct_emb = self.struct_embed(struct)
        loop_emb = self.loop_embed(loop)

        # Concatenate embeddings
        combined = torch.cat([seq_emb, struct_emb, loop_emb], dim=-1)
        combined = torch.relu(self.combine(combined))

        # Transpose for convolutional layers: (batch, hidden_dim, seq_len)
        conv_input = combined.transpose(1, 2)

        # Apply multi-scale convolutions
        conv3_out = torch.relu(self.bn3(self.conv3(conv_input)))
        conv5_out = torch.relu(self.bn5(self.conv5(conv_input)))
        conv7_out = torch.relu(self.bn7(self.conv7(conv_input)))
        conv_res_out = torch.relu(self.bn_res(self.conv_res(conv_input)))

        # Concatenate multi-scale features
        multi_scale = torch.cat([conv3_out, conv5_out, conv7_out, conv_res_out], dim=1)

        # Transpose back: (batch, seq_len, hidden_dim)
        multi_scale = multi_scale.transpose(1, 2)

        # Process with LSTM
        lstm_out, _ = self.lstm(multi_scale)

        # Apply dropout
        lstm_out = self.dropout(lstm_out)

        # Fully connected layers
        out = torch.relu(self.fc1(lstm_out))
        out = self.dropout(out)
        out = torch.relu(self.fc2(out))
        out = self.dropout(out)
        out = self.fc3(out)

        return out


# Define error-weighted MCRMSE loss
def error_weighted_mcrmse_loss(preds, targets, errors, scored_indices=[0, 1, 3]):
    """Calculate error-weighted MCRMSE loss for scored targets only"""
    # preds: (batch, seq_len, num_targets)
    # targets: (batch, seq_len, num_targets)
    # errors: (batch, seq_len, num_targets)

    # Select only scored targets
    preds_scored = preds[:, :, scored_indices]
    targets_scored = targets[:, :, scored_indices]
    errors_scored = errors[:, :, scored_indices]

    # Calculate inverse error weights (higher weight for lower error)
    # Add small epsilon to avoid division by zero
    eps = 1e-8
    weights = 1.0 / (errors_scored + eps)

    # Normalize weights per batch and target dimension
    weights = weights / (torch.mean(weights, dim=[0, 1], keepdim=True) + eps)

    # Calculate weighted MSE
    squared_error = (preds_scored - targets_scored) ** 2
    weighted_mse = torch.mean(
        weights * squared_error, dim=1
    )  # (batch, num_scored_targets)

    # Calculate RMSE
    rmse = torch.sqrt(weighted_mse)

    # Average across targets
    loss = torch.mean(rmse)
    return loss


# Training function
def train_epoch(model, dataloader, optimizer, device):
    model.train()
    total_loss = 0
    for seq, struct, loop, targets, errors in tqdm(dataloader, desc="Training"):
        seq, struct, loop, targets, errors = (
            seq.to(device),
            struct.to(device),
            loop.to(device),
            targets.to(device),
            errors.to(device),
        )

        optimizer.zero_grad()
        preds = model(seq, struct, loop)

        # We only have targets for first 68 positions
        preds = preds[:, :68, :]

        loss = error_weighted_mcrmse_loss(preds, targets, errors)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()

        total_loss += loss.item()

    return total_loss / len(dataloader)


# Validation function
def validate(model, dataloader, device):
    model.eval()
    total_loss = 0
    all_preds = []
    all_targets = []

    with torch.no_grad():
        for seq, struct, loop, targets, errors in tqdm(dataloader, desc="Validation"):
            seq, struct, loop, targets, errors = (
                seq.to(device),
                struct.to(device),
                loop.to(device),
                targets.to(device),
                errors.to(device),
            )

            preds = model(seq, struct, loop)
            preds = preds[:, :68, :]

            loss = error_weighted_mcrmse_loss(preds, targets, errors)
            total_loss += loss.item()

            all_preds.append(preds.cpu().numpy())
            all_targets.append(targets.cpu().numpy())

    avg_loss = total_loss / len(dataloader)
    all_preds = np.concatenate(all_preds, axis=0)
    all_targets = np.concatenate(all_targets, axis=0)

    return avg_loss, all_preds, all_targets


# Use 5-fold cross-validation for better evaluation
print("Running 5-fold cross-validation...")
n_splits = 5
kf = KFold(n_splits=n_splits, shuffle=True, random_state=42)

fold_scores = []
best_model_state = None
best_val_score = float("inf")

for fold, (train_idx, val_idx) in enumerate(kf.split(train_seq_padded)):
    print(f"\n=== Fold {fold+1}/{n_splits} ===")

    # Create datasets
    train_dataset = RNADataset(
        train_seq_padded[train_idx],
        train_struct_padded[train_idx],
        train_loop_padded[train_idx],
        train_targets_array[train_idx],
        train_errors_array[train_idx],
    )

    val_dataset = RNADataset(
        train_seq_padded[val_idx],
        train_struct_padded[val_idx],
        train_loop_padded[val_idx],
        train_targets_array[val_idx],
        train_errors_array[val_idx],
    )

    # Create dataloaders - use num_workers=0 to avoid pickling issues
    batch_size = 32
    train_loader = DataLoader(
        train_dataset, batch_size=batch_size, shuffle=True, num_workers=0
    )
    val_loader = DataLoader(
        val_dataset, batch_size=batch_size, shuffle=False, num_workers=0
    )

    # Initialize model
    model = RNAModel().to(device)
    optimizer = optim.AdamW(model.parameters(), lr=0.001, weight_decay=0.01)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", patience=3, factor=0.5
    )

    # Train model
    n_epochs = 15
    best_fold_loss = float("inf")
    patience = 5
    patience_counter = 0

    for epoch in range(n_epochs):
        # Train
        train_loss = train_epoch(model, train_loader, optimizer, device)

        # Validate
        val_loss, val_preds, val_targets = validate(model, val_loader, device)

        # Update learning rate
        scheduler.step(val_loss)

        # Save best model for this fold
        if val_loss < best_fold_loss:
            best_fold_loss = val_loss
            patience_counter = 0
            # Save best model state for this fold
            torch.save(model.state_dict(), f"./working/best_fold_{fold}.pth")
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print(f"Early stopping at epoch {epoch+1}")
                break

        print(
            f"Epoch {epoch+1}: Train Loss = {train_loss:.4f}, Val Loss = {val_loss:.4f}"
        )

    fold_scores.append(best_fold_loss)
    print(f"Fold {fold+1} best validation MCRMSE: {best_fold_loss:.4f}")

    # Keep track of overall best model
    if best_fold_loss < best_val_score:
        best_val_score = best_fold_loss
        best_model_state = model.state_dict().copy()

# Print cross-validation results
print(f"\n=== Cross-validation results ===")
print(f"Fold scores: {fold_scores}")
print(f"Mean CV score: {np.mean(fold_scores):.4f} ± {np.std(fold_scores):.4f}")

# Train final model on all training data
print("\n=== Training final model on all data ===")
full_train_dataset = RNADataset(
    train_seq_padded,
    train_struct_padded,
    train_loop_padded,
    train_targets_array,
    train_errors_array,
)

full_train_loader = DataLoader(
    full_train_dataset, batch_size=32, shuffle=True, num_workers=0
)

# Use best model from CV as starting point
final_model = RNAModel().to(device)
if best_model_state is not None:
    final_model.load_state_dict(best_model_state)

optimizer = optim.AdamW(final_model.parameters(), lr=0.0005, weight_decay=0.01)

# Train for a few more epochs
for epoch in range(5):
    train_loss = train_epoch(final_model, full_train_loader, optimizer, device)
    print(f"Final training epoch {epoch+1}: MCRMSE = {train_loss:.4f}")

# Create test dataset and loader
test_dataset = RNADataset(test_seq_padded, test_struct_padded, test_loop_padded)
test_loader = DataLoader(test_dataset, batch_size=32, shuffle=False, num_workers=0)

# Make predictions on test set
print("\nMaking predictions on test set...")
final_model.eval()
test_preds = []

with torch.no_grad():
    for seq, struct, loop, _, _ in tqdm(test_loader, desc="Predicting"):
        seq, struct, loop = seq.to(device), struct.to(device), loop.to(device)

        preds = final_model(seq, struct, loop)
        test_preds.append(preds.cpu().numpy())

test_preds = np.concatenate(test_preds, axis=0)  # Shape: (n_test, 107, 5)

# Create submission file
print("Creating submission file...")
submission_rows = []

for i, (_, row) in enumerate(test_df.iterrows()):
    sample_id = row["id"]
    seq_length = row["seq_length"]
    seq_scored = row["seq_scored"]

    # Get predictions for this sample
    sample_preds = test_preds[i]  # Shape: (107, 5)

    # For each position, create a row
    for pos in range(seq_length):
        id_seqpos = f"{sample_id}_{pos}"

        # Get predictions for this position
        if pos < seq_scored:
            # Use predictions for first seq_scored positions
            pred_values = sample_preds[pos]
        else:
            # For positions beyond seq_scored, we still need to predict
            # Use the last available prediction (position 106 if seq_length is 107)
            pred_values = sample_preds[min(pos, seq_length - 1)]

        # Ensure predictions are reasonable (clamp to reasonable range)
        pred_values = np.clip(pred_values, -2, 2)

        submission_rows.append(
            [
                id_seqpos,
                float(pred_values[0]),  # reactivity
                float(pred_values[1]),  # deg_Mg_pH10
                float(pred_values[2]),  # deg_pH10
                float(pred_values[3]),  # deg_Mg_50C
                float(pred_values[4]),  # deg_50C
            ]
        )

# Create submission DataFrame
submission_df = pd.DataFrame(
    submission_rows,
    columns=[
        "id_seqpos",
        "reactivity",
        "deg_Mg_pH10",
        "deg_pH10",
        "deg_Mg_50C",
        "deg_50C",
    ],
)

# Save submission
os.makedirs("./submission", exist_ok=True)
submission_path = "./submission/submission.csv"
submission_df.to_csv(submission_path, index=False)
print(f"Submission saved to {submission_path}")
print(f"Submission shape: {submission_df.shape}")

# Display sample of submission
print("\nSample of submission:")
print(submission_df.head())

# Print final evaluation metric
print(f"\n=== Final Evaluation ===")
print(f"5-fold CV mean MCRMSE: {np.mean(fold_scores):.4f} ± {np.std(fold_scores):.4f}")
print(f"Best fold score: {best_val_score:.4f}")
print(f"Submission file created at: {submission_path}")

# Validate that submission has correct number of rows
expected_rows = test_df["seq_length"].sum()
print(f"Expected rows in submission: {expected_rows}")
print(f"Actual rows in submission: {len(submission_df)}")
print(
    f"Submission {'PASSED' if len(submission_df) == expected_rows else 'FAILED'} validation"
)
