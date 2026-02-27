# Face Analysis: Build Your Own Model — Step-by-Step Plan & Requirements

This document outlines a plan to build an in-house face/skin analysis model that produces **the same style of results** as your current Claude-based API: per-parameter scores (0–100), estimated age, estimated skin type, and optional summary/recommendations.

---

## Current API Output (Target to Match)

Your API returns:

| Output | Type | Notes |
|--------|------|--------|
| **analysis** | Object | 9 parameters: `acne`, `dark_spot`, `dark_circle`, `wrinkle`, `uneven_skintone`, `pores`, `pigmentation`, `dullness`, `overall_skin_health` |
| Per parameter | `observation` (text), `score` (0–100), `recommendation` (text) | |
| **overall_score** | Number | e.g. average of parameter scores |
| **estimated_age** | Number / string | Years |
| **estimated_skintype** | String | normal, dry, oily, combination, sensitive |
| **summary** | String | High-level assessment |
| **recommendations** | String | Personalized routine |

To replicate with your own model you will: **collect data → label it → (optionally) add segmentation → design and train a model → validate and test**.

---

## Phase 1: Data Collection

### 1.1 Image Data

- **Source ideas**
  - Existing user uploads (with consent and anonymization).
  - Public face/skin datasets (e.g. FERET, CelebA, SCUT-FBP, AFAD, skin lesion/face datasets) — check licenses.
  - Synthetic/augmented data from your current pipeline (e.g. crop to face only).
- **Requirements**
  - **Format**: Same as API input (e.g. JPEG/PNG, front-facing face, good lighting when possible).
  - **Resolution**: At least 224×224 (better 384–512) for training; can match your current preprocessing (e.g. 800px max).
  - **Diversity**: Multiple ethnicities, ages, genders, skin types, and conditions so the model generalizes.
- **Volume (rough targets)**
  - Minimum: **~2,000–5,000** labeled face images for a first version.
  - Better: **10,000+** for more robust scores and age/skin type.
  - If you use the API to generate “silver labels”, you can start with 5k–10k and then refine with a smaller expert-labeled set.

### 1.2 Metadata (Optional but Useful)

- Store alongside each image: **ethnicity**, **gender**, **age** (if known). Use same enums as in `config.py` so you can condition the model or evaluate fairness later.

---

## Phase 2: Data Labeling

### 2.1 What to Label

- **Primary (must-have for “same results”)**
  - **9 skin scores** (0–100): acne, dark_spot, dark_circle, wrinkle, uneven_skintone, pores, pigmentation, dullness, overall_skin_health.
  - **Skin type**: one of normal, dry, oily, combination, sensitive.
  - **Age**: numeric (or binned for classification).
- **Optional**
  - Short **observations** or **summary** per image (for training a separate text model or template-based generator later).

### 2.2 Labeling Strategies

| Strategy | Pros | Cons |
|----------|------|------|
| **Expert (dermatologist)** | Gold standard, high quality | Expensive, slow |
| **Silver labels from Claude API** | Fast, cheap, consistent schema | Bias and noise from API; need validation subset |
| **Crowdsourcing** | Scale, cost | Quality control and calibration needed |
| **Hybrid** | Balance cost vs quality | More process to design |

**Recommended approach**

1. Use **Claude API (or current pipeline)** to generate labels for a large set (e.g. 5k–15k images) → **silver dataset**.
2. Have **experts** label a **small subset** (e.g. 500–1,500 images) → **gold dataset**.
3. Use gold set for **validation/test** and optionally for **fine-tuning or re-training** after correcting silver labels.

### 2.3 Labeling Tools

- **Label Studio**, **CVAT**, **Supervisely**, or **Scale AI** for image + numeric/categorical labels.
- Export format: one JSON/CSV per image (or one table) with: `image_id`, `acne`, `dark_spot`, …, `overall_skin_health`, `skin_type`, `age`, (optional: `observation`, `summary`).

### 2.4 Quality Control

- Inter-annotator agreement (if multiple raters): e.g. ICC or correlation for scores.
- Spot-checks and consensus on a subset.
- Sanity checks: score ranges 0–100, skin_type in allowed set, age in reasonable range.

---

## Phase 3: Segmentation (Optional but Recommended)

