import os
import json
import numpy as np
import pandas as pd
from sklearn.model_selection import KFold
from sklearn.metrics import mean_squared_error
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import warnings

warnings.filterwarnings("ignore")

# Set random seeds for reproducibility
np.random.seed(42)
torch.manual_seed(42)
torch.cuda.manual_seed(42)
torch.backends.cudnn.deterministic = True

# Device configuration
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")

# Load data as JSON Lines (each line is a JSON object)
train_data = []
with open("./input/train.json", "r") as f:
    for line in f:
        train_data.append(json.loads(line))

test_data = []
with open("./input/test.json", "r") as f:
    for line in f:
        test_data.append(json.loads(line))

# Convert to DataFrame for easier manipulation
train_df = pd.DataFrame(train_data)
test_df = pd.DataFrame(test_data)

# Define target columns
target_cols = ["reactivity", "deg_Mg_pH10", "deg_pH10", "deg_Mg_50C", "deg_50C"]
scored_cols = ["reactivity", "deg_Mg_pH10", "deg_Mg_50C"]


# Prepare sequences and features
def preprocess_data(df, is_train=True):
    """Preprocess the data for model input."""
    sequences = []
    structures = []
    loop_types = []

    for idx, row in df.iterrows():
        seq = row["sequence"]
        struct = row["structure"]
        loop = row["predicted_loop_type"]

        # Convert to indices
        seq_idx = [{"A": 0, "G": 1, "U": 2, "C": 3}[s] for s in seq]
        struct_idx = [{"(": 0, ")": 1, ".": 2}[s] for s in struct]
        loop_idx = [
            {"S": 0, "M": 1, "I": 2, "B": 3, "H": 4, "E": 5, "X": 6}[s] for s in loop
        ]

        sequences.append(seq_idx)
        structures.append(struct_idx)
        loop_types.append(loop_idx)

    # Convert to numpy arrays
    sequences = np.array(sequences)
    structures = np.array(structures)
    loop_types = np.array(loop_types)

    # Stack features: [batch, seq_len, 3]
    features = np.stack([sequences, structures, loop_types], axis=-1)

    if is_train:
        # Get targets
        targets = []
        for idx, row in df.iterrows():
            target_vec = []
            for col in target_cols:
                target_vec.append(row[col])
            targets.append(np.array(target_vec).T)  # Shape: (68, 5)
        targets = np.array(targets)

        return features, targets
    else:
        return features


# Preprocess train and test data
X_train, y_train = preprocess_data(train_df, is_train=True)
X_test = preprocess_data(test_df, is_train=False)

print(f"Training data shape: {X_train.shape}, Targets shape: {y_train.shape}")
print(f"Test data shape: {X_test.shape}")


# Create dataset class at module level to avoid pickling issues
class RNADataset(Dataset):
    def __init__(self, features, targets=None):
        self.features = features
        self.targets = targets
        self.has_targets = targets is not None

    def __len__(self):
        return len(self.features)

    def __getitem__(self, idx):
        features = torch.tensor(self.features[idx], dtype=torch.long)
        if self.has_targets:
            targets = torch.tensor(self.targets[idx], dtype=torch.float32)
            return features, targets
        else:
            return features


