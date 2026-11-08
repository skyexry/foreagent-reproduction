import os
import json
import numpy as np
import pandas as pd
from sklearn.model_selection import KFold
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from tqdm import tqdm
import warnings

warnings.filterwarnings("ignore")

# Set random seeds for reproducibility
np.random.seed(42)
torch.manual_seed(42)
if torch.cuda.is_available():
    torch.cuda.manual_seed(42)
    torch.backends.cudnn.deterministic = True

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")

# Load data correctly from input directory
print("Loading data...")
train_data = []
with open("./input/train.json", "r") as f:
    for line in f:
        train_data.append(json.loads(line))

test_data = []
with open("./input/test.json", "r") as f:
    for line in f:
        test_data.append(json.loads(line))

train_df = pd.DataFrame(train_data)
test_df = pd.DataFrame(test_data)

# Prepare training data
print("Preparing training data...")
sequences_train = train_df["sequence"].values
structures_train = train_df["structure"].values
loop_types_train = train_df["predicted_loop_type"].values

# Target columns - keep as arrays of length seq_scored (68)
target_cols = ["reactivity", "deg_Mg_pH10", "deg_pH10", "deg_Mg_50C", "deg_50C"]
targets_train = []
for col in target_cols:
    # Each is list of lists, convert to numpy array
    targets_train.append(np.array(train_df[col].tolist()))
# Stack to shape (n_samples, seq_scored=68, 5)
targets_train = np.stack(targets_train, axis=-1)

# Prepare test data
print("Preparing test data...")
sequences_test = test_df["sequence"].values
structures_test = test_df["structure"].values
loop_types_test = test_df["predicted_loop_type"].values
seq_scored_test = test_df["seq_scored"].values
seq_length_test = test_df["seq_length"].values

# Create mappings for categorical features with safe defaults
base_to_idx = {"A": 0, "G": 1, "U": 2, "C": 3}
structure_to_idx = {".": 0, "(": 1, ")": 2}
loop_type_to_idx = {"S": 0, "M": 1, "I": 2, "B": 3, "H": 4, "E": 5, "X": 6}


def encode_sequence(seq, mapping, default_idx=0):
    return [mapping.get(base, default_idx) for base in seq]


def encode_features(sequences, structures, loop_types):
    seq_encoded = [
        encode_sequence(seq, base_to_idx, default_idx=0) for seq in sequences
    ]
    struct_encoded = [
        encode_sequence(struct, structure_to_idx, default_idx=0)
        for struct in structures
    ]
    loop_encoded = [
        encode_sequence(loop, loop_type_to_idx, default_idx=0) for loop in loop_types
    ]
    # Shape: (n_samples, seq_len=107, 3)
    return np.stack([seq_encoded, struct_encoded, loop_encoded], axis=-1)


X_train = encode_features(sequences_train, structures_train, loop_types_train)
X_test = encode_features(sequences_test, structures_test, loop_types_test)

print(f"Training data shape: {X_train.shape}")
print(f"Test data shape: {X_test.shape}")
print(f"Targets shape: {targets_train.shape}")


# Define dataset class at module level for proper pickling
class RNADataset(Dataset):
    def __init__(self, features, targets=None, seq_scored=None):
        self.features = features
        self.targets = targets
        self.seq_scored = seq_scored
        self.has_targets = targets is not None

    def __len__(self):
        return len(self.features)

    def __getitem__(self, idx):
        features = torch.tensor(self.features[idx], dtype=torch.long)
        if self.has_targets:
            # targets shape: (seq_scored, 5)
            targets = torch.tensor(self.targets[idx], dtype=torch.float32)
            return features, targets
        return features


# Define model
class RNAModel(nn.Module):
    def __init__(
        self,
        vocab_sizes=[5, 3, 7],
        embed_dims=[32, 16, 16],
        hidden_dim=128,
        num_layers=2,
        dropout=0.3,
    ):
        super(RNAModel, self).__init__()

        self.embedding_layers = nn.ModuleList(
            [
                nn.Embedding(vocab_size, embed_dim)
                for vocab_size, embed_dim in zip(vocab_sizes, embed_dims)
            ]
        )

        total_embed_dim = sum(embed_dims)

        # Bidirectional LSTM that processes full sequence
        self.lstm = nn.LSTM(
            input_size=total_embed_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            bidirectional=True,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0,
        )

        # Position-wise feedforward to get 5 outputs per position
        self.position_wise = nn.Sequential(
            nn.Linear(hidden_dim * 2, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, 5),  # 5 targets per position
        )

    def forward(self, x):
        # x shape: (batch_size, seq_len=107, 3)
        batch_size, seq_len, _ = x.shape

        embeddings = []
        for i in range(3):
            embed = self.embedding_layers[i](x[:, :, i])
            embeddings.append(embed)

        x_embed = torch.cat(embeddings, dim=-1)

        # LSTM processes full sequence
        lstm_out, _ = self.lstm(x_embed)  # shape: (batch_size, seq_len, hidden_dim*2)

        # Apply position-wise network to each position
        lstm_flat = lstm_out.reshape(batch_size * seq_len, -1)
        outputs_flat = self.position_wise(lstm_flat)
        outputs = outputs_flat.reshape(batch_size, seq_len, 5)

        return outputs  # shape: (batch_size, seq_len, 5)