Segmentation helps the model focus on **skin** and **face regions**, and can support region-specific scores (e.g. dark circles under eyes, acne on cheeks).

### 3.1 Goals

- **Face parsing**: pixel-level masks for skin vs hair vs eyes vs background.
- **Use**: crop/mask to skin only before feeding the scoring model, or add a segmentation branch in the architecture.

### 3.2 Options

| Option | Effort | Notes |
|--------|--------|--------|
| **Off-the-shelf** | Low | Use existing face-parsing models (e.g. face-parsing PyTorch repos, or MediaPipe face mesh to derive a rough skin mask like in your `filter_hybrid.py`). |
| **Label segmentation** | High | Manually or semi-automatically label skin/face regions; train your own parser. |
| **Pre-trained + fine-tune** | Medium | Start from a public face-parsing model, fine-tune on your data if you have masks. |

### 3.3 Deliverables

- Per image: **skin mask** (binary or multi-class: forehead, cheeks, nose, etc.) so that training/inference can use “skin-only” or “face” crops.
- Pipeline step: **input image → face detect → (optional) segment → crop/mask → feed to scoring model**.

---

## Phase 4: Model Architecture

Design a model that outputs the **same structure** as the API: 9 scores + overall_score + age + skin_type (+ optional text).

### 4.1 Output Heads

- **Regression heads (9 + 1)**
  - 9 skin parameters: each output a single scalar in [0, 100] (e.g. Sigmoid × 100 or bounded regression).
  - 1 age: regression (years) or classification (bins).
- **Classification head**
  - Skin type: 5 classes (normal, dry, oily, combination, sensitive).
- **Overall score**
  - Can be **computed** as mean of 9 scores (no extra head) to match your current logic.

### 4.2 Backbone + Heads (Recommended)

- **Backbone**: Pretrained vision encoder (e.g. **EfficientNet-B0/B2**, **ResNet-50**, **ViT-Small**) to get a feature vector per image.
- **Heads**:
  - Shared trunk (optional 1–2 FC layers), then:
    - 9 × regression head (each 1 output),
    - 1 × age head (1 output or N classes),
    - 1 × skin_type head (5 classes).
- **Segmentation** (if used): either a separate U-Net/Decoder on top of the same backbone (multi-task), or a fixed external segmenter that runs before the backbone.

### 4.3 Optional Text (Summary / Recommendations)

- **Option A**: Rule/template-based from scores + age + skin_type (e.g. “If acne > 70 and age < 25 → add recommendation X”). No extra model.
- **Option B**: Small language model or encoder–decoder that takes **concatenated scores + metadata** and generates `summary` and `recommendations` to mimic API text. Train on API-generated or expert text.

### 4.4 Input Pipeline

- Resize to fixed size (e.g. 224 or 384).
- Normalize with ImageNet mean/std if using ImageNet-pretrained backbone.
- Optional: multiply input by skin mask so background is zeroed out.

---

## Phase 5: Model Training

### 5.1 Losses

- **Skin scores**: MSE or Smooth L1 (regression); ensure labels are in [0, 100].
- **Age**: MSE (regression) or cross-entropy (binned).
- **Skin type**: Cross-entropy.
- **Combined**: Weighted sum, e.g. `L = w1 * L_scores + w2 * L_age + w3 * L_skintype`. Tune weights so no head dominates.

### 5.2 Training Setup

- **Framework**: PyTorch or TensorFlow/Keras.
- **Optimizer**: AdamW.
- **Scheduler**: Cosine or step decay.
- **Regularization**: Dropout, weight decay, optional MixUp/CutMix for robustness.
- **Validation**: Hold out 10–15% of labeled data (prefer gold labels for test).

### 5.3 Silver vs Gold Data

- Train on **silver labels** first (large set).
- Validate on **gold labels**; use metrics below.
- Optionally: **fine-tune** on gold only (or gold + corrected silver) with smaller LR.

### 5.4 Metrics to Track

- **Scores**: MAE, RMSE, Pearson correlation per parameter and overall.
- **Age**: MAE (years).
- **Skin type**: Accuracy, macro F1, confusion matrix.
- **Agreement with API**: On a fixed test set, compare your model’s scores vs Claude output (correlation, MAE) to measure “same results” objectively.

