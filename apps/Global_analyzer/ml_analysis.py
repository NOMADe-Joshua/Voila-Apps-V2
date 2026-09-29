"""
ML Analysis Module

Basic, ready-to-run analyses over the currently merged dataset - a Random Forest
"what matters most" model and a Bayesian-Optimization-style "what to try next"
suggestion step. Zero widget imports (consistent with data_manager.py/plot_manager.py):
this module only computes and returns plain data structures (dicts/DataFrames);
rendering (Markdown text, Plotly figures) is the caller's job.

Both analyses are intentionally fixed-configuration rather than a tunable ML
workbench - feature selection, split ratios, and model hyperparameters are all
sensible defaults so a lab scientist can pick a target and click "Run".
"""

import logging
import warnings

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MIN_ROWS_RANDOM_FOREST = 8
MIN_ROWS_BAYESIAN_OPT = 6


def select_numeric_feature_columns(df: pd.DataFrame, target_col: str) -> list:
    """Numeric columns usable as model features: everything except the target itself
    and columns with fewer than 2 distinct values (constants carry no signal)."""
    numeric_df = df.select_dtypes(include="number")
    return [
        col
        for col in numeric_df.columns
        if col != target_col and numeric_df[col].dropna().nunique() > 1
    ]


def run_random_forest(
    df: pd.DataFrame,
    target_col: str,
    feature_cols: list = None,
    n_estimators: int = 300,
    random_state: int = 42,
) -> dict:
    """
    Fit a RandomForestRegressor to predict target_col from the dataset's other
    numeric parameters, and report held-out performance plus feature importances.

    Returns a dict: target, n_samples, n_features, held_out (bool - False means the
    dataset was too small for a train/test split and R²/RMSE are on training data),
    r2, rmse, importances (list of (feature, importance) sorted descending).
    """
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import mean_squared_error, r2_score
    from sklearn.model_selection import train_test_split

    numeric_df = df.select_dtypes(include="number")
    if target_col not in numeric_df.columns:
        raise ValueError(f"'{target_col}' is not a numeric column in the current dataset.")

    if feature_cols is None:
        feature_cols = select_numeric_feature_columns(df, target_col)

    if not feature_cols:
        raise ValueError("No usable numeric feature parameters found besides the target.")

    model_df = numeric_df[[target_col, *feature_cols]].dropna()
    if len(model_df) < MIN_ROWS_RANDOM_FOREST:
        raise ValueError(
            f"Only {len(model_df)} complete rows available (need at least "
            f"{MIN_ROWS_RANDOM_FOREST}) - load more batches, or pick a target/feature "
            "set with fewer missing values."
        )

    X = model_df[feature_cols]
    y = model_df[target_col]

    held_out = len(model_df) >= 20
    if held_out:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.25, random_state=random_state
        )
    else:
        X_train, y_train = X, y
        X_test, y_test = X, y

    model = RandomForestRegressor(n_estimators=n_estimators, random_state=random_state)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    r2 = r2_score(y_test, y_pred)
    rmse = mean_squared_error(y_test, y_pred) ** 0.5

    importances = sorted(
        zip(feature_cols, model.feature_importances_), key=lambda item: item[1], reverse=True
    )
    logger.debug(
        "run_random_forest: target=%s, n_samples=%d, n_features=%d, held_out=%s, r2=%.3f",
        target_col,
        len(model_df),
        len(feature_cols),
        held_out,
        r2,
    )

    return {
        "target": target_col,
        "n_samples": len(model_df),
        "n_features": len(feature_cols),
        "held_out": held_out,
        "r2": r2,
        "rmse": rmse,
        "importances": importances,
    }


MAX_BO_SUGGESTIONS = 20


