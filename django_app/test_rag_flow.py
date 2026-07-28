import os
import django
import tempfile
import sys
from unittest.mock import MagicMock
from django.core.files.uploadedfile import SimpleUploadedFile

# Setup Django Environment
# Add the directory containing 'audit_backend' (which is this script's directory) to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auditportal.settings')
django.setup()

from dashboard.models import ContextDocument, DocumentChunk
from dashboard.ai_service import AuditAI

def test_rag_logic():
    print("=== RAG Flow Test ===")
    print(f"Python Executable: {sys.executable}")
    
    # Check for local embedding capability
    try:
        from sentence_transformers import SentenceTransformer
        has_local_model = True
        print("[OK] sentence-transformers is installed. Running in REAL mode.")
    except ImportError:
        has_local_model = False
        print("[WARN] sentence-transformers NOT found. Running in MOCK mode.")

    # 1. Create a temporary text file for extraction test
    print("\n1. Testing Document Ingestion...")
    
    # Create content (Longer to force chunking if size was small, but verifying existence is enough)
    content = b"The company policy forbids gifts over $50 from vendors. Approval is required for all software subscriptions. " * 20
    
    try:
        # Create ContextDocument using SimpleUploadedFile to handle storage correctly
        suf = SimpleUploadedFile("policy.txt", content, content_type="text/plain")
        
        doc = ContextDocument.objects.create(
            title="Gift & Software Policy",
            file=suf
        )
        
        ai = AuditAI(user_id='test_user')
        
        # Test Extraction
        print("   Extracting text from file...")
        ai.extract_text_from_file(doc)
        doc.refresh_from_db()
        
        if doc.extracted_text and "forbids gifts" in doc.extracted_text:
            print(f"   [OK] Text Extraction Successful: '{doc.extracted_text[:30]}...'")
        else:
            print(f"   [FAIL] Text Extraction Failed: {doc.extracted_text}")

        # Test Embedding
        print("\n2. Testing Embedding Generation & Chunking...")
        
        if not has_local_model:
                # Mock generate_embedding to return a fixed vector
            ai.generate_embedding = MagicMock(return_value=[1.0, 0.0, 0.0])
            print("   (Mocking embedding generation)")

        success = ai.process_document_embedding(doc.id)
        
        doc.refresh_from_db()
        if success and doc.embedding_vector:
            vec_len = len(doc.embedding_vector)
            print(f"   [OK] Embedding Generated. Vector Length: {vec_len}")
            
            # Check Chunks
            chunk_count = DocumentChunk.objects.filter(document=doc).count()
            if chunk_count > 0:
                 print(f"   [OK] Chunks Created: {chunk_count}")
            else:
                 print(f"   [FAIL] No chunks created.")
                 
        else:
            print("   [FAIL] Embedding Generation Failed.")

        # Test Query
        print("\n3. Testing RAG Retrieval...")
        
        query = "What is the policy on gifts?"
        print(f"   Query: '{query}'")
        
        if not has_local_model:
            # Mock generate_embedding for the query too
            ai.generate_embedding = MagicMock(return_value=[0.9, 0.1, 0.0])
        
        results = ai.query_corporate_brain(query)
        
        found = any(r['doc'] == "Gift & Software Policy" for r in results)
        if found:
            print(f"   [OK] SUCCESS: Retrieved document! Top score: {results[0]['score']:.4f}")
            print(f"   Snippet: {results[0]['summary'][:100]}...")
        else:
            print(f"   [FAIL] FAILURE: Document not found.")
            print(f"   Results: {results}")

    except Exception as e:
        print(f"   [ERROR] Exception during test: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Cleanup
        if 'doc' in locals() and doc.id:
            # Delete file from storage
            if doc.file:
                doc.file.delete(save=False)
            doc.delete()

if __name__ == "__main__":
    test_rag_logic()
