"""Similarity matching for trajectory feature rows."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from config import settings


MATCH_RESULT_COLUMNS = (
    "target_customer_id",
    "matched_customer_id",
    "rank",
    "distance",
    "similarity_score",
)

DISPLAY_COLUMNS = {
    "persona": "matched_persona",
    "final_outcome": "matched_final_outcome",
}


class TrajectoryMatcher:
    """Match customers by weighted Euclidean distance over trajectory features."""

    def __init__(
        self,
        feature_names: tuple[str, ...] = settings.MATCH_FEATURES,
        feature_weights: dict[str, float] | None = None,
    ) -> None:
        """Initialize a matcher with the configured feature list and weights."""

        self.feature_names = tuple(feature_names)
        self.feature_weights = dict(feature_weights or settings.MATCH_WEIGHTS)
        self.scaler = StandardScaler()
        self._features_df: pd.DataFrame | None = None
        self._weighted_features: np.ndarray | None = None
        self._customer_ids: pd.Series | None = None

    def fit(self, features_df: pd.DataFrame) -> "TrajectoryMatcher":
        """Fit scaling parameters and cache weighted feature vectors."""

        self._validate_input_features(features_df)
        ordered_df = features_df.reset_index(drop=True).copy()
        feature_matrix = ordered_df.loc[:, self.feature_names].to_numpy(dtype=float)
        scaled_features = self.scaler.fit_transform(feature_matrix)
        weights = np.array([self.feature_weights[name] for name in self.feature_names], dtype=float)

        self._features_df = ordered_df
        self._weighted_features = scaled_features * np.sqrt(weights)
        self._customer_ids = ordered_df["customer_id"].astype(str)
        return self

    def match(self, target_customer_id: str, top_k: int = settings.TOP_K_MATCHES) -> pd.DataFrame:
        """Return the nearest customers for a fitted target customer."""

        if self._features_df is None or self._weighted_features is None or self._customer_ids is None:
            raise RuntimeError("TrajectoryMatcher must be fit before calling match().")
        if top_k <= 0:
            raise ValueError("top_k must be a positive integer.")
        if top_k > len(self._customer_ids) - 1:
            raise ValueError("top_k cannot exceed the number of non-target customers.")

        matches = np.flatnonzero(self._customer_ids.to_numpy() == target_customer_id)
        if len(matches) == 0:
            raise ValueError(f"Unknown customer_id: {target_customer_id}")

        target_index = int(matches[0])
        distances = np.linalg.norm(
            self._weighted_features - self._weighted_features[target_index],
            axis=1,
        )
        distances[target_index] = np.inf
        nearest_indices = np.argsort(distances, kind="mergesort")[:top_k]
        nearest_distances = distances[nearest_indices]

        result = pd.DataFrame(
            {
                "target_customer_id": target_customer_id,
                "matched_customer_id": self._customer_ids.iloc[nearest_indices].to_numpy(),
                "rank": np.arange(1, top_k + 1, dtype=int),
                "distance": nearest_distances,
                "similarity_score": 1.0 / (1.0 + nearest_distances),
            }
        )

        for source_column, result_column in DISPLAY_COLUMNS.items():
            if source_column in self._features_df.columns:
                result[result_column] = self._features_df.iloc[nearest_indices][source_column].to_numpy()
        return result

    def _validate_input_features(self, features_df: pd.DataFrame) -> None:
        missing_columns = ["customer_id", *self.feature_names]
        missing_columns = [column for column in missing_columns if column not in features_df.columns]
        if missing_columns:
            raise ValueError(f"Missing required feature columns: {missing_columns}")

        missing_weights = [name for name in self.feature_names if name not in self.feature_weights]
        if missing_weights:
            raise ValueError(f"Missing feature weights: {missing_weights}")

        weights = np.array([self.feature_weights[name] for name in self.feature_names], dtype=float)
        if not np.isfinite(weights).all() or (weights < 0).any():
            raise ValueError("Feature weights must be finite non-negative numbers.")

        if features_df["customer_id"].duplicated().any():
            raise ValueError("customer_id values must be unique.")

        feature_matrix = features_df.loc[:, self.feature_names].to_numpy(dtype=float)
        if not np.isfinite(feature_matrix).all():
            raise ValueError("Feature values must not contain NaN or inf.")


def load_trajectory_features(
    features_path: Path = settings.TRAJECTORY_FEATURES_PATH,
) -> pd.DataFrame:
    """Load the configured trajectory feature CSV."""

    return pd.read_csv(features_path)


def build_matcher(
    features_path: Path = settings.TRAJECTORY_FEATURES_PATH,
) -> TrajectoryMatcher:
    """Load trajectory features and return a fitted matcher."""

    features_df = load_trajectory_features(features_path)
    return TrajectoryMatcher().fit(features_df)