# Custom loss that only computes on scored positions
class PositionScoredMSELoss(nn.Module):
    def __init__(self, scored_indices=[0, 1, 3], seq_scored=68):
        super(PositionScoredMSELoss, self).__init__()
        self.scored_indices = scored_indices
        self.seq_scored = seq_scored
        self.mse = nn.MSELoss(reduction="none")

    def forward(self, pred, target):
        # pred shape: (batch_size, seq_len, 5)
        # target shape: (batch_size, seq_scored, 5)
        batch_size = pred.shape[0]

        # Only take predictions for scored positions (first seq_scored positions)
        pred_scored = pred[:, : self.seq_scored, :]

        # Calculate MSE for all targets at scored positions
        mse_all = self.mse(pred_scored, target)  # shape: (batch_size, seq_scored, 5)

        # Average over sequence positions first
        mse_per_target = mse_all.mean(dim=1)  # shape: (batch_size, 5)

        # Weight the losses: higher weight for scored targets
        weights = torch.ones_like(mse_per_target)
        for idx in self.scored_indices:
            weights[:, idx] = 2.0

        weighted_mse = mse_per_target * weights
        return weighted_mse.mean()


# Training function
def train_epoch(model, dataloader, optimizer, criterion, device, seq_scored=68):
    model.train()
    total_loss = 0
    for batch in tqdm(dataloader, desc="Training", leave=False):
        features, targets = batch
        features = features.to(device)
        targets = targets.to(device)

        optimizer.zero_grad()
        outputs = model(features)  # shape: (batch_size, seq_len, 5)
        loss = criterion(outputs, targets)
        loss.backward()
        optimizer.step()

        total_loss += loss.item()

    return total_loss / len(dataloader)


# Validation function with MCRMSE calculation
def validate_epoch(model, dataloader, criterion, device, seq_scored=68):
    model.eval()
    total_loss = 0
    all_preds = []
    all_targets = []

    with torch.no_grad():
        for batch in tqdm(dataloader, desc="Validation", leave=False):
            features, targets = batch
            features = features.to(device)
            targets = targets.to(device)

            outputs = model(features)
            loss = criterion(outputs, targets)
            total_loss += loss.item()

            # Store predictions and targets for scored positions only
            pred_scored = outputs[:, :seq_scored, :].cpu().numpy()
            all_preds.append(pred_scored)
            all_targets.append(targets.cpu().numpy())

    all_preds = np.concatenate(all_preds, axis=0)  # shape: (n_samples, seq_scored, 5)
    all_targets = np.concatenate(all_targets, axis=0)

    # Calculate MCRMSE for scored targets
    scored_indices = [0, 1, 3]
    mcrmse = 0
    for idx in scored_indices:
        # Flatten across samples and positions
        pred_flat = all_preds[:, :, idx].ravel()
        target_flat = all_targets[:, :, idx].ravel()
        rmse = np.sqrt(np.mean((pred_flat - target_flat) ** 2))
        mcrmse += rmse
    mcrmse /= len(scored_indices)

    return total_loss / len(dataloader), mcrmse


# Prepare for cross-validation
print("\nStarting cross-validation...")
n_splits = 5
kf = KFold(n_splits=n_splits, shuffle=True, random_state=42)

# Training parameters - adjust for faster execution
batch_size = 32
epochs = 30
patience = 5

# Store results
cv_scores = []
test_predictions = []

