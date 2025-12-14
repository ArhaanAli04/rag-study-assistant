from topic_classifier import topic_classifier

queries = [
    "what is unsupervised learning in machine learning",
    "what is part of speech tagging",
    "explain quantum entanglement",
    "how does photosynthesis work",
    "what is bubble sort algorithm",
    "hello how are you",
    "explain TCP/IP protocol",
]

print("Testing LLM-based Topic Classifier")
print("=" * 60)

for query in queries:
    result = topic_classifier.classify_topic(query)
    print(f"\nQuery: {query}")
    print(f"Topic: {result['topic']}")
    print(f"Confidence: {result['confidence']:.2f}")
    print(f"Method: {result['method']}")
