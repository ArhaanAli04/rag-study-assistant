"""
Sample RAG evaluation data for testing metrics.
Replace with real /chat responses + ground truth from your docs.
"""
SAMPLE_EVAL_DATA = [
    {
        "question": "What is overfitting?",
        "answer": "Overfitting occurs when a model learns training data too well, including noise, performing poorly on new data.",
        "contexts": [
            "Overfitting happens when a model learns noise and specific details in training data.",
            "High variance = overfitting (model too complex)."
        ],
        "ground_truth": "Overfitting happens when a model learns noise and specific details in training data, harming its performance on new data."
    },
    {
        "question": "Explain confusion matrix",
        "answer": "Confusion matrix compares actual vs predicted labels with TP, TN, FP, FN.",
        "contexts": [
            "A confusion matrix is a table that compares actual vs predicted class labels.",
            "Contains True Positives (TP), True Negatives (TN), False Positives (FP), False Negatives (FN)."
        ],
        "ground_truth": "Confusion matrix contains TP, TN, FP, FN comparing actual vs predicted labels."
    }
]

def get_sample_data() -> list:
    return SAMPLE_EVAL_DATA
