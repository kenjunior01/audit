from sentence_transformers import SentenceTransformer
print("Imported successfully")
model = SentenceTransformer('all-MiniLM-L6-v2')
print("Model loaded")
vec = model.encode("This is a test")
print(f"Vector generated: {len(vec)}")