---

## Phase 6: Validation & Testing

### 6.1 Validation (During Training)

- Same metrics as above on a **validation split** (preferably gold labels).
- Early stopping on validation loss or on a composite metric (e.g. score MAE + age MAE).
- Check for overfitting (train vs val gap).

### 6.2 Testing (Final Evaluation)

- **Test set**: Only gold labels (or a clean subset never used in training).
- Report:
  - Per-parameter MAE/RMSE/correlation for the 9 scores.
  - Age MAE.
  - Skin type accuracy and F1.
  - Correlation/MAE between **your model** and **Claude API** on the same images (if available) to quantify “same results”.

### 6.3 Edge Cases

- No face / multiple faces: use your existing face detection (e.g. MediaPipe/OpenCV in `filter_hybrid.py`); if no face, return an error like the API.
- Poor lighting, occlusion, low resolution: add such examples to test set and report metrics separately.

### 6.4 Deployment Parity

- Run **A/B or shadow mode**: same request to both Claude API and your model; log differences in scores and downstream behavior (e.g. recommendations) before full switch.

---

## Phase 7: Summary Checklist

| Phase | Main tasks |
|-------|------------|
| **1. Data collection** | 5k–15k face images, diverse demographics, same format as API input |
| **2. Labeling** | 9 scores + skin_type + age per image; silver (API) + gold (expert) strategy; use Label Studio/CVAT |
| **3. Segmentation** | Optional; face/skin masks via off-the-shelf or custom model for focused analysis |
| **4. Architecture** | CNN/ViT backbone + 9 regression heads + age head + skin_type head; optional text from templates or small LM |
| **5. Training** | Combined loss, AdamW, validation on gold set; train on silver, optionally fine-tune on gold |
| **6. Validation & testing** | MAE/correlation per score, age MAE, skin type accuracy; compare with Claude on same images; edge-case tests |

---

## Requirements Summary

### Data

- **Images**: 5,000–15,000+ face images (aligned with your API input specs).
- **Labels**: 9 scores (0–100), skin type (5 classes), age (numeric or binned); 500–1,500 expert-labeled for gold.
- **Storage**: Tens of GB depending on resolution and count.

### Tools & Software

- **Labeling**: Label Studio, CVAT, or similar.
- **Training**: Python 3.8+, PyTorch or TensorFlow, torchvision/tf.data.
- **Experiment tracking**: Weights & Biases, MLflow, or TensorBoard.
- **Versioning**: DVC or Git LFS for datasets and model weights.

### Compute

- **GPU**: At least one GPU with 8 GB VRAM (e.g. RTX 3070); 16 GB+ for larger backbones or batch sizes.
- **Training time**: From a few hours (small dataset, EfficientNet-B0) to days (large dataset, ViT).
- **Optional**: Cloud (AWS SageMaker, GCP Vertex, Lambda, etc.) for larger experiments.

### People & Time

- **Labeling**: 1–2 people for silver-label pipeline + expert labeling (or outsourced gold labels).
- **Engineering**: 1 person for data pipeline, model code, training, and API integration.
- **Rough timeline**: 2–4 months for first end-to-end version (data → labeled dataset → trained model → validation and basic deployment).

### Compliance & Ethics

- **Consent and privacy**: Only use images with proper consent; anonymize where needed; comply with GDPR/CCPA if applicable.
- **Bias**: Monitor performance across ethnicity, age, gender; document limitations.

---

## Matching Your Codebase

- **Output format**: Your new model should return the same structure as `analyzer.analyze_face()` so that callers (e.g. `main.py` `/analyze`, `/analyze/json`) need minimal changes: same `analysis` dict (scores + observation + recommendation), `overall_score`, `estimated_age`, `estimated_skintype`, `summary`, `recommendations`.
- **Parameters**: Use `settings.SKIN_ANALYSIS_PARAMETERS` and skin type list from `config.py` so the API contract stays identical.
- **Preprocessing**: Reuse or mirror `FaceAnalyzer.preprocess_image()` (resize, sharpening) and your face detection/filter pipeline so input distribution matches training.

If you want, next step can be a concrete **project layout** (repo folders, configs, and a minimal training script skeleton) under `app/faceAnalysis` or a separate `ml/` directory.