# Define the model
class RNADegradationTransformer(nn.Module):
    def __init__(
        self,
        vocab_sizes=[4, 3, 7],
        embed_dim=128,
        hidden_dim=256,
        num_heads=8,
        num_layers=4,
        num_targets=5,
        max_len=107,
    ):
        super().__init__()

        # Embedding layers for each feature type
        self.seq_embed = nn.Embedding(vocab_sizes[0], embed_dim)
        self.struct_embed = nn.Embedding(vocab_sizes[1], embed_dim)
        self.loop_embed = nn.Embedding(vocab_sizes[2], embed_dim)

        # Positional encoding
        self.pos_embed = nn.Parameter(torch.zeros(1, max_len, embed_dim * 3))

        # Transformer encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=embed_dim * 3,
            nhead=num_heads,
            dim_feedforward=hidden_dim,
            batch_first=True,
            dropout=0.1,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

        # Output layers
        self.fc1 = nn.Linear(embed_dim * 3, hidden_dim)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(0.1)
        self.fc2 = nn.Linear(hidden_dim, num_targets)

    def forward(self, x):
        # x shape: [batch, seq_len, 3]
        seq_emb = self.seq_embed(x[:, :, 0])  # [batch, seq_len, embed_dim]
        struct_emb = self.struct_embed(x[:, :, 1])
        loop_emb = self.loop_embed(x[:, :, 2])

        # Concatenate embeddings
        emb = torch.cat(
            [seq_emb, struct_emb, loop_emb], dim=-1
        )  # [batch, seq_len, embed_dim*3]

        # Add positional encoding
        emb = emb + self.pos_embed[:, : emb.size(1), :]

        # Transformer encoder
        encoded = self.transformer(emb)

        # Output projection
        out = self.fc1(encoded)
        out = self.relu(out)
        out = self.dropout(out)
        out = self.fc2(out)  # [batch, seq_len, num_targets]

        return out


# Training function
def train_epoch(model, dataloader, optimizer, criterion, device):
    model.train()
    total_loss = 0
    for batch_idx, (features, targets) in enumerate(dataloader):
        features, targets = features.to(device), targets.to(device)

        optimizer.zero_grad()
        outputs = model(features)

        # Calculate loss only on first 68 positions (scored positions)
        loss = criterion(outputs[:, :68, :], targets)
        loss.backward()
        optimizer.step()

        total_loss += loss.item()

    return total_loss / len(dataloader)


# Validation function
def validate_epoch(model, dataloader, criterion, device, scored_indices=[0, 1, 3]):
    model.eval()
    total_loss = 0
    all_preds = []
    all_targets = []

    with torch.no_grad():
        for features, targets in dataloader:
            features, targets = features.to(device), targets.to(device)
            outputs = model(features)

            # Calculate MCRMSE on scored columns
            preds = outputs[:, :68, :].cpu().numpy()
            targs = targets.cpu().numpy()

            # Keep only scored columns
            preds_scored = preds[:, :, scored_indices]
            targs_scored = targs[:, :, scored_indices]

            # Calculate RMSE for each column
            rmse_per_col = []
            for i in range(preds_scored.shape[2]):
                rmse = np.sqrt(
                    mean_squared_error(
                        targs_scored[:, :, i].flatten(), preds_scored[:, :, i].flatten()
                    )
                )
                rmse_per_col.append(rmse)

            # Calculate MCRMSE
            mcrmse = np.mean(rmse_per_col)
            total_loss += mcrmse

            all_preds.append(preds)
            all_targets.append(targs)

    return (
        total_loss / len(dataloader),
        np.concatenate(all_preds, axis=0),
        np.concatenate(all_targets, axis=0),
    )