def suggest_next_experiments(
    df: pd.DataFrame,
    target_col: str,
    feature_cols: list = None,
    direction: str = "maximize",
    n_candidates: int = 3000,
    n_suggestions: int = 5,
    random_state: int = 42,
) -> dict:
    """
    Fit a Gaussian Process surrogate model on already-measured samples and suggest
    a batch of n_suggestions parameter combinations to measure next, chosen by
    Expected Improvement (EI) over randomly sampled candidates within the observed
    parameter ranges.

    Classic Bayesian Optimization proposes one point per iteration: fit, pick the
    EI maximum, measure it, refit. To propose a whole batch without the
    measurements, this uses the "Kriging Believer" heuristic: after each pick,
    pretend it was measured and came out exactly at the model's predicted mean,
    add that fake observation to the training set, re-condition the GP (kernel
    hyperparameters kept fixed from the real fit) and pick the next EI maximum.
    The fake point collapses the uncertainty around itself, so later picks move
    to other promising regions instead of returning near-duplicates of the first.
    n_suggestions=1 is exactly one ordinary BO step.

    This is a single-shot "propose next experiments" step, not a full closed-loop
    optimizer - re-run it after each new batch of measurements comes in.

    Returns a dict: target, direction, n_samples, n_features, best_observed,
    suggestions (DataFrame with feature_cols + predicted_<target>, predicted_std,
    expected_improvement columns, in the order they were picked). predicted_* come
    from the GP fit on real data only; expected_improvement is the EI at the
    moment each point was picked, i.e. given the previous picks in the batch.
    """
    from scipy.stats import norm
    from sklearn.exceptions import ConvergenceWarning
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import RBF, WhiteKernel
    from sklearn.preprocessing import StandardScaler

    if direction not in ("maximize", "minimize"):
        raise ValueError("direction must be 'maximize' or 'minimize'")
    if not 1 <= n_suggestions <= MAX_BO_SUGGESTIONS:
        raise ValueError(f"n_suggestions must be between 1 and {MAX_BO_SUGGESTIONS}.")

    numeric_df = df.select_dtypes(include="number")
    if target_col not in numeric_df.columns:
        raise ValueError(f"'{target_col}' is not a numeric column in the current dataset.")

    if feature_cols is None:
        feature_cols = select_numeric_feature_columns(df, target_col)

    if not feature_cols:
        raise ValueError("No usable numeric feature parameters found besides the target.")

    model_df = numeric_df[[target_col, *feature_cols]].dropna()
    if len(model_df) < MIN_ROWS_BAYESIAN_OPT:
        raise ValueError(
            f"Only {len(model_df)} complete rows available (need at least "
            f"{MIN_ROWS_BAYESIAN_OPT}) - load more batches, or pick a target/feature "
            "set with fewer missing values."
        )

    X = model_df[feature_cols].to_numpy()
    y = model_df[target_col].to_numpy()

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    kernel = RBF(length_scale=1.0, length_scale_bounds=(1e-2, 1e2)) + WhiteKernel(
        noise_level=1.0, noise_level_bounds=(1e-8, 1e1)
    )
    gp = GaussianProcessRegressor(kernel=kernel, normalize_y=True, random_state=random_state)
    # A near-zero fitted noise level (the optimizer pinned against noise_level_bounds'
    # lower edge) just means the data looks near-noiseless to the model - harmless for
    # this "basic" suggestion tool, so the sklearn ConvergenceWarning about it is
    # suppressed rather than surfaced as an error to the user.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=ConvergenceWarning)
        gp.fit(X_scaled, y)

    rng = np.random.default_rng(random_state)
    mins = X.min(axis=0)
    maxs = X.max(axis=0)
    candidates = rng.uniform(mins, maxs, size=(n_candidates, len(feature_cols)))
    candidates_scaled = scaler.transform(candidates)

    mu, sigma = gp.predict(candidates_scaled, return_std=True)
    sigma = np.maximum(sigma, 1e-9)

    best_observed = y.max() if direction == "maximize" else y.min()

    # Kriging Believer batch selection (see docstring). The "believer" GP reuses
    # the real fit's kernel hyperparameters (optimizer=None), so fake points only
    # shrink uncertainty around themselves rather than reshaping the model.
    believer = GaussianProcessRegressor(kernel=gp.kernel_, normalize_y=True, optimizer=None)
    X_train, y_train = X_scaled, y
    mu_step, sigma_step = mu, sigma
    incumbent = best_observed
    available = np.ones(n_candidates, dtype=bool)
    picked_idx, picked_ei = [], []
    for _ in range(min(n_suggestions, n_candidates)):
        if direction == "maximize":
            improvement = mu_step - incumbent
        else:
            improvement = incumbent - mu_step
        z = improvement / sigma_step
        ei = improvement * norm.cdf(z) + sigma_step * norm.pdf(z)
        ei[sigma_step < 1e-8] = 0.0
        ei[~available] = -np.inf

        idx = int(np.argmax(ei))
        picked_idx.append(idx)
        picked_ei.append(max(float(ei[idx]), 0.0))
        available[idx] = False

        fake_y = mu_step[idx]
        X_train = np.vstack([X_train, candidates_scaled[idx]])
        y_train = np.append(y_train, fake_y)
        incumbent = max(incumbent, fake_y) if direction == "maximize" else min(incumbent, fake_y)
        if len(picked_idx) < n_suggestions:
            believer.fit(X_train, y_train)
            mu_step, sigma_step = believer.predict(candidates_scaled, return_std=True)
            sigma_step = np.maximum(sigma_step, 1e-9)

    suggestions = pd.DataFrame(candidates[picked_idx], columns=feature_cols)
    suggestions[f"predicted_{target_col}"] = mu[picked_idx]
    suggestions["predicted_std"] = sigma[picked_idx]
    suggestions["expected_improvement"] = picked_ei
    suggestions = suggestions.reset_index(drop=True)
    logger.debug(
        "suggest_next_experiments: target=%s, direction=%s, n_samples=%d, "
        "n_suggestions=%d, best_observed=%.4g",
        target_col,
        direction,
        len(model_df),
        len(suggestions),
        best_observed,
    )

    return {
        "target": target_col,
        "direction": direction,
        "n_samples": len(model_df),
        "n_features": len(feature_cols),
        "best_observed": best_observed,
        "suggestions": suggestions,
    }


def estimate_max_bo_steps(n_features: int, min_steps: int = 10, max_steps: int = 200) -> dict:
    """Rule-of-thumb estimate for how many optimization rounds a GP-based Bayesian
    Optimization typically needs to converge in a low-dimensional setting: roughly
    10-20 evaluations per active dimension is common guidance for this class of
    surrogate model. This is a heuristic, not derived from the current dataset -
    treat it as a ballpark, not a guarantee.

    Returns a dict: n_features, suggested_max_steps, rationale.
    """
    suggested_max_steps = min(max(15 * n_features, min_steps), max_steps)
    rationale = (
        f"Rough guideline: ~10-20 evaluations per active parameter. With "
        f"{n_features} parameter(s), a typical GP-based search converges within "
        f"roughly {suggested_max_steps} total experiments (including ones already run)."
    )
    return {
        "n_features": n_features,
        "suggested_max_steps": suggested_max_steps,
        "rationale": rationale,
    }
