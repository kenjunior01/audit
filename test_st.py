def main():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("sentence-transformers not installed. Skipping local embedding smoke test.")
        return 0

    print("Imported successfully")
    model = SentenceTransformer('all-MiniLM-L6-v2')
    print("Model loaded")
    vec = model.encode("This is a test")
    print(f"Vector generated: {len(vec)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