def main():
    # 5-fold cross-validation
    n_splits = 5
    kf = KFold(n_splits=n_splits, shuffle=True, random_state=42)

    fold_scores = []
    all_test_preds = []

    print("Starting 5-fold cross-validation...")

    for fold, (train_idx, val_idx) in enumerate(kf.split(X_train)):
        print(f"\nFold {fold + 1}/{n_splits}")

        # Split data
        X_train_fold, X_val_fold = X_train[train_idx], X_train[val_idx]
        y_train_fold, y_val_fold = y_train[train_idx], y_train[val_idx]

        # Create datasets and dataloaders
        train_dataset = RNADataset(X_train_fold, y_train_fold)
        val_dataset = RNADataset(X_val_fold, y_val_fold)
        test_dataset = RNADataset(X_test)

        # Set num_workers=0 to avoid pickling issues
        train_loader = DataLoader(
            train_dataset, batch_size=32, shuffle=True, num_workers=0
        )
        val_loader = DataLoader(
            val_dataset, batch_size=32, shuffle=False, num_workers=0
        )
        test_loader = DataLoader(
            test_dataset, batch_size=32, shuffle=False, num_workers=0
        )

        # Initialize model, optimizer, and loss
        model = RNADegradationTransformer().to(device)
        optimizer = optim.AdamW(model.parameters(), lr=0.001, weight_decay=0.01)
        criterion = nn.MSELoss()

        # Training loop with early stopping
        best_val_score = float("inf")
        patience = 10
        patience_counter = 0

        for epoch in range(100):
            train_loss = train_epoch(model, train_loader, optimizer, criterion, device)
            val_score, val_preds, val_targets = validate_epoch(
                model, val_loader, criterion, device
            )

            print(
                f"Epoch {epoch+1}: Train Loss = {train_loss:.4f}, Val MCRMSE = {val_score:.4f}"
            )

            # Early stopping
            if val_score < best_val_score:
                best_val_score = val_score
                patience_counter = 0
                # Save best model for this fold
                os.makedirs("./working", exist_ok=True)
                torch.save(model.state_dict(), f"./working/best_model_fold{fold}.pth")
            else:
                patience_counter += 1

            if patience_counter >= patience:
                print(f"Early stopping at epoch {epoch+1}")
                break

        # Load best model for this fold
        model.load_state_dict(torch.load(f"./working/best_model_fold{fold}.pth"))

        # Final validation score
        final_val_score, _, _ = validate_epoch(model, val_loader, criterion, device)
        fold_scores.append(final_val_score)
        print(f"Fold {fold+1} Best MCRMSE: {final_val_score:.4f}")

        # Predict on test set for this fold
        model.eval()
        fold_test_preds = []
        with torch.no_grad():
            for features in test_loader:
                features = features.to(device)
                outputs = model(features)
                fold_test_preds.append(outputs.cpu().numpy())

        fold_test_preds = np.concatenate(fold_test_preds, axis=0)
        all_test_preds.append(fold_test_preds)

    # Calculate average validation score
    avg_score = np.mean(fold_scores)
    print(f"\n5-fold CV Average MCRMSE: {avg_score:.4f}")
    print(f"Fold scores: {fold_scores}")

    # Ensemble predictions from all folds
    test_preds_ensemble = np.mean(all_test_preds, axis=0)  # Average predictions

    # Prepare submission file
    print("\nPreparing submission file...")

    # Create submission DataFrame
    submission_rows = []
    for i, (idx, row) in enumerate(test_df.iterrows()):
        seq_id = row["id"]
        seq_length = row["seq_length"]

        # Get predictions for this sequence
        preds = test_preds_ensemble[i]  # Shape: (107, 5)

        # For each position
        for pos in range(seq_length):
            id_seqpos = f"{seq_id}_{pos}"

            # Use predictions for all positions
            reactivity = float(preds[pos, 0])
            deg_Mg_pH10 = float(preds[pos, 1])
            deg_pH10 = float(preds[pos, 2])
            deg_Mg_50C = float(preds[pos, 3])
            deg_50C = float(preds[pos, 4])

            submission_rows.append(
                {
                    "id_seqpos": id_seqpos,
                    "reactivity": reactivity,
                    "deg_Mg_pH10": deg_Mg_pH10,
                    "deg_pH10": deg_pH10,
                    "deg_Mg_50C": deg_Mg_50C,
                    "deg_50C": deg_50C,
                }
            )

    submission_df = pd.DataFrame(submission_rows)

    # Ensure the submission directory exists
    os.makedirs("./submission", exist_ok=True)

    # Save submission
    submission_path = "./submission/submission.csv"
    submission_df.to_csv(submission_path, index=False)
    print(f"Submission saved to {submission_path}")
    print(f"Submission shape: {submission_df.shape}")

    # Validate submission format
    print("\nValidating submission format...")
    print(f"First few rows of submission:")
    print(submission_df.head())

    # Check against sample submission format
    sample_sub = pd.read_csv("./input/sample_submission.csv")
    sample_cols = list(sample_sub.columns)
    submission_cols = list(submission_df.columns)
    print(f"\nSample submission columns: {sample_cols}")
    print(f"Our submission columns: {submission_cols}")
    print(f"Columns match: {sample_cols == submission_cols}")
    print(f"Number of rows match: {len(submission_df) == len(sample_sub)}")

    print(f"\nFinal 5-fold CV MCRMSE: {avg_score:.6f}")


if __name__ == "__main__":
    main()