for fold, (train_idx, val_idx) in enumerate(kf.split(X_train)):
    print(f"\nFold {fold + 1}/{n_splits}")

    # Split data
    X_train_fold = X_train[train_idx]
    X_val_fold = X_train[val_idx]
    y_train_fold = targets_train[train_idx]
    y_val_fold = targets_train[val_idx]

    # Create datasets and dataloaders - set num_workers=0 to avoid pickling issues
    train_dataset = RNADataset(X_train_fold, y_train_fold)
    val_dataset = RNADataset(X_val_fold, y_val_fold)

    train_loader = DataLoader(
        train_dataset, batch_size=batch_size, shuffle=True, num_workers=0
    )
    val_loader = DataLoader(
        val_dataset, batch_size=batch_size, shuffle=False, num_workers=0
    )

    # Initialize model
    model = RNAModel().to(device)

    # Loss and optimizer
    criterion = PositionScoredMSELoss(scored_indices=[0, 1, 3], seq_scored=68)
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", patience=3, factor=0.5
    )

    # Training loop
    best_val_loss = float("inf")
    best_val_mcrmse = float("inf")
    patience_counter = 0
    best_model_state = None

    for epoch in range(epochs):
        print(f"\nEpoch {epoch + 1}/{epochs}")

        # Train
        train_loss = train_epoch(model, train_loader, optimizer, criterion, device)

        # Validate
        val_loss, val_mcrmse = validate_epoch(model, val_loader, criterion, device)

        print(
            f"Train Loss: {train_loss:.4f}, Val Loss: {val_loss:.4f}, Val MCRMSE: {val_mcrmse:.4f}"
        )

        # Learning rate scheduling
        scheduler.step(val_loss)

        # Early stopping
        if val_mcrmse < best_val_mcrmse:
            best_val_mcrmse = val_mcrmse
            best_val_loss = val_loss
            patience_counter = 0
            best_model_state = model.state_dict().copy()
        else:
            patience_counter += 1

        if patience_counter >= patience:
            print(f"Early stopping at epoch {epoch + 1}")
            break

    # Load best model
    model.load_state_dict(best_model_state)

    # Store fold score
    cv_scores.append(best_val_mcrmse)
    print(f"Fold {fold + 1} best MCRMSE: {best_val_mcrmse:.4f}")

    # Make predictions on test set
    print("Making test predictions...")
    model.eval()
    test_dataset = RNADataset(X_test)
    test_loader = DataLoader(
        test_dataset, batch_size=batch_size, shuffle=False, num_workers=0
    )

    fold_test_preds = []
    with torch.no_grad():
        for batch in tqdm(test_loader, desc="Test Prediction", leave=False):
            features = batch.to(device)
            outputs = model(features)  # shape: (batch_size, seq_len=107, 5)
            fold_test_preds.append(outputs.cpu().numpy())

    fold_test_preds = np.concatenate(fold_test_preds, axis=0)  # shape: (n_test, 107, 5)
    test_predictions.append(fold_test_preds)

# Average predictions across folds
test_predictions = np.mean(test_predictions, axis=0)  # shape: (n_test, 107, 5)
print(f"\nCross-validation scores: {cv_scores}")
print(f"Mean CV MCRMSE: {np.mean(cv_scores):.4f} (+/- {np.std(cv_scores):.4f})")

# Create submission file
print("\nCreating submission file...")

submission_rows = []
for i in range(len(test_df)):
    sample_id = test_df.iloc[i]["id"]
    seq_length = int(test_df.iloc[i]["seq_length"])
    seq_scored = int(test_df.iloc[i]["seq_scored"])

    # Get predictions for this sample - shape: (107, 5)
    preds = test_predictions[i]

    # For each position in the sequence
    for pos in range(seq_length):
        row_id = f"{sample_id}_{pos}"

        # Get predictions for this position
        if pos < seq_scored:
            # Use predictions for scored positions
            reactivity = preds[pos, 0]
            deg_Mg_pH10 = preds[pos, 1]
            deg_pH10 = preds[pos, 2]
            deg_Mg_50C = preds[pos, 3]
            deg_50C = preds[pos, 4]
        else:
            # For positions beyond seq_scored, we still need to predict something
            # Use the average of the last few scored positions
            if seq_scored > 0:
                avg_preds = preds[max(0, seq_scored - 5) : seq_scored].mean(axis=0)
                reactivity = avg_preds[0]
                deg_Mg_pH10 = avg_preds[1]
                deg_pH10 = avg_preds[2]
                deg_Mg_50C = avg_preds[3]
                deg_50C = avg_preds[4]
            else:
                reactivity = 0.0
                deg_Mg_pH10 = 0.0
                deg_pH10 = 0.0
                deg_Mg_50C = 0.0
                deg_50C = 0.0

        # Clip to reasonable range
        submission_rows.append(
            {
                "id_seqpos": row_id,
                "reactivity": max(0.0, min(5.0, float(reactivity))),
                "deg_Mg_pH10": max(0.0, min(5.0, float(deg_Mg_pH10))),
                "deg_pH10": max(0.0, min(5.0, float(deg_pH10))),
                "deg_Mg_50C": max(0.0, min(5.0, float(deg_Mg_50C))),
                "deg_50C": max(0.0, min(5.0, float(deg_50C))),
            }
        )

# Create submission DataFrame
submission_df = pd.DataFrame(submission_rows)

# Sort to match sample submission order
submission_df = submission_df.sort_values("id_seqpos")

# Ensure submission directory exists
os.makedirs("./submission", exist_ok=True)
submission_path = "./submission/submission.csv"
submission_df.to_csv(submission_path, index=False)
print(f"Submission saved to {submission_path}")
print(f"Submission shape: {submission_df.shape}")

# Verify the submission file exists
if os.path.exists(submission_path):
    print(f"\nSuccessfully created submission file at {submission_path}")
    print(f"File size: {os.path.getsize(submission_path)} bytes")
else:
    print(f"\nERROR: Failed to create submission file at {submission_path}")

print(f"\nFinal mean CV MCRMSE: {np.mean(cv_scores):.4f}")
