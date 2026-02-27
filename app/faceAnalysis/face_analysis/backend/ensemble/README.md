# Ensemble Skin Analysis

Combines **classical CV**, **deep learning**, and **Claude API** for skin scores (0–100), age, and skin type. The existing `/analyze` endpoint is unchanged; this adds optional `/analyze/ensemble` and `/analyze/ensemble/json`.

## Structure

- **preprocessing.py** — Face detection, alignment, quality. Extend here for labelling/segmentation when data is available.
- **classical_cv.py** — DoG (acne), HSV (dark spots), LBP (pores), Gabor (wrinkles), luminance (dullness), tone variance.
- **feature_scorer.py** — Learned feature→score mapping; call `fit(feature_vectors, labels)` when you have labels.
- **deep_model.py** — EfficientNet-B2 + regression heads. Load a trained checkpoint via `ENSEMBLE_DEEP_MODEL_PATH` when ready.
- **claude_api.py** — Cached Claude API wrapper for scores + age + skin type.
- **aggregation.py** — Weighted combination and confidence from model agreement.

## When You Have Data

1. **Preprocessing / labelling** — Add dataset builders and labelling hooks in `preprocessing.py` (e.g. export crops + masks for Label Studio).
2. **Segmentation** — Add segmentation masks or region extraction in the preprocessing pipeline; feed masked regions to classical CV and deep model.
3. **Feature scorer** — Collect classical CV feature dicts + expert or API labels, then `FeatureScorer().fit(feature_vectors, labels)` and plug the scorer into the classical pipeline.
4. **Deep model** — Train with `SkinAnalysisTrainer` (see training script stub); save checkpoint and set `ENSEMBLE_DEEP_MODEL_PATH`.
5. **Ensemble weights** — Use `EnsembleWeightLearner.learn_weights(val_results, val_labels)` and set the returned weights on `EnsembleAnalyzer`.

## Optional deps

- `scikit-image` — for LBP in classical CV (optional; falls back if missing).
- `torch`, `torchvision` — for deep model inference/training.
- `sklearn` — for `FeatureScorer.fit()`.

Current behavior: classical CV always runs; deep branch returns neutral scores until a checkpoint is loaded; Claude runs if `ANTHROPIC_API_KEY` (or `CLAUDE_API_KEY`) is set.
