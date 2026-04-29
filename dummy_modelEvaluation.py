import matplotlib.pyplot as plt
import numpy as np

# ----------------------------
# DATA
# ----------------------------

parameters = ["Acne", "Pigmentation", "Wrinkles", "Pores", "Dark Circles", "Dullness"]
accuracy = [91, 92, 90, 90, 92, 91]

precision = [0.90, 0.91, 0.88]
recall = [0.89, 0.90, 0.87]
pr_labels = ["Acne", "Pigmentation", "Wrinkles"]

lr = ["0.001", "0.0005", "0.0001", "0.0001 (LB)"]
lr_acc = [88, 90, 92, 91]

conf_matrix = np.array([[145, 15],
                        [10, 146]])  # BIGGER NUMBERS

system_labels = ["Preprocessing", "Analysis", "Recommendation"]
system_time = [1, 3, 1]

confidence_labels = ["High (>0.8)", "Medium (0.5-0.8)", "Low (<0.5)"]
confidence_vals = [40, 35, 25]

# ROC-AUC dummy points (FPR vs TPR)
roc_curves = {
    "Acne": {
        "fpr": np.array([0.00, 0.05, 0.10, 0.20, 1.00]),
        "tpr": np.array([0.00, 0.68, 0.82, 0.92, 1.00]),
    },
    "Pigmentation": {
        "fpr": np.array([0.00, 0.04, 0.09, 0.18, 1.00]),
        "tpr": np.array([0.00, 0.72, 0.86, 0.94, 1.00]),
    },
    "Wrinkles": {
        "fpr": np.array([0.00, 0.07, 0.13, 0.24, 1.00]),
        "tpr": np.array([0.00, 0.64, 0.79, 0.89, 1.00]),
    },
}

# ----------------------------
# 1. Accuracy Bar Graph (separate window)
# ----------------------------
plt.figure(figsize=(9, 5))
plt.bar(parameters, accuracy)
plt.title("Accuracy per Skin Condition")
plt.xticks(rotation=30)
plt.tight_layout()

# ----------------------------
# 2. Precision vs Recall (separate window)
# ----------------------------
x = np.arange(len(pr_labels))
width = 0.35

plt.figure(figsize=(8, 5))
plt.bar(x - width/2, precision, width, label='Precision')
plt.bar(x + width/2, recall, width, label='Recall')
plt.xticks(x, pr_labels)
plt.title("Precision vs Recall")
plt.legend()
plt.tight_layout()

# ----------------------------
# 3. Hyperparameter Graph (separate window)
# ----------------------------
plt.figure(figsize=(8, 5))
plt.plot(lr, lr_acc, marker='o')
plt.title("Learning Rate vs Accuracy")
plt.tight_layout()

# ----------------------------
# 4. Confusion Matrix (separate window)
# ----------------------------
plt.figure(figsize=(6, 5))
plt.imshow(conf_matrix)
plt.title("Confusion Matrix (Acne)")
plt.colorbar()

for i in range(conf_matrix.shape[0]):
    for j in range(conf_matrix.shape[1]):
        plt.text(j, i, str(conf_matrix[i, j]),
                 ha='center', va='center', fontsize=16, fontweight='bold')

plt.xlabel("Predicted")
plt.ylabel("Actual")
plt.tight_layout()

# ----------------------------
# 5. System Performance (separate window)
# ----------------------------
plt.figure(figsize=(8, 5))
plt.bar(system_labels, system_time)
plt.title("System Processing Time")
plt.tight_layout()

# ----------------------------
# 6. Confidence Pie Chart (separate window)
# ----------------------------
plt.figure(figsize=(7, 5))
plt.pie(confidence_vals, labels=confidence_labels, autopct='%1.1f%%')
plt.title("Confidence Distribution")
plt.tight_layout()

# ----------------------------
# 7. ROC-AUC (combined, separate window)
# ----------------------------
plt.figure(figsize=(8, 6))
for label, curve in roc_curves.items():
    auc_val = np.trapz(curve["tpr"], curve["fpr"])
    plt.plot(curve["fpr"], curve["tpr"], linewidth=2, label=f"{label} (AUC={auc_val:.3f})")

plt.plot([0, 1], [0, 1], "k--", alpha=0.7, label="Random Classifier")
plt.title("ROC Curves (One-vs-Rest)")
plt.xlabel("False Positive Rate")
plt.ylabel("True Positive Rate")
plt.legend(loc="lower right")
plt.grid(alpha=0.25)
plt.tight_layout()

# ----------------------------
# 8. ROC-AUC (individual windows)
# ----------------------------
for label, curve in roc_curves.items():
    auc_val = np.trapz(curve["tpr"], curve["fpr"])
    plt.figure(figsize=(7, 5))
    plt.plot(curve["fpr"], curve["tpr"], color="tab:blue", linewidth=2,
             label=f"{label} (AUC={auc_val:.3f})")
    plt.plot([0, 1], [0, 1], "k--", alpha=0.7, label="Random Classifier")
    plt.title(f"ROC Curve - {label}")
    plt.xlabel("False Positive Rate")
    plt.ylabel("True Positive Rate")
    plt.legend(loc="lower right")
    plt.grid(alpha=0.25)
    plt.tight_layout()

# ----------------------------
# Show all figure windows
# ----------------------------
plt.show()