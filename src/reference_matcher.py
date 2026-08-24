"""Reference-only trajectory matching for prospective/as-of evaluation.

Unlike the legacy matcher, this matcher receives reference and target feature
tables separately.  Its scaler is fit only on the reference table; target
features are transformed only after that fit has completed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from config import settings
from src.matcher import MATCH_RESULT_COLUMNS


class ReferenceTrajectoryMatcher:
    """Match one as-of target against a separately fitted reference cohort."""

    def __init__(
        self,
        feature_names: tuple[str, ...] = settings.MATCH_FEATURES,
        feature_weights: dict[str, float] | None = None,
    ) -> None:
        self.feature_names = tuple(feature_names)
        self.feature_weights = dict(feature_weights or settings.MATCH_WEIGHTS)
        self.scaler = StandardScaler()
        self._reference_customer_ids: pd.Series | None = None
        self._reference_weighted_features: np.ndarray | None = None

    def fit(self, reference_features_df: pd.DataFrame) -> "ReferenceTrajectoryMatcher":
        """Fit scaler and cache vectors from the reference table only.

        Only ``customer_id`` and configured numeric feature columns are
        selected.  Labels and other display metadata in an input frame are not
        read by this matcher.
        """

        reference_df = _validated_feature_frame(
            reference_features_df,
            self.feature_names,
            self.feature_weights,
            label="reference_features_df",
        )
        feature_matrix = reference_df.loc[:, self.feature_names].to_numpy(dtype=float)
        self.scaler.fit(feature_matrix)
        scaled_features = self.scaler.transform(feature_matrix)
        weights = np.array([self.feature_weights[name] for name in self.feature_names], dtype=float)
        self._reference_customer_ids = reference_df["customer_id"].astype(str).reset_index(drop=True)
        self._reference_weighted_features = scaled_features * np.sqrt(weights)
        return self

    def match(
        self,
        target_features_df: pd.DataFrame,
        *,
        top_k: int = settings.TOP_K_MATCHES,
    ) -> pd.DataFrame:
        """Return the nearest reference customers for exactly one target row."""

        if self._reference_customer_ids is None or self._reference_weighted_features is None:
            raise RuntimeError("ReferenceTrajectoryMatcher must be fit before calling match().")
        target_df = _validated_feature_frame(
            target_features_df,
            self.feature_names,
            self.feature_weights,
            label="target_features_df",
        )
        if len(target_df) != 1:
            raise ValueError("target_features_df must contain exactly one target customer row")
        if top_k <= 0 or top_k > len(self._reference_customer_ids):
            raise ValueError("top_k must be between 1 and the reference customer count")

        target_customer_id = str(target_df.iloc[0]["customer_id"])
        if target_customer_id in set(self._reference_customer_ids):
            raise ValueError(
                "target_customer_id must not be present in the reference feature table"
            )
        target_matrix = target_df.loc[:, self.feature_names].to_numpy(dtype=float)
        target_scaled = self.scaler.transform(target_matrix)
        weights = np.array([self.feature_weights[name] for name in self.feature_names], dtype=float)
        target_weighted = target_scaled[0] * np.sqrt(weights)
        distances = np.linalg.norm(self._reference_weighted_features - target_weighted, axis=1)
        nearest_indices = np.argsort(distances, kind="mergesort")[:top_k]
        nearest_distances = distances[nearest_indices]
        return pd.DataFrame(
            {
                "target_customer_id": target_customer_id,
                "matched_customer_id": self._reference_customer_ids.iloc[nearest_indices].to_numpy(),
                "rank": np.arange(1, top_k + 1, dtype=int),
                "distance": nearest_distances,
                "similarity_score": 1.0 / (1.0 + nearest_distances),
            },
            columns=MATCH_RESULT_COLUMNS,
        )


def _validated_feature_frame(
    features_df: pd.DataFrame,
    feature_names: tuple[str, ...],
    feature_weights: dict[str, float],
    *,
    label: str,
) -> pd.DataFrame:
    required_columns = ("customer_id", *feature_names)
    missing_columns = [column for column in required_columns if column not in features_df.columns]
    if missing_columns:
        raise ValueError(f"{label} is missing required feature columns: {missing_columns}")
    missing_weights = [name for name in feature_names if name not in feature_weights]
    if missing_weights:
        raise ValueError(f"Missing feature weights: {missing_weights}")
    weights = np.array([feature_weights[name] for name in feature_names], dtype=float)
    if not np.isfinite(weights).all() or (weights < 0).any():
        raise ValueError("Feature weights must be finite non-negative numbers")

    selected = features_df.loc[:, required_columns].copy()
    selected["customer_id"] = selected["customer_id"].astype(str)
    if selected["customer_id"].duplicated().any():
        raise ValueError(f"{label} customer_id values must be unique")
    feature_matrix = selected.loc[:, feature_names].to_numpy(dtype=float)
    if not np.isfinite(feature_matrix).all():
        raise ValueError(f"{label} feature values must not contain NaN or inf")
    return selected.reset_index(drop=True)
