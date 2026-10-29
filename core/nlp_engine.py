import os
import pickle
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

MODEL_PATH = "models/intent_classifier.pkl"
DATA_PATH = "data/training_set_large.csv"

def train_and_save_model():
    """Trains a TF-IDF + Logistic Regression classifier."""
    if not os.path.exists(DATA_PATH):
        print(f"❌ Error: {DATA_PATH} not found.")
        return False
        
    df = pd.read_csv(DATA_PATH)
    
    # Create Pipeline: Vectorizer -> Classifier
    pipeline = Pipeline([
        ('tfidf', TfidfVectorizer(stop_words='english')),
        ('clf', LogisticRegression(max_iter=1000))
    ])
    
    # Train
    print("🧠 Training NLP Model...")
    pipeline.fit(df['text'], df['intent'])
    
    # Save
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    with open(MODEL_PATH, 'wb') as f:
        pickle.dump(pipeline, f)
        
    print(f"✅ Model Saved to {MODEL_PATH}")
    return True

def predict_intent(text):
    """Loads model and predicts intent with confidence score."""
    if not os.path.exists(MODEL_PATH):
        print("⚠️ Warning: No trained model found. Returning UNKNOWN.")
        return {"intent": "UNKNOWN", "confidence": 0.0}
        
    with open(MODEL_PATH, 'rb') as f:
        model = pickle.load(f)
        
    try:
        prediction = model.predict([text])[0]
        probabilities = model.predict_proba([text])[0]
        max_prob = float(max(probabilities))
        
        return {
            "intent": prediction,
            "confidence": round(max_prob, 4),
            "probabilities": dict(zip(model.classes_, [round(float(p), 4) for p in probabilities]))
        }
    except Exception as e:
        print(f"❌ Prediction Error: {e}")
        return {"intent": "ERROR", "confidence": 0.0}

if __name__ == "__main__":
    train_and_save_model()
