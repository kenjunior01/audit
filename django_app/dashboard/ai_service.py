import json
import requests
import os
import math
import numpy as np
from datetime import timedelta
from django.db.models import Count, Avg, Sum
from django.utils import timezone
from .models import Transaction, AiFeedback, Alert, ContextProfile, RegulatoryRule, AuditCase, ReferenceItem, ContextDocument, DocumentChunk, IntegrationSettings, AIGovernanceEvent, RiskAgent, ExternalActionTemplate
import re
import logging
import time

# Mem0 Integration (Persistent Memory)
try:
    from mem0 import Memory
    MEM0_AVAILABLE = True
except ImportError:
    MEM0_AVAILABLE = False
    print("AI Service: Mem0 not installed. Persistent memory disabled.")

logger = logging.getLogger(__name__)

# Optional: Local Embeddings
# Initialize as None, load lazily
LOCAL_EMBEDDING_MODEL = None

def get_local_embedding_model():
    """Disabled local model to avoid hangs on download in restricted environment."""
    return None

# Using Hugging Face Inference API (Fallback)
HF_API_URL = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2"
HF_EMBEDDING_URL = "https://api-inference.huggingface.co/pipeline/feature-extraction/sentence-transformers/all-MiniLM-L6-v2"

class PersistentMemory:
    _instance = None
    
    @classmethod
    def get_instance(cls):
        print(f"[DEBUG] PersistentMemory.get_instance() chamado. _instance existe? {cls._instance is not None}")
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
        
    def __init__(self):
        self.memory = None
        # self.memory = None
        # if MEM0_AVAILABLE:
        #     # Check if Ollama is running before initializing to avoid hangs
        #     try:
        #         requests.get("http://localhost:11434", timeout=1)
        #         
        #         self.memory = Memory.from_config({
        #             "vector_store": {
        #                 "provider": "chroma",
        #                 "config": {
        #                     "collection_name": "audit_memory",
        #                     "path": "./chroma_db"
        #                 }
        #             },
        #             "llm": {
        #                 "provider": "ollama",
        #                 "config": {
        #                     "model": "deepseek-r1:1.5b",
        #                     "temperature": 0.1
        #                 }
        #             }
        #         })
        #     except requests.exceptions.ConnectionError:
        #         print("AI Service: Ollama is not running. Persistent Memory disabled.")
        #     except Exception as e:
        #         print(f"PersistentMemory Init Error: {e}")
    
    def add(self, text, user_id=None, metadata=None):
        if self.memory:
            try:
                self.memory.add(text, user_id=str(user_id) if user_id else "system", metadata=metadata)
                return True
            except Exception as e:
                print(f"Mem0 Add Error: {e}")
        return False

    def search(self, query, user_id=None, limit=3):
        if self.memory:
            try:
                # Search specifically for this user or system-wide if user_id is None
                # Mem0 search signature might vary, assuming standard .search(query, user_id=...)
                return self.memory.search(query, user_id=str(user_id) if user_id else "system", limit=limit)
            except Exception as e:
                print(f"Mem0 Search Error: {e}")
        return []

class AuditAI:
    def __init__(self, user_id=None):
        self.user_id = user_id
        self.api_key = os.environ.get("HF_API_KEY")
        
        # Initialize Persistent Memory (Mem0) via Singleton
        self.mem_service = PersistentMemory.get_instance()
        # Keep self.mem0 for backward compatibility if needed, but rely on service
        self.mem0 = self.mem_service.memory
        
        # Check if Ollama is actually available for general generation
        self.ollama_available = False
        if self.mem_service.memory: # If memory initialized, Ollama was reachable
            self.ollama_available = True
        else:
            # Quick check if memory is disabled but Ollama is still there
            try:
                requests.get("http://localhost:11434", timeout=0.5)
                self.ollama_available = True
            except:
                self.ollama_available = False

    def _log_governance_event(self, event_type, model_name, input_data, output_data, latency_ms, status='SUCCESS', confidence_score=None):
        """Logs an event for AI Governance monitoring."""
        print(f"[DEBUG] _log_governance_event: {event_type}, {status}")
        
        # Anomaly Detection Logic
        metadata = {}
        if status == 'SUCCESS' and confidence_score is not None and confidence_score < 0.3:
            metadata['anomaly_flag'] = 'LOW_CONFIDENCE'
            metadata['anomaly_reason'] = f"Confidence score {confidence_score} is below threshold (0.3)"
        
        if status == 'HALLUCINATION':
            metadata['anomaly_flag'] = 'CRITICAL_HALLUCINATION'
            metadata['anomaly_reason'] = "User reported AI hallucination"

        try:
            event = AIGovernanceEvent.objects.create(
                event_type=event_type,
                model_name=model_name,
                input_data=input_data,
                output_data=output_data,
                latency_ms=latency_ms,
                status=status,
                confidence_score=confidence_score,
                user_id=self.user_id,
                metadata=metadata
            )
            print(f"[DEBUG] Evento criado com ID: {event.id}")
            
            # If critical anomaly, create an Audit Alert
            if metadata.get('anomaly_flag') == 'CRITICAL_HALLUCINATION':
                from .models import Alert
                Alert.objects.create(
                    alert_type="AI_GOVERNANCE_ANOMALY",
                    description=f"ALERTA CRÍTICO: Alucinação detectada no modelo {model_name}. Evento ID: {event.id}",
                    severity="Critical",
                    status="New"
                )
        except Exception as e:
            print(f"Error logging governance event: {e}")

    def suggest_investigation_steps(self, case):
        """
        Uses AI and Persistent Memory to suggest specific investigation steps for an Audit Case.
        """
        start_time = time.time()
        # 1. Gather context
        print("[DEBUG] ENTERING suggest_investigation_steps")
        transaction = None
        if case.transaction_id:
            try:
                if str(case.transaction_id).isdigit():
                    transaction = Transaction.objects.filter(id=int(case.transaction_id)).first()
                if not transaction:
                    transaction = Transaction.objects.filter(transaction_id=case.transaction_id).first()
            except:
                pass

        # 2. Search for similar cases in Persistent Memory
        memory_context = ""
        if self.mem_service:
            try:
                similar_cases = self.mem_service.search(
                    f"Audit case like: {case.title} {case.description}",
                    limit=2
                )
                if similar_cases:
                    memory_context = "HISTÓRICO INSTITUCIONAL (Casos Similares):\n"
                    for mem in similar_cases:
                        memory_context += f"- {mem.get('text', '')}\n"
            except:
                pass

        prompt = f"""
        ACT AS: Senior Audit Investigator.
        TASK: Suggest 3-5 specific investigation steps for this case.
        
        CASE: {case.title}
        DESCRIPTION: {case.description}
        PRIORITY: {case.priority}
        
        {memory_context}
        """
        if transaction:
            prompt += f"TRANSACTION: {transaction.vendor}, {transaction.amount} {transaction.currency}\n"
            if transaction.xai_explanation:
                prompt += f"RISK REASONS: {json.dumps(transaction.xai_explanation.get('reasons', []))}\n"

        prompt += """
        REQUIREMENTS:
        - List format (1. 2. 3.).
        - Action-oriented.
        - Portuguese language.
        - Professional and objective.
        - If institutional history is provided, incorporate lessons learned.
        """

        steps = "1. Analisar documentação suporte.\n2. Verificar histórico do fornecedor.\n3. Confirmar aprovações internas."
        model_used = "Rule-based (Fallback)"
        status = "SUCCESS"
        
        try:
            # Try Ollama only if available
            if self.ollama_available:
                import requests
                model_used = "Ollama/DeepSeek-R1"
                ollama_resp = requests.post('http://localhost:11434/api/generate', json={
                    "model": "deepseek-r1:1.5b",
                    "prompt": prompt,
                    "stream": False
                }, timeout=0.5) # Reduced timeout even more
                if ollama_resp.status_code == 200:
                    steps = ollama_resp.json().get('response', '')
                else:
                    # Fallback to HF
                    model_used = "HuggingFace/Mistral"
                    hf_resp = self._query_llm({"inputs": prompt})
                    if hf_resp and isinstance(hf_resp, list) and 'generated_text' in hf_resp[0]:
                        steps = hf_resp[0]['generated_text']
                    else:
                        status = "FAILED"
            else:
                model_used = "HuggingFace/Mistral"
                hf_resp = self._query_llm({"inputs": prompt})
                if hf_resp and isinstance(hf_resp, list) and 'generated_text' in hf_resp[0]:
                    steps = hf_resp[0]['generated_text']
                else:
                    status = "FAILED"
        except Exception as e:
            status = "FAILED"
            pass

        latency = int((time.time() - start_time) * 1000)
        self._log_governance_event(
            event_type='SUGGEST_STEPS',
            model_name=model_used,
            input_data={'prompt': prompt},
            output_data={'steps': steps},
            latency_ms=latency,
            status=status
        )

        return steps

    def auto_assign_case(self, case):
        """
        Simulates automatic assignment of a case to an auditor.
        """
        # Mock logic: assign based on priority
        priority = case.priority
        
        assigned_to = "Junior Auditor"
        if priority == 'Critical':
            assigned_to = "Chief Auditor"
        elif priority == 'High':
            assigned_to = "Senior Auditor"
            
        try:
            from .models import AuditCase
            AuditCase.objects.filter(id=case.id).update(assigned_to=assigned_to)
            case.assigned_to = assigned_to # Update local object
        except Exception as e:
            print(f"Error auto-assigning case: {e}")
            
        return assigned_to

    def generate_case_report(self, case):
        """
        Generates a comprehensive investigation report for an Audit Case.
        """
        # 1. Gather Context
        transaction = None
        if case.transaction_id:
            try:
                # Try ID first, then transaction_id string
                if case.transaction_id.isdigit():
                    transaction = Transaction.objects.filter(id=int(case.transaction_id)).first()
                if not transaction:
                    transaction = Transaction.objects.filter(transaction_id=case.transaction_id).first()
            except:
                pass

        comments = case.comments.all().order_by('created_at')
        attachments = case.attachments.all()
        
        # 2. Build Prompt for Executive Summary
        user_ctx = self.build_user_context()
        country = user_ctx.get("country") or "Unknown"
        regs = user_ctx.get("regulatory_frameworks") or []
        domains = user_ctx.get("audit_domains") or []
        risk_appetite = user_ctx.get("risk_appetite") or "Balanced"

        context_str = f"Case Title: {case.title}\nDescription: {case.description}\nPriority: {case.priority}\nStatus: {case.status}\n"
        if transaction:
            context_str += f"Transaction: {transaction.vendor} - {transaction.amount} {transaction.currency}\n"
            if transaction.xai_explanation:
                context_str += f"AI Risk Factors: {json.dumps(transaction.xai_explanation.get('reasons', []))}\n"
            # If transaction category is outside current audit domains, make it explicit in the prompt
            tx_category = getattr(transaction, 'category', None)
            if tx_category and domains and tx_category not in domains:
                context_str += f"OUT-OF-SCOPE NOTE: This transaction belongs to category '{tx_category}', which is currently outside the configured audit domains in scope.\n"
        
        if comments.exists():
            context_str += "Investigation Notes:\n" + "\n".join([f"- {c.comment}" for c in comments])

        prompt = f"""
        ACT AS: Chief Internal Auditor.
        TASK: Write an Executive Summary for Audit Case #{case.id}.
        
        REGULATORY CONTEXT:
        - Country: {country}
        - Regulatory Frameworks: {", ".join(regs) if regs else "None specified"}
        - Audit Domains in Scope: {", ".join(domains) if domains else "General"}
        - Risk Appetite: {risk_appetite}
        
        CONTEXT:
        {context_str}
        
        REQUIREMENTS:
        - Concise paragraph (max 150 words).
        - Highlight key risks and recommended actions.
        - Explicitly mention if the case or underlying transaction is outside the configured audit domains or country (OUT-OF-SCOPE NOTE).
        - Professional tone.
        - Portuguese language.
        """
        
        # Call LLM (Reuse _query_llm or generic generation)
        executive_summary = "Resumo indisponível no momento."
        try:
            # Try Ollama first if available (mimicking generate_work_paper_content logic)
            if self.ollama_available:
                import requests
                print("AuditAI: Tentando gerar resumo executivo via Ollama...")
                ollama_resp = requests.post('http://localhost:11434/api/generate', json={
                    "model": "deepseek-r1:1.5b",
                    "prompt": prompt,
                    "stream": False
                }, timeout=3)
                if ollama_resp.status_code == 200:
                    print("AuditAI: Resumo gerado via Ollama.")
                    executive_summary = ollama_resp.json().get('response', '')
                else:
                    print(f"AuditAI: Ollama retornou {ollama_resp.status_code}. Tentando HF...")
                    # Fallback
                    hf_resp = self._query_llm({"inputs": prompt})
                    if hf_resp and isinstance(hf_resp, list) and 'generated_text' in hf_resp[0]:
                        print("AuditAI: Resumo gerado via HF.")
                        executive_summary = hf_resp[0]['generated_text']
            else:
                print("AuditAI: Ollama indisponível para resumo executivo. Tentando HF...")
                hf_resp = self._query_llm({"inputs": prompt})
                if hf_resp and isinstance(hf_resp, list) and 'generated_text' in hf_resp[0]:
                    print("AuditAI: Resumo gerado via HF.")
                    executive_summary = hf_resp[0]['generated_text']
        except Exception as e:
            print(f"AuditAI: Erro no resumo executivo ({type(e).__name__}).")
            pass

        # 3. Structure Response
        report = {
            "executive_summary": executive_summary,
            "risk_analysis": {
                "xai_explanation": transaction.xai_explanation if transaction else None
            },
            "evidence": [
                {"name": a.file_name, "url": a.file_url, "uploaded_by": a.uploaded_by} 
                for a in attachments
            ],
            "investigation_log": [
                {"user": c.user_id, "date": c.created_at.strftime('%d/%m/%Y %H:%M'), "content": c.comment}
                for c in comments
            ],
            "metadata": {
                "generated_by": "AuditAI Agent",
                "generated_at": timezone.now().isoformat()
            }
        }
        
        return report

    def generate_work_paper_content(self, transaction, risk_score, reasons):
        """
        Generates a formal Audit Work Paper (NBC TA style) using the LLM.
        """
        # Construct prompt with transaction details, risk, and RAG context
        user_ctx = self.build_user_context()
        country = user_ctx.get("country") or "Unknown"
        regs = user_ctx.get("regulatory_frameworks") or []
        domains = user_ctx.get("audit_domains") or []
        risk_appetite = user_ctx.get("risk_appetite") or "Balanced"

        prompt = f"""
        ACT AS: Senior Auditor adhering to NBC TA standards.
        TASK: Generate a Draft Audit Work Paper for the following transaction.
        
        TRANSACTION:
        ID: {transaction.id}
        Vendor: {transaction.vendor}
        Amount: {transaction.amount}
        Date: {transaction.date}
        Description: {transaction.description}
        
        RISK ASSESSMENT:
        Score: {risk_score}
        Flags: {json.dumps(reasons)}
        
        REGULATORY CONTEXT:
        - Country: {country}
        - Regulatory Frameworks: {", ".join(regs) if regs else "None specified"}
        - Audit Domains in Scope: {", ".join(domains) if domains else "General"}
        - Risk Appetite: {risk_appetite}
        
        OUT-OF-SCOPE INSTRUCTIONS:
        - If the transaction category or country is outside the configured audit domains or country in scope, explicitly document this in the Scope section as \"fora do escopo atual da auditoria\" and explain the implication for conclusions.
        
        REQUIREMENTS:
        - Output Format: Markdown.
        - Structure: 
          1. Objective (Objetivo)
          2. Scope (Escopo)
          3. Methodology (Metodologia)
          4. Findings (Achados)
          5. Conclusion/Recommendation (Conclusão)
        - Tone: Formal, objective, professional.
        - Language: Portuguese (Brazil).
        - Do not include conversational filler. Start directly with the report title.
        """
        
        # Call LLM
        # Use _query_llm which falls back to HF, but ideally we use Ollama if available locally
        try:
             if self.ollama_available:
                 import requests
                 print("AuditAI: Tentando gerar papel de trabalho via Ollama...")
                 ollama_resp = requests.post('http://localhost:11434/api/generate', json={
                     "model": "deepseek-r1:1.5b",
                     "prompt": prompt,
                     "stream": False
                 }, timeout=3)
                 if ollama_resp.status_code == 200:
                     print("AuditAI: Papel de trabalho gerado via Ollama.")
                     return ollama_resp.json().get('response', '')
        except:
             pass

        # Fallback to HF
        response = self._query_llm({"inputs": prompt})
        if response and isinstance(response, list) and 'generated_text' in response[0]:
            return response[0]['generated_text']
            
        return "Work paper generation failed or LLM unavailable."

    def _query_llm(self, payload):
        if self.api_key:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            try:
                response = requests.post(HF_API_URL, headers=headers, json=payload, timeout=5)
                return response.json()
            except:
                pass
        return None

    def process_alert_feedback(self, alert_id, feedback_type, comment=None):
        """
        Processes human feedback on an alert and updates the relevant risk agent's reputation.
        This is the core of the Auto-Adaptive AI feedback loop.
        """
        from .models import Alert, RiskAgent, AiFeedback
        
        try:
            alert = Alert.objects.get(id=alert_id)
            
            # 1. Store feedback for long-term memory
            AiFeedback.objects.create(
                transaction_id=alert.transaction.transaction_id if alert.transaction else None,
                user_id=self.user_id,
                feedback_type=feedback_type,
                comment=f"Alert {alert_id} ({alert.alert_type}): {comment or ''}"
            )

            # 2. Identify if this alert was generated by a Risk Agent
            if "Agent Finding:" in alert.alert_type:
                agent_name = alert.alert_type.replace("Agent Finding: ", "").strip()
                agent = RiskAgent.objects.filter(name=agent_name).first()
                
                if agent:
                    old_rep = agent.reputation_score
                    if feedback_type == 'accurate' or feedback_type == 'helpful':
                        # Reward accurate detection
                        agent.reputation_score = min(agent.reputation_score + 0.1, 2.0)
                        
                        # Add to institutional memory
                        if self.mem_service:
                            self.mem_service.add(
                                f"Agent {agent.name} correctly identified risk in transaction {alert.transaction.transaction_id if alert.transaction else 'unknown'}. Pattern: {alert.description}",
                                user_id=self.user_id,
                                metadata={"agent": agent.name, "type": "positive_feedback"}
                            )
                    elif feedback_type == 'inaccurate' or feedback_type == 'not_helpful':
                        # Penalize false positive
                        agent.reputation_score = max(agent.reputation_score - 0.2, 0.0)
                        
                        # Add to institutional memory
                        if self.mem_service:
                            self.mem_service.add(
                                f"Agent {agent.name} incorrectly flagged transaction {alert.transaction.transaction_id if alert.transaction else 'unknown'} as risk. This was a False Positive.",
                                user_id=self.user_id,
                                metadata={"agent": agent.name, "type": "negative_feedback"}
                            )
                    
                    agent.save()
                    print(f"ADAPTIVE: Updated reputation for agent '{agent.name}': {old_rep:.2f} -> {agent.reputation_score:.2f}")
            
            return True
        except Exception as e:
            print(f"Error processing alert feedback: {e}")
            return False

    def build_user_context(self):
        """
        Builds a deep profile of the user based on their entire history.
        """
        if not self.user_id:
            return {
                "persona": "Anonymous", 
                "trust_score": 0.5,
                "stats": {'total': 0, 'confirmations': 0},
                "learning_progress": 0,
                "department": None,
                "sector": "Other",
                "org_structure": "Functional",
                "avg_transaction_val": 0,
                "top_vendors": []
            }

        # 1. Feedback History
        print(f"[DEBUG] build_user_context para user_id: {self.user_id}")
        feedbacks = AiFeedback.objects.filter(user_id=self.user_id)
        feedback_stats = {
            'total': feedbacks.count(),
            'false_positives': feedbacks.filter(feedback_type='inaccurate').count(),
            'confirmations': feedbacks.filter(feedback_type='accurate').count()
        }

        # 2. Transaction History (Actions)
        # Assuming we track who approved/reviewed transactions (simplified here via user_id on transaction if that implies ownership/action)
        user_txs = Transaction.objects.filter(user_id=self.user_id)
        
        avg_amount = user_txs.aggregate(Avg('amount'))['amount__avg'] or 0
        preferred_vendors = user_txs.values('vendor').annotate(count=Count('id')).order_by('-count')[:5]
        
        # 3. Derive Persona
        persona = "Standard Auditor"
        if feedback_stats['false_positives'] > feedback_stats['confirmations'] * 2:
            persona = "Skeptical Analyst"
        elif avg_amount > 50000:
            persona = "High-Value Approver"
            
        # Persist Persona to Profile
        profile_dept = None
        try:
            uid = str(self.user_id)
            profile, created = ContextProfile.objects.get_or_create(user_id=uid)
            if profile.persona != persona:
                profile.persona = persona
                profile.save()
            profile_dept = profile.department
            profile_sector = profile.sector
            profile_structure = profile.org_structure
            profile_limits = profile.approval_limits
            profile_onboarding = profile.onboarding_data
            profile_country = profile.country
            profile_regulations = profile.regulatory_frameworks
            profile_domains = profile.audit_domains
            profile_risk_appetite = profile.risk_appetite
        except Exception as e:
            print(f"Error updating profile: {e}")
            profile_sector = 'Other'
            profile_structure = 'Functional'
            profile_limits = {}
            profile_onboarding = {}
            profile_country = None
            profile_regulations = []
            profile_domains = []
            profile_risk_appetite = 'Balanced'
            pass
            
        return {
            "stats": feedback_stats,
            "avg_transaction_val": avg_amount,
            "top_vendors": [v['vendor'] for v in preferred_vendors],
            "persona": persona,
            "department": profile_dept,
            "sector": profile_sector,
            "org_structure": profile_structure,
            "approval_limits": profile_limits,
            "onboarding": profile_onboarding,
            "country": profile_country,
            "regulatory_frameworks": profile_regulations,
            "audit_domains": profile_domains,
            "risk_appetite": profile_risk_appetite,
            "learning_progress": min(100, feedback_stats['total'] * 5) # 20 feedbacks = 100% calibrated
        }

    def generate_embedding(self, text):
        """
        Generates embedding using Local Model (preferred) or HF API (fallback).
        Returns a list of floats.
        """
        print(f"[DEBUG] generate_embedding para texto: {text[:30]}...")
        if not text:
            return None
            
        # 1. Try Local Model (Self-Hosted / Open Source)
        model = get_local_embedding_model()
        if model:
            try:
                print("[DEBUG] Usando modelo de embedding local...")
                # encode returns a numpy array
                embedding = model.encode(text).tolist()
                return embedding
            except Exception as e:
                print(f"Local Embedding Error: {e}")

        # 2. Fallback to API
        print("[DEBUG] Tentando fallback para HF API para embedding...")
        if not self.api_key:
            print("[DEBUG] Sem API Key para HF. Abortando embedding.")
            return None
            
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {"inputs": text, "options": {"wait_for_model": True}}
        try:
            response = requests.post(HF_EMBEDDING_URL, headers=headers, json=payload, timeout=2) # Reduzi timeout
            print(f"[DEBUG] Resposta HF Embedding status: {response.status_code}")
            data = response.json()
            # HF API returns list of floats for single string input
            if isinstance(data, list) and len(data) > 0 and isinstance(data[0], float):
                return data
            return None
        except Exception as e:
            print(f"Embedding error: {e}")
            return None

    def chunk_text(self, text, chunk_size=500, overlap=50):
        """
        Splits text into chunks of chunk_size with overlap.
        """
        if not text:
            return []
        
        chunks = []
        start = 0
        text_len = len(text)
        
        while start < text_len:
            end = start + chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            start += chunk_size - overlap
            
        return chunks

    def process_document_embedding(self, doc_id):
        try:
            doc = ContextDocument.objects.get(id=doc_id)
            
            # Extract Text if file exists and extracted_text is empty
            if doc.file and not doc.extracted_text:
                self.extract_text_from_file(doc)
            
            if doc.extracted_text:
                # Clear existing chunks if any (reprocessing)
                DocumentChunk.objects.filter(document=doc).delete()
                
                # Create Chunks
                chunks_text = self.chunk_text(doc.extracted_text)
                
                # Generate Embedding for Document Level (Summary)
                # Still useful for broad matches or if chunks fail
                doc_vector = self.generate_embedding(doc.extracted_text[:1000])
                if doc_vector:
                    doc.embedding_vector = doc_vector
                
                # Generate Embeddings for Chunks
                for i, chunk_text in enumerate(chunks_text):
                    vector = self.generate_embedding(chunk_text)
                    if vector:
                        DocumentChunk.objects.create(
                            document=doc,
                            chunk_index=i,
                            text=chunk_text,
                            embedding_vector=vector
                        )
                
                doc.processed = True
                doc.save()
                return True
        except Exception as e:
            print(f"Doc processing error: {e}")
        return False

    def extract_text_from_file(self, doc):
        """
        Extracts text from PDF or Text files locally using pypdf.
        """
        try:
            file_path = doc.file.path
            ext = os.path.splitext(file_path)[1].lower()
            text = ""
            
            if ext == '.pdf':
                from pypdf import PdfReader
                reader = PdfReader(file_path)
                for page in reader.pages:
                    text += page.extract_text() + "\n"
            elif ext == '.txt' or ext == '.csv':
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
            
            if text:
                doc.extracted_text = text.strip()
                doc.save()
        except Exception as e:
            print(f"Text extraction error for {doc.title}: {e}")

    @staticmethod
    def cosine_similarity(v1, v2):
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        dot_product = sum(a * b for a, b in zip(v1, v2))
        magnitude1 = math.sqrt(sum(a * a for a in v1))
        magnitude2 = math.sqrt(sum(b * b for b in v2))
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        return dot_product / (magnitude1 * magnitude2)

    def query_corporate_brain(self, query):
        """
        RAG Implementation: Search in ContextDocuments using Vector Similarity (or fallback to keywords).
        """
        print(f"[DEBUG] query_corporate_brain: {query}")
        results = []
        
        # 1. Try Vector Search (if API Key available)
        query_embedding = self.generate_embedding(query)
        
        # Search Chunks first (Granular)
        if query_embedding:
            chunks = DocumentChunk.objects.select_related('document').all()
            for chunk in chunks:
                if chunk.embedding_vector:
                    score = self.cosine_similarity(query_embedding, chunk.embedding_vector)
                    if score > 0.30: # Slightly higher threshold for chunks
                        # De-duplicate by document title in results if needed, or allow multiple hits
                        snippet = chunk.text
                        results.append({'doc': chunk.document.title, 'score': score, 'summary': snippet})

        # Search Documents (Broad/Legacy)
        docs = ContextDocument.objects.filter(processed=True)
        
        if query_embedding:
            for doc in docs:
                if doc.embedding_vector:
                    score = self.cosine_similarity(query_embedding, doc.embedding_vector)
                    if score > 0.25: # Semantic threshold
                        snippet = doc.ai_summary or (doc.extracted_text[:200] + "..." if doc.extracted_text else "")
                        # Only add if not already present with higher score
                        if not any(r['doc'] == doc.title and r['score'] >= score for r in results):
                             results.append({'doc': doc.title, 'score': score, 'summary': snippet})
        
        # 2. Fallback to Keywords if no vector results
        if not results:
            keywords = query.split()
            for doc in docs:
                score = 0
                if doc.extracted_text:
                    for word in keywords:
                        if word.lower() in doc.extracted_text.lower():
                            score += 1
                if score > 0:
                    snippet = doc.ai_summary or (doc.extracted_text[:200] + "..." if doc.extracted_text else "")
                    results.append({'doc': doc.title, 'score': score * 0.1, 'summary': snippet}) # Lower score for keywords
        
        # Deduplicate results by document title, keeping highest score
        unique_results = {}
        for r in results:
            doc_title = r['doc']
            if doc_title not in unique_results or r['score'] > unique_results[doc_title]['score']:
                unique_results[doc_title] = r

        final_results = list(unique_results.values())
        print(f"[DEBUG] query_corporate_brain finalizado. Resultados: {len(final_results)}")
        return sorted(final_results, key=lambda x: x['score'], reverse=True)[:3]

    def generate_xai_log(self, transaction, risk_score, reasons, context):
        """
        Generates an immutable AI Audit Log (XAI) for the transaction.
        Returns a JSON-serializable dictionary.
        """
        return {
            "model_version": "AuditAI-v2.1-Hybrid",
            "timestamp": timezone.now().isoformat(),
            "risk_score": risk_score,
            "feature_weights": {
                "layer_1_personal": [r for r in reasons if "[Personal]" in r],
                "layer_2_corporate": [r for r in reasons if "[Corporate]" in r],
                "layer_3_global": [r for r in reasons if "[Global]" in r],
            },
            "context_snapshot": {
                "sector": context.get("sector"),
                "structure": context.get("org_structure"),
                "persona": context.get("persona")
            }
        }

    def evaluate_risk_agents(self, transaction):
        """
        Evaluates active RiskAgents against the transaction.
        Returns a list of triggered actions.
        """
        triggered_actions = []
        # Lazy import to avoid circular dependency if models import AuditAI
        from .models import RiskAgent, AuditCase
        
        agents = RiskAgent.objects.filter(active=True)
        
        for agent in agents:
            # Factor in reputation: If reputation < 0.5, skip the agent (it's too noisy)
            if agent.reputation_score < 0.5:
                print(f"Skipping noisy agent '{agent.name}' (Reputation: {agent.reputation_score:.2f})")
                continue

            conditions = agent.conditions # List of {metric, operator, value}
            if not conditions: continue
            
            match = True
            for cond in conditions:
                metric = cond.get('metric') or cond.get('field')
                if not metric:
                    match = False
                    break
                    
                operator = cond.get('operator')
                val_target = cond.get('value')
                
                # Get transaction value
                tx_val = getattr(transaction, metric, None)
                
                # Normalize types for comparison
                try:
                    if metric == 'amount': 
                        tx_val = float(transaction.amount)
                        val_target = float(val_target)
                    else:
                        tx_val = str(tx_val).lower() if tx_val else ""
                        val_target = str(val_target).lower()
                except Exception as e:
                    print(f"[DEBUG] Error normalizing {metric}: {e}")
                    match = False
                    break

                # Compare
                if operator == '>':
                    if not (tx_val > val_target): match = False
                elif operator == '<':
                    if not (tx_val < val_target): match = False
                elif operator == '=' or operator == '==':
                    if tx_val != val_target: match = False
                elif operator == 'contains':
                    if val_target not in tx_val: match = False
                elif operator == '!=':
                    if tx_val == val_target: match = False
                
                if not match: break
            
            if match:
                # Execute Action
                self.trigger_agent_action(agent, transaction)
                triggered_actions.append({'name': agent.name, 'action': agent.action})
                
        return triggered_actions

    def trigger_agent_action(self, agent, transaction):
        from .models import AuditCase, Alert, RiskAgentLog
        
        # Update agent stats
        agent.last_triggered = timezone.now()
        agent.save()
        
        action_summary = ""
        
        if agent.action == 'create_case_high':
            # Create a high priority case if one doesn't exist
            try:
                AuditCase.objects.get_or_create(
                    transaction_id=transaction.id,
                    defaults={
                        'title': f"Auto-Case: {agent.name}",
                        'description': f"Triggered by Risk Agent '{agent.name}'. Transaction matches criteria.",
                        'status': 'New',
                        'priority': 'High',
                        'created_by': 'RiskAgent'
                    }
                )
                action_summary = f"Created High Priority Case for Transaction {transaction.id}"
            except AuditCase.MultipleObjectsReturned:
                pass
        elif agent.action == 'flag_alert_critical':
            # Escalate existing alert or create new one
            # Calculate materiality for the alert
            materiality = 0.5 # Default
            try:
                # Try to get context for materiality
                context = self.build_user_context()
                materiality = self.calculate_materiality(transaction.amount, context)
            except:
                pass

            Alert.objects.update_or_create(
                transaction=transaction,
                defaults={
                    'alert_type': f"Agent: {agent.name}",
                    'severity': 'Critical',
                    'materiality': materiality,
                    'status': 'New',
                    'description': f"Critical Flag by Risk Agent '{agent.name}'",
                    'vendor': transaction.vendor,
                    'amount': transaction.amount
                }
            )
            action_summary = f"Flagged Critical Alert for Transaction {transaction.id}"
        elif agent.action == 'notify_manager':
            # Mock notification
            print(f"NOTIFY: Risk Agent {agent.name} triggered for TX {transaction.id}")
            action_summary = f"Notified Manager for Transaction {transaction.id}"
            
        elif agent.action == 'auto_resolve':
            # Auto-resolve existing alerts as False Positive
            updated = Alert.objects.filter(transaction=transaction).update(
                status='False Positive',
                description=f"Auto-resolved by Risk Agent '{agent.name}'. Criteria met."
            )
            if updated:
                print(f"AUTO-RESOLVE: {updated} alerts resolved for TX {transaction.id}")
                action_summary = f"Auto-resolved {updated} alerts for Transaction {transaction.id}"

        # Log the action
        if action_summary:
            # Calculate a risk score for the log (0-100)
            log_risk_score = 50.0 # Default
            if agent.reputation_score > 1.5: log_risk_score = 90.0
            elif agent.reputation_score < 0.8: log_risk_score = 30.0

            RiskAgentLog.objects.create(
                agent=agent,
                scanned_count=1,
                finding_summary=action_summary,
                finding_details={"transaction_id": transaction.id, "action": agent.action},
                risk_score=log_risk_score,
                suggested_action=agent.action
            )

    def calculate_materiality(self, amount, context):
        """
        Calculates the materiality of a transaction based on the organization's context.
        Materiality is a critical concept in audit, determining if a value is significant
        enough to warrant investigation.
        """
        if not amount: return 0.0
        
        # Base materiality: relative to approval limits
        limits = context.get('approval_limits', {})
        l2_limit = limits.get('L2', 50000) # Default L2 limit
        
        # If amount > L2 limit, it's highly material
        ratio = float(amount) / float(l2_limit)
        
        # Score from 0.0 to 1.0
        # 10% of L2 = 0.1 materiality
        # 100% of L2 = 1.0 materiality
        materiality = min(1.0, ratio)
        
        return materiality

    def analyze_transaction_risk(self, transaction, context=None):
        """
        Analyzes risk with specific adaptation to the user's historical preferences and organizational context.
        Context should be passed explicitly for robust analysis.
        """
        start_time = time.time()
        if context is None:
            context = self.build_user_context()

        # Fetch Integration Settings (AI Control Plane)
        settings = None
        try:
            # Handle user_id (might be 'system' or string)
            uid_int = 1 # Default fallback
            if self.user_id and str(self.user_id).isdigit():
                uid_int = int(self.user_id)
            settings = IntegrationSettings.objects.filter(user_id=uid_int).first()
        except:
            pass
        
        active_learning = settings.active_learning if settings else True
        sensitivity = settings.ai_sensitivity if settings else 0.5

        risk_score = 0.2 # Baseline
        reasons = []

        # Calculate Materiality
        print(f"[DEBUG] Calculando materialidade para valor: {transaction.amount}")
        materiality = self.calculate_materiality(transaction.amount, context)
        if materiality > 0.8:
            reasons.append(f"[Global] High Materiality: Transaction value is significant relative to org limits.")
            risk_score += 0.15
        elif materiality < 0.1:
             # Lower risk for very small transactions (Immaterial)
             risk_score -= 0.05

        # --- LAYER 0: AUTOMATION AGENTS (Hard Rules) ---
        print(f"[DEBUG] Avaliando agentes de automação para TX: {transaction.id}")
        triggered_agents = self.evaluate_risk_agents(transaction)
        if triggered_agents:
            agent_names = [a['name'] for a in triggered_agents]
            reasons.append(f"[Automation] Triggered Risk Agents: {', '.join(agent_names)}")
            
            # Boost risk weighted by average reputation of triggered agents
            from .models import RiskAgent
            total_rep = 0
            for a_info in triggered_agents:
                agent_obj = RiskAgent.objects.filter(name=a_info['name']).first()
                if agent_obj:
                    total_rep += agent_obj.reputation_score
            
            avg_rep = total_rep / len(triggered_agents) if triggered_agents else 1.0
            risk_boost = (0.1 * len(triggered_agents)) * avg_rep
            risk_score += risk_boost
            
            if avg_rep > 1.2:
                reasons.append(f"[Automation] Risk boost amplified by high-reputation agents (Avg Rep: {avg_rep:.2f})")
            elif avg_rep < 0.8:
                reasons.append(f"[Automation] Risk boost reduced due to low-reputation agents (Avg Rep: {avg_rep:.2f})")

        # --- LAYER 1: PERSONAL (User Context, Onboarding, Feedback) ---
        print("[DEBUG] Entrando no LAYER 1: PERSONAL")
        # 1.1 Onboarding Concerns (Hot Data)
        onboarding = context.get('onboarding', {})
        risk_concern = onboarding.get('risk_concern', '').lower()
        is_high_risk_cat = any(cat in (transaction.category or '') for cat in ['Consulting', 'Services'])
        if ('suborno' in risk_concern or 'bribery' in risk_concern) and is_high_risk_cat:
            risk_score += 0.2
            reasons.append("[Personal] Higher sensitivity for Services due to your onboarding concern (Bribery).")

        # 1.2 Vendor Trust (Personal History)
        if transaction.vendor in context.get('top_vendors', []):
            risk_score -= 0.2
            reasons.append(f"[Personal] Trusted vendor based on your history: {transaction.vendor}")

        # 1.3 Feedback Loop (Learning)
        if active_learning:
            recent_vendor_feedback = AiFeedback.objects.filter(
                user_id=self.user_id,
                comment__icontains=transaction.vendor if transaction.vendor else "UNKNOWN_VENDOR"
            ).last()
            if recent_vendor_feedback and recent_vendor_feedback.feedback_type == 'inaccurate':
                 risk_score -= 0.3
                 reasons.append(f"[Personal] You previously marked alerts for {transaction.vendor} as False Positives.")

        # --- LAYER 2: CORPORATE (Org Structure, Sector, RAG, Reference Lists) ---
        print("[DEBUG] Entrando no LAYER 2: CORPORATE")
        # 2.1 Sector & Structure
        sector = context.get('sector', 'Other')
        structure = context.get('org_structure', 'Functional')
        
        if sector == 'SaaS':
            if transaction.category in ['Raw Materials', 'Inventory', 'Manufacturing Equipment']:
                risk_score += 0.4
                reasons.append(f"[Corporate] SaaS Anomaly: '{transaction.category}' is unusual for your sector.")
            if transaction.amount > 100000 and 'Subscription' not in (transaction.vendor or ''):
                risk_score += 0.1
                reasons.append("[Corporate] Large one-time payment in SaaS model warrants revenue recognition review.")
        elif sector == 'Manufacturing':
             if transaction.category == 'Consulting Services' and transaction.amount > 50000:
                risk_score += 0.2
                reasons.append("[Corporate] High consulting spend for Manufacturing entity.")
        elif sector == 'Retail':
            if transaction.category == 'Services' and transaction.amount > 20000:
                risk_score += 0.15
                reasons.append("[Corporate] Unspecified service expense in Retail sector.")

        if structure == 'SME':
            if context.get('avg_transaction_val', 0) > 0 and transaction.amount > context['avg_transaction_val'] * 2:
                risk_score += 0.25
                reasons.append(f"[Corporate] SME Context: Large transaction relative to history.")

        # 2.2 Corporate Brain (RAG)
        print(f"[DEBUG] Chamando Corporate Brain (RAG) com categoria: {transaction.category}")
        relevant_docs = self.query_corporate_brain(f"{transaction.category or 'General'} policy limit approval")
        if relevant_docs:
            doc_titles = ", ".join([d['doc'] for d in relevant_docs])
            reasons.append(f"[Corporate] Checked against internal policies: {doc_titles}")

        # 2.3 Reference Lists (Departments, Risk Lists, Vendor Watchlists)
        from .models import ReferenceItem
        if transaction.category:
            ref_match = ReferenceItem.objects.filter(value__iexact=transaction.category).order_by('-risk_factor').first()
            if ref_match and ref_match.risk_factor > 1.0:
                risk_score += (ref_match.risk_factor - 1.0) * 0.5
                reasons.append(f"[Corporate] Category '{transaction.category}' flagged in '{ref_match.reference_list.name}'")

        if transaction.vendor:
            vendor_match = ReferenceItem.objects.filter(value__iexact=transaction.vendor).order_by('-risk_factor').first()
            if vendor_match:
                if vendor_match.risk_factor > 1.0:
                    risk_score += (vendor_match.risk_factor - 1.0) * 0.8 # Higher weight for vendor match
                    reasons.append(f"[Corporate] Vendor '{transaction.vendor}' flagged in '{vendor_match.reference_list.name}'")
                elif vendor_match.risk_factor < 1.0:
                    risk_score -= (1.0 - vendor_match.risk_factor) * 0.5
                    reasons.append(f"[Corporate] Vendor '{transaction.vendor}' is on a Trusted List ('{vendor_match.reference_list.name}')")

        if context.get('department'):
            dept_ref = ReferenceItem.objects.filter(value__iexact=context['department']).order_by('-risk_factor').first()
            if dept_ref and dept_ref.risk_factor > 1.0:
                risk_score += (dept_ref.risk_factor - 1.0) * 0.5
                reasons.append(f"[Corporate] User department '{context['department']}' is flagged as high risk")

        # --- LAYER 3: INSTITUTIONAL MEMORY (Mem0 - Long Term Learning) ---
        if active_learning and self.mem_service:
            try:
                # 3.1 General Feedback
                mem_query = f"Risk feedback for vendor {transaction.vendor} category {transaction.category}"
                mem_results = self.mem_service.search(mem_query, user_id=self.user_id, limit=3)
                
                for res in mem_results:
                    mem_text = res.get('memory', '').lower()
                    if 'false positive' in mem_text or 'safe' in mem_text:
                        risk_score -= 0.15
                        reasons.append(f"[Institutional Memory] Similar patterns previously marked as False Positive.")
                    elif 'fraud' in mem_text or 'risk' in mem_text or 'alert' in mem_text:
                        risk_score += 0.15
                        reasons.append(f"[Institutional Memory] Similar patterns previously flagged as Risk.")

                # 3.2 Agent-Specific Reputation in Memory
                if triggered_agents:
                    for a_info in triggered_agents:
                        agent_query = f"Feedback for agent {a_info['name']}"
                        agent_mems = self.mem_service.search(agent_query, user_id=self.user_id, limit=2)
                        for am in agent_mems:
                            am_text = am.get('memory', '').lower()
                            if 'incorrectly flagged' in am_text:
                                risk_score -= 0.1
                                reasons.append(f"[Institutional Memory] Agent '{a_info['name']}' has history of false flags for similar patterns.")
                            elif 'correctly identified' in am_text:
                                risk_score += 0.1
                                reasons.append(f"[Institutional Memory] Agent '{a_info['name']}' has high confidence history for this pattern.")
            except:
                pass

        # --- LAYER 4: GLOBAL (Universal Rules) ---
        # 4.1 High Value (Universal)
        if transaction.amount > 100000:
            risk_score += 0.1
            reasons.append("[Global] High value transaction (> $100k).")
        
        # 4.2 Anomaly relative to Average
        avg_val = context.get('avg_transaction_val', 0)
        if avg_val > 0:
            threshold = 3
            if structure == 'SME': threshold = 2
            if transaction.amount > avg_val * threshold:
                risk_score += 0.3
                reasons.append(f"[Global] Amount is {threshold}x higher than your average approval.")

        # --- AI CONTROL PLANE SENSITIVITY ---
        if sensitivity != 0.5:
            adjustment = (sensitivity - 0.5) * 0.4 
            if risk_score > 0.1 or sensitivity > 0.8:
                old_score = risk_score
                risk_score += adjustment
                risk_score = max(0.0, risk_score)
                if abs(risk_score - old_score) > 0.01:
                    reasons.append(f"[AI Control] Score adjusted by sensitivity ({sensitivity:.1f}): {adjustment:+.2f}")

        # Generate XAI Log
        print("[DEBUG] Gerando XAI Log...")
        xai_log = self.generate_xai_log(transaction, risk_score, reasons, context)

        result = {
            "risk_score": min(max(risk_score, 0.0), 1.0),
            "reasons": reasons,
            "triggered_agents": triggered_agents,
            "ai_context": {
                "user_trust_score": min(context.get('learning_progress', 0) / 100.0 + 0.5, 0.99),
                "persona": context.get('persona', 'Anonymous'),
            },
            "xai_explanation": xai_log
        }

        latency = int((time.time() - start_time) * 1000)
        self._log_governance_event(
            event_type='RISK_SCORING',
            model_name='Multi-Layer Risk Engine',
            input_data={'transaction_id': transaction.transaction_id, 'amount': float(transaction.amount)},
            output_data={'risk_score': result['risk_score'], 'reasons': reasons},
            latency_ms=latency,
            status='SUCCESS',
            confidence_score=result['risk_score']
        )

        return result

    def generate_executive_summary(self):
        """
        Generates a proactive, high-level executive summary of the organization's risk posture.
        This simulates a 'Chief Audit Executive' AI analysis.
        """
        from .models import Alert, Transaction, AuditCase, ContextProfile
        from django.db.models import Count, Avg, Sum, Max
        from django.utils import timezone
        from datetime import timedelta

        now = timezone.now()
        start_of_week = now - timedelta(days=7)
        
        # 0. Load current audit context (country and domains in scope)
        profile = ContextProfile.objects.order_by('-updated_at').first()
        ctx_country = profile.country if profile and profile.country else None
        ctx_domains = profile.audit_domains if profile and profile.audit_domains else []

        # 1. High-Level Metrics
        total_alerts_week = Alert.objects.filter(timestamp__gte=start_of_week).count()
        high_risk_alerts = Alert.objects.filter(timestamp__gte=start_of_week, severity='High').count()
        
        # 2. Department Analysis (Where is the heat?)
        dept_risks = self.get_department_risk_stats()
        top_risk_dept = dept_risks[0] if dept_risks else None
        
        # 3. Trend Analysis
        alerts_last_week = Alert.objects.filter(timestamp__gte=start_of_week - timedelta(days=7), timestamp__lt=start_of_week).count()
        trend_msg = "stable"
        if total_alerts_week > (alerts_last_week * 1.2) and alerts_last_week > 0:
            trend_msg = "increasing significantly"
        elif total_alerts_week < (alerts_last_week * 0.8) and alerts_last_week > 0:
            trend_msg = "improving"

        # 3b. Out-of-scope analysis (category and country vs configured context)
        out_of_scope_alerts = 0
        out_of_scope_categories = set()
        out_of_scope_countries = set()

        recent_alerts = Alert.objects.filter(timestamp__gte=start_of_week).select_related('transaction')
        for alert in recent_alerts:
            txn = getattr(alert, 'transaction', None)
            tx_category = getattr(txn, 'category', None) if txn else None
            tx_country = None
            try:
                tx_country = getattr(txn, 'country', None) if txn else None
            except:
                tx_country = None

            category_out = bool(ctx_domains and tx_category and tx_category not in ctx_domains)
            country_out = bool(ctx_country and tx_country and tx_country != ctx_country)

            if category_out or country_out:
                out_of_scope_alerts += 1
                if category_out and tx_category:
                    out_of_scope_categories.add(tx_category)
                if country_out and tx_country:
                    out_of_scope_countries.add(tx_country)
            
        # 4. Generate Narrative (The "Power" part)
        summary_title = "Executive Risk Briefing"
        insights = []
        
        # Insight 1: Overall Posture
        if trend_msg == "increasing significantly":
            insights.append(f"⚠️ **Critical Trend:** Risk alerts have surged by over 20% this week compared to last. Immediate attention required.")
        elif trend_msg == "improving":
            insights.append(f"✅ **Positive Trend:** Alert volume is down this week, indicating effective remediation or lower transaction volume.")
        else:
            insights.append(f"ℹ️ **Stable Posture:** Risk levels are consistent with the previous week baseline.")

        # Insight 2: Department Hotspot
        if top_risk_dept and top_risk_dept['risk_score'] > 50:
            insights.append(f"🎯 **Focus Area:** The **{top_risk_dept['department']}** department is the current primary outlier with a Risk Score of {top_risk_dept['risk_score']}/100 and {top_risk_dept['alert_count']} active alerts.")
            
        # Insight 3: Specific "Deep Dive" Finding (Simulated Logic)
        # Find a pattern: Same vendor, multiple high alerts?
        risky_vendors = Alert.objects.filter(severity='High', timestamp__gte=start_of_week).values('vendor').annotate(c=Count('id')).filter(c__gt=1)
        if risky_vendors:
            v = risky_vendors[0]
            insights.append(f"🔍 **Pattern Detection:** Vendor **{v['vendor']}** has triggered multiple high-severity alerts this week. This suggests a potential systemic issue or policy gap rather than isolated incidents.")
        
        # Insight 4: Actionable Recommendation
        if high_risk_alerts > 5:
            insights.append(f"⚡ **Recommended Action:** Initiate a targeted review for the {high_risk_alerts} high-risk exceptions. Consider freezing payments for flagged vendors in {top_risk_dept['department'] if top_risk_dept else 'affected departments'}.")
        else:
            insights.append(f"⚡ **Recommended Action:** Routine monitoring is sufficient. No immediate critical interventions required.")

        # Insight 5: Out-of-scope signals vs configured audit context
        if out_of_scope_alerts > 0 and total_alerts_week > 0:
            cats = ", ".join(sorted(out_of_scope_categories)) if out_of_scope_categories else "categorias diversas"
            countries = ", ".join(sorted(out_of_scope_countries)) if out_of_scope_countries else None
            if countries:
                insights.append(
                    f"🌐 **Escopo vs Realidade:** {out_of_scope_alerts} alertas desta semana pertencem a {cats} "
                    f"e países ({countries}) fora do contexto configurado. Avalie se o escopo formal da auditoria precisa ser ajustado "
                    f"ou se esses sinais devem ser tratados como monitoramento complementar."
                )
            else:
                insights.append(
                    f"🌐 **Escopo vs Realidade:** {out_of_scope_alerts} alertas desta semana pertencem a {cats} "
                    f"fora dos domínios de auditoria atualmente configurados. Considere revisar o escopo ou documentar essas exceções."
                )

        # --- ORCHESTRATE AGENTS (THE "MOTHER INTELLIGENCE") ---
        # Get active specialized agents
        from .models import RiskAgent
        agents = RiskAgent.objects.filter(active=True).exclude(specialization='General')
        agent_reports = []
        
        # --- MOTHER INTELLIGENCE SELF-TRAINING ---
        # Mother learns from the collective reputation of her agents
        # If high-reputation agents are finding risks, Mother increases alertness.
        mother_alertness = 1.0
        if self.mem_service:
            # Mother reflects on past executive summaries
            try:
                mem_context = self.mem_service.search("Executive Summary Feedback", user_id=self.user_id, limit=1)
                if mem_context:
                    # E.g., "Last summary was too alarmist" -> reduce alertness
                    last_memory = mem_context[0].get('memory', '').lower()
                    if "alarmist" in last_memory or "false positive" in last_memory:
                        mother_alertness = 0.8
                    elif "missed" in last_memory or "underreported" in last_memory:
                        mother_alertness = 1.2
            except:
                pass # Fail silently if mem0 issues

        if agents.exists():
            for agent in agents:
                # Simulate agent findings based on their specialization and TRAINING INSTRUCTIONS
                finding = self._simulate_agent_finding(agent, start_of_week)
                if finding:
                    # Weight finding by agent reputation and Mother's alertness
                    if finding['priority'] == 'High':
                        agent.reputation_score = min(agent.reputation_score + 0.05, 2.0) # Reward active agents
                        agent.save()
                    
                    agent_reports.append(finding)
                    
                    # Integrate into main insights if high priority
                    if finding['priority'] == 'High' or (finding['priority'] == 'Medium' and mother_alertness > 1.0):
                        insights.append(f"🤖 **Agent {agent.name} ({agent.specialization}):** {finding['message']}")

        return {
            "title": summary_title,
            "insights": insights,
            "generated_at": now.strftime("%Y-%m-%d %H:%M"),
            "risk_level": "Critical" if high_risk_alerts > 10 else "Moderate" if high_risk_alerts > 0 else "Low",
            "agent_reports": agent_reports,
            "out_of_scope_alerts": out_of_scope_alerts,
            "total_alerts_week": total_alerts_week,
            "context_country": ctx_country,
            "context_domains": ctx_domains
        }

    def _conditions_to_filter(self, conditions):
        from django.db.models import Q
        q_obj = Q()
        for cond in conditions:
            metric = cond.get('metric')
            operator = cond.get('operator')
            value = cond.get('value')
            
            if not metric or not operator: continue

            # Handle amount conversion
            if metric == 'amount':
                try: 
                    value = float(value)
                except: 
                    pass # Keep as is if conversion fails
            
            # Map operators to Django lookups
            if operator == '>':
                q_obj &= Q(**{f"{metric}__gt": value})
            elif operator == '<':
                q_obj &= Q(**{f"{metric}__lt": value})
            elif operator in ['=', '==']:
                q_obj &= Q(**{f"{metric}": value})
            elif operator == 'contains':
                q_obj &= Q(**{f"{metric}__icontains": value})
            elif operator == '!=':
                q_obj &= ~Q(**{f"{metric}": value})
                
        return q_obj

    def _execute_agent_external_action(self, agent, alert=None, case=None, transaction=None):
        """
        Executes an external action for an agent if an external action template is configured.
        Returns the execution record or None.
        """
        if not agent.external_action_template:
            return None
            
        if not agent.external_action_template.active:
            return None
            
        try:
            from .external_action_service import ExternalActionExecutor
            execution = ExternalActionExecutor.execute_template(
                agent.external_action_template,
                alert=alert,
                case=case,
                transaction=transaction,
                agent=agent
            )
            logger.info(f"Successfully executed external action {agent.external_action_template.name} for agent {agent.name}")
            return execution
        except Exception as e:
            logger.error(f"Failed to execute external action for agent {agent.name}: {str(e)}")
            return None

    def _simulate_agent_finding(self, agent, start_date):
        """
        Simulates the specialized analysis of a sub-agent.
        Uses 'training_instructions' to guide the simulation.
        NOW UPGRADED: Uses actual agent conditions for retrospective analysis.
        """
        from .models import Alert, Transaction, RiskAgentLog
        from django.db.models import Sum, Count, Q
        
        spec = agent.specialization.lower()
        instructions = (agent.training_instructions or "").lower()
        
        finding_result = None

        # 1. Dynamic Retrospective Analysis (The "Real" Logic)
        if agent.conditions:
            try:
                q_filter = self._conditions_to_filter(agent.conditions)
                # Apply filter to transactions in the period
                matches = Transaction.objects.filter(timestamp__gte=start_date).filter(q_filter)
                match_count = matches.count()
                
                if match_count > 0:
                    total_amt = matches.aggregate(Sum('amount'))['amount__sum'] or 0
                    priority = "High" if match_count > 5 or total_amt > 50000 else "Medium"
                    
                    finding_result = {
                        "agent": agent.name, 
                        "specialization": agent.specialization, 
                        "message": f"Retrospective Analysis: Found {match_count} transactions matching '{agent.name}' criteria (Total: {total_amt:.2f}).", 
                        "priority": priority
                    }
            except Exception as e:
                print(f"Error in dynamic agent simulation: {e}")
        
        # 2. Legacy/Fallback Logic based on Specialization (if no conditions or specific override needed)
        if not finding_result:
            if 'fraud' in spec:
                # Fraud Agent Logic (Split Payment Detection)
                threshold = 5
                if "strict" in instructions: threshold = 3
                
                suspicious = Transaction.objects.filter(timestamp__gte=start_date).values('vendor').annotate(c=Count('id')).filter(c__gt=threshold).count()
                if suspicious > 0:
                    finding_result = {
                        "agent": agent.name, 
                        "specialization": agent.specialization, 
                        "message": f"Detected {suspicious} vendors with potential split payment structuring (Threshold: {threshold}).", 
                        "priority": "High"
                    }

            elif 'compliance' in spec:
                 # Compliance Agent Logic
                 violations = Alert.objects.filter(timestamp__gte=start_date, alert_type='Policy Violation').count()
                 if violations > 2:
                     finding_result = {
                         "agent": agent.name, 
                         "specialization": agent.specialization, 
                         "message": f"Found {violations} distinct policy violations this week.", 
                         "priority": "Medium"
                     }

            elif 'it' in spec or 'tech' in spec:
                 # IT Agent
                 if "logs" in instructions:
                      finding_result = {
                          "agent": agent.name, 
                          "specialization": agent.specialization, 
                          "message": "Log analysis requested: No anomalies found in server access logs.", 
                          "priority": "Low"
                      }
                 else:
                     finding_result = {
                         "agent": agent.name, 
                         "specialization": agent.specialization, 
                         "message": "System logs are normal. No unauthorized access attempts correlated with transactions.", 
                         "priority": "Low"
                     }
             
            # Fallback for generic agents
            elif instructions:
                finding_result = {
                    "agent": agent.name, 
                "specialization": agent.specialization, 
                "message": f"Executing custom instruction: '{instructions[:50]}...' - No anomalies found.", 
                "priority": "Low"
            }

        # Log the finding (even if None or Low, effectively tracking execution)
        if finding_result:
             risk_score = 0.9 if finding_result.get('priority') == 'High' else 0.5
             suggested_action = "Investigate Vendor" if 'vendor' in finding_result['message'] else "Review Logs"
             
             RiskAgentLog.objects.create(
                 agent=agent,
                 scanned_count=100, # Simulated count
                 finding_summary=finding_result['message'],
                 finding_details=finding_result,
                 risk_score=risk_score,
                 suggested_action=suggested_action
             )
             
             # If High Priority, create a System Alert
             if finding_result.get('priority') == 'High':
                 Alert.objects.create(
                     alert_type=f"Agent Finding: {agent.name}",
                     severity='High',
                     status='New',
                     description=finding_result['message'],
                     materiality=0.9,
                     vendor=agent.specialization # Use specialization as vendor/category proxy for some UI views
                 )

        
        return finding_result
    def calculate_risk_score(self, transaction, context=None, active_learning=True):
        if context is None: context = {}
        from .models import ReferenceItem
        
        risk_score = 0.2 # Baseline
        reasons = []
        triggered_agents = []
        sensitivity = context.get('sensitivity', 0.5)
        structure = context.get('structure', 'Corporate')

        # --- LAYER 2: CORPORATE (Reference Lists) ---
        vendor_match = ReferenceItem.objects.filter(value__iexact=transaction.vendor).order_by('-risk_factor').first()
        if vendor_match:
            if vendor_match.risk_factor > 1.0:
                risk_score += (vendor_match.risk_factor - 1.0) * 0.5
                reasons.append(f"[Corporate] Vendor '{transaction.vendor}' is on a High Risk List ('{vendor_match.reference_list.name}')")
            elif vendor_match.risk_factor < 1.0:
                risk_score -= (1.0 - vendor_match.risk_factor) * 0.5
                reasons.append(f"[Corporate] Vendor '{transaction.vendor}' is on a Trusted List ('{vendor_match.reference_list.name}')")
        
        if context.get('department'):
            dept_ref = ReferenceItem.objects.filter(value__iexact=context['department']).order_by('-risk_factor').first()
            if dept_ref and dept_ref.risk_factor > 1.0:
                risk_score += (dept_ref.risk_factor - 1.0) * 0.5
                reasons.append(f"[Corporate] User department '{context['department']}' is flagged as high risk")

        # --- LAYER 3: INSTITUTIONAL MEMORY (Mem0 - Long Term Learning) ---
        if active_learning and self.mem_service:
            try:
                mem_query = f"Risk feedback for vendor {transaction.vendor} category {transaction.category}"
                mem_results = self.mem_service.search(mem_query, user_id=self.user_id, limit=3)
                
                for res in mem_results:
                    # Mem0 results are dicts with 'memory', 'score', etc.
                    mem_text = res.get('memory', '').lower()
                    
                    # Check for strong signals in memory
                    if 'false positive' in mem_text or 'safe' in mem_text:
                        risk_score -= 0.15
                        reasons.append(f"[Institutional Memory] Similar patterns previously marked as False Positive.")
                    elif 'fraud' in mem_text or 'risk' in mem_text or 'alert' in mem_text:
                        risk_score += 0.15
                        reasons.append(f"[Institutional Memory] Similar patterns previously flagged as Risk.")
            except:
                pass

        # --- LAYER 4: GLOBAL (Universal Rules) ---
        # 4.1 High Value (Universal)
        if transaction.amount > 100000:
            risk_score += 0.1
            reasons.append("[Global] High value transaction (> $100k).")
        
        # 3.2 Anomaly relative to Average (Universal logic, though uses personal avg)
        avg_val = context.get('avg_transaction_val', 0)
        if avg_val > 0:
            threshold = 3
            if structure == 'SME': threshold = 2
            if transaction.amount > avg_val * threshold:
                risk_score += 0.3
                reasons.append(f"[Global] Amount is {threshold}x higher than your average approval.")

        # --- AI CONTROL PLANE SENSITIVITY ---
        if sensitivity != 0.5:
            # 0.5 is neutral. 1.0 is +0.2 risk. 0.0 is -0.2 risk.
            adjustment = (sensitivity - 0.5) * 0.4 
            
            # Only apply if there's some base risk (don't make safe things risky just because of sensitivity)
            # Or if it's very sensitive (high paranoia), maybe we do want to bump even small risks.
            if risk_score > 0.1 or sensitivity > 0.8:
                old_score = risk_score
                risk_score += adjustment
                # Clamp temporarily to check change
                risk_score = max(0.0, risk_score)
                
                if abs(risk_score - old_score) > 0.01:
                    reasons.append(f"[AI Control] Score adjusted by sensitivity ({sensitivity:.1f}): {adjustment:+.2f}")

        # Generate XAI Log
        xai_log = self.generate_xai_log(transaction, risk_score, reasons, context)

        return {
            "risk_score": min(max(risk_score, 0.0), 1.0),
            "reasons": reasons,
            "triggered_agents": triggered_agents,
            "ai_context": {
                "user_trust_score": min(context.get('learning_progress', 0) / 100.0 + 0.5, 0.99),
                "persona": context.get('persona', 'Anonymous'),
            },
            "xai_explanation": xai_log
        }

    def execute_suggestion_action(self, action_id, action_type, params=None):
        """
        Executes an action proposed by the AI (e.g. create rule, adjust settings).
        """
        response = {"success": False, "message": "Unknown action"}
        
        if action_type == "create_risk_agent":
            try:
                from .models import RiskAgent
                agent = RiskAgent.objects.create(
                    name=params.get('name', 'AI Generated Agent'),
                    conditions=params.get('conditions', []),
                    action=params.get('action', 'notify_manager'),
                    specialization=params.get('specialization', 'General'),
                    persona=params.get('persona', ''),
                    active=True
                )
                response = {"success": True, "message": f"Agente de Risco '{agent.name}' criado com sucesso! (ID: {agent.id})"}
            except Exception as e:
                response = {"success": False, "message": f"Erro ao criar agente: {str(e)}"}

        elif action_type == "create_rule":
            # Example: Create a rule to ignore specific vendor alerts
            # params might contain vendor_name or logic
            # For simplicity, we assume action_id encodes the intent or we pass data
            try:
                # Naive implementation: Create a "whitelist" rule
                # In real world, we'd parse params. Here we just create a dummy rule for demo.
                rule = RegulatoryRule.objects.create(
                    country="Global",
                    regulation="AI Generated Exception",
                    alert_type="Whitelist Vendor",
                    description=f"Auto-generated exception based on user feedback action {action_id}",
                    suggested_by_ai=True,
                    ai_confidence=0.9,
                    active=True
                )
                response = {"success": True, "message": f"Regra de exceção criada com sucesso! (ID: {rule.id})"}
            except Exception as e:
                response = {"success": False, "message": str(e)}
                
        elif action_type == "adjust_sensitivity":
            # Adjust user profile settings (mock)
            # We could store a 'sensitivity' float in ContextProfile if we had it
            response = {"success": True, "message": "Sensibilidade do modelo ajustada para 80%."}
            
        return response

    def generate_user_insights(self):
        context = self.build_user_context()
        insights = []
        recommendations = []
        
        if context['persona'] == "Skeptical Analyst":
            insights.append("You tend to flag 2x more false positives than average. We've adjusted sensitivity down for you.")
            recommendations.append("Review 'Low Confidence' alerts in batch to save time.")
        elif context['persona'] == "High-Value Approver":
            insights.append("You deal with large sums. We're prioritizing 'Split Transaction' risks for you.")
            recommendations.append("Check the 'Forecast' tab to see cash flow impacts.")
        else:
            insights.append("Your feedback helps the model learn. Keep rating alerts!")
            recommendations.append("Try the 'Simulate' feature to test new risk rules.")
            
        return {
            "title": "Seu Perfil de Auditor",
            "persona": context['persona'],
            "learning_level": context['learning_progress'],
            "agreement_rate": int((context['stats']['confirmations'] / context['stats']['total'] * 100)) if context['stats']['total'] > 0 else 0,
            "insights": insights,
            "recommendations": recommendations
        }

    def get_department_risk_stats(self):
        """
        Aggregates risk data by department for the 'Risk Radar'.
        """
        stats = []
        
        # Group Profiles by Department
        departments = ContextProfile.objects.values('department').annotate(
            user_count=Count('id')
        ).exclude(department__isnull=True)
        
        for dept in departments:
            dept_name = dept['department']
            if not dept_name: continue
            
            # Find users in this department
            user_ids = ContextProfile.objects.filter(department=dept_name).values_list('user_id', flat=True)
            
            # Find transactions/alerts for these users
            tx_count = Transaction.objects.filter(user_id__in=user_ids).count()
            
            # Find Alerts linked to these transactions
            alerts = Alert.objects.filter(transaction__user_id__in=user_ids)
            alert_count = alerts.count()
            avg_risk = alerts.aggregate(Avg('materiality'))['materiality__avg'] or 0
            
            # Calculate Risk Score (0-100)
            risk_score = 0
            if tx_count > 0:
                alert_rate = alert_count / tx_count
                risk_score = (alert_rate * 50) + (avg_risk * 50)
            
            stats.append({
                'department': dept_name,
                'risk_score': min(int(risk_score), 100), 
                'alert_count': alert_count,
                'user_count': dept['user_count']
            })
            
        return sorted(stats, key=lambda x: x['risk_score'], reverse=True)

    def get_category_risk_stats(self):
        """
        Aggregates risk data by transaction category for the 'Risk Radar'.
        """
        stats = []
        
        # Get all distinct categories
        categories = Transaction.objects.values('category').annotate(
            tx_count=Count('id')
        ).exclude(category__isnull=True)
        
        for cat in categories:
            cat_name = cat['category']
            if not cat_name: continue
            
            tx_count = cat['tx_count']
            
            # Find Alerts linked to these transactions
            alerts = Alert.objects.filter(transaction__category=cat_name)
            alert_count = alerts.count()
            avg_risk = alerts.aggregate(Avg('materiality'))['materiality__avg'] or 0
            
            # Calculate Risk Score (0-100)
            risk_score = 0
            if tx_count > 0:
                alert_rate = alert_count / tx_count
                risk_score = (alert_rate * 50) + (avg_risk * 50)
            
            stats.append({
                'category': cat_name,
                'risk_score': min(int(risk_score), 100), 
                'alert_count': alert_count,
                'tx_count': tx_count
            })
        
        return sorted(stats, key=lambda x: x['risk_score'], reverse=True)

    def generate_case_report(self, case_or_id):
        """
        Generates a comprehensive report for an audit case.
        """
        try:
            if isinstance(case_or_id, (int, str)):
                case = AuditCase.objects.get(id=case_or_id)
            else:
                case = case_or_id
        except AuditCase.DoesNotExist:
            return {"error": "Case not found"}

        # Gather Data
        comments = case.comments.all().order_by('created_at')
        attachments = case.attachments.all()
        
        transaction_data = {}
        ai_analysis = {}
        
        if case.transaction_id:
            try:
                txn = Transaction.objects.get(transaction_id=case.transaction_id)
                transaction_data = {
                    "id": txn.id,
                    "date": txn.timestamp.strftime('%Y-%m-%d %H:%M'),
                    "amount": float(txn.amount),
                    "vendor": txn.vendor,
                    "description": getattr(txn, 'description', txn.category),
                    "user": txn.user_id
                }
                # Re-run analysis for the report context
                ai_analysis = self.analyze_transaction_risk(txn)
            except Transaction.DoesNotExist:
                pass

        # Generate Executive Summary (Mock LLM behavior)
        risk_score = ai_analysis.get('risk_score', 0)
        risk_level = "Baixo"
        if risk_score > 0.7: risk_level = "Crítico"
        elif risk_score > 0.4: risk_level = "Alto"
        elif risk_score > 0.2: risk_level = "Moderado"

        summary_text = f"O Caso #{case.id} ('{case.title}') foi aberto em {case.created_at.strftime('%d/%m/%Y')} e apresenta um nível de risco **{risk_level}** ({int(risk_score*100)}%). "
        summary_text += f"O status atual é {case.status} com prioridade {case.priority}. "
        
        reasons = ai_analysis.get('reasons', [])
        if reasons:
            summary_text += f"A IA identificou {len(reasons)} fatores de risco principais, incluindo: '{', '.join(reasons[:2])}'. "

        if comments.exists():
            summary_text += f"Houve {comments.count()} interações registradas na investigação. "
            last_comment = comments.last()
            summary_text += f"A última atualização foi: '{last_comment.comment[:100]}...'. "
        
        if attachments.exists():
            summary_text += f"Foram anexados {attachments.count()} documentos comprobatórios."

        # Include automated Agent findings if any exist for this transaction
        from .models import RiskAgentLog, Alert
        # Try to find alerts linked to this transaction
        related_alerts = Alert.objects.filter(transaction__transaction_id=case.transaction_id)
        if related_alerts.exists():
             summary_text += "\n\n**Detecções Automáticas (Agentes):**"
             for alert in related_alerts:
                 summary_text += f"\n- {alert.alert_type}: {alert.description} (Severidade: {alert.severity})"

        # Final Report Structure
        report = {
            "metadata": {
                "generated_at": timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
                "generated_by": self.user_id or "System",
                "case_id": case.id
            },
            "header": {
                "title": case.title,
                "status": case.status,
                "priority": case.priority,
                "created_at": case.created_at.strftime('%Y-%m-%d')
            },
            "transaction_details": transaction_data,
            "risk_analysis": {
                "score": ai_analysis.get('risk_score', 0),
                "factors": ai_analysis.get('reasons', []),
                "ai_notes": ai_analysis.get('ai_context', {}),
                "xai_explanation": ai_analysis.get('xai_explanation', {})
            },
            "investigation_log": [
                {
                    "user": c.user_id,
                    "date": c.created_at.strftime('%Y-%m-%d %H:%M'),
                    "content": c.comment
                } for c in comments
            ],
            "evidence": [
                {
                    "name": a.file_name,
                    "url": a.file_url,
                    "uploaded_by": a.uploaded_by
                } for a in attachments
            ],
            "executive_summary": summary_text
        }
        
        return report

    def process_natural_language_query(self, query):
        """
        Simple intent recognition for Audit Chat Assistant.
        """
        query = query.lower()
        response = {"type": "text", "content": "I didn't understand that query."}
        
        # Intent: Explain Risk / Why (Contextual Explanation)
        if "porque" in query or "explica" in query or "why" in query or "motivo" in query:
            # Try to find a specific transaction/alert ID
            match = re.search(r'\b\d+\b', query)
            target_alert = None
            
            if match:
                tx_id = match.group()
                target_alert = Alert.objects.filter(id=tx_id).first()
                if not target_alert:
                    # Maybe it's a transaction ID?
                    tx = Transaction.objects.filter(id=tx_id).first()
                    if tx:
                        target_alert = Alert.objects.filter(vendor=tx.vendor, amount=tx.amount, timestamp=tx.timestamp).first()
            else:
                # Default to the most recent high risk alert
                target_alert = Alert.objects.filter(materiality__gt=0.7).order_by('-timestamp').first()
                
            if target_alert:
                # Construct explanation
                explanation = f"O Alerta #{target_alert.id} para {target_alert.vendor} é considerado de Alto Risco ({int(target_alert.materiality*100)}%).\n"
                explanation += "Principais Fatores Contribuintes:\n"
                
                if "Factors:" in target_alert.description:
                    factors = target_alert.description.split("Factors:")[1].split(",")
                    for f in factors:
                        explanation += f"- {f.strip()}\n"
                else:
                    explanation += f"- {target_alert.description}\n"
                    
                # Add Contextual Reference Data check if applicable
                if target_alert.vendor:
                    ref_vendor = ReferenceItem.objects.filter(value__iexact=target_alert.vendor).first()
                    if ref_vendor and ref_vendor.risk_factor > 1.0:
                        explanation += f"- [Contexto] O fornecedor '{target_alert.vendor}' está na lista de monitoramento (Risco x{ref_vendor.risk_factor}).\n"
                
                response = {
                    "type": "message",
                    "content": explanation
                }
            else:
                response = {
                    "type": "message",
                    "content": "Não encontrei nenhum alerta de alto risco recente para explicar. Tente especificar o ID, ex: 'Explique o alerta 12'."
                }
            
        # Intent: Corporate Brain / Policy / RAG
        elif any(word in query for word in ["politica", "policy", "procedimento", "procedure", "norma", "regra", "como funciona", "guideline"]):
            docs = self.query_corporate_brain(query)
            if docs:
                content = "🧠 **Cérebro Corporativo (Políticas & Normas):**\n\n"
                for d in docs:
                    content += f"📄 **{d['doc']}** (Relevância: {int(d['score']*100)}%)\n"
                    content += f"> {d['summary']}\n\n"
                
                response = {
                    "type": "message",
                    "content": content
                }
            else:
                response = {
                    "type": "text",
                    "content": "Não encontrei documentos internos relevantes para sua pergunta no Cérebro Corporativo."
                }

        # Intent: Agents / Agent Status
        elif "agente" in query or "agent" in query:
            from .models import RiskAgentLog, RiskAgent
            
            # Sub-intent: List agents
            if "lista" in query or "quais" in query or "status" in query:
                agents = RiskAgent.objects.filter(active=True)
                content = "🤖 **Agentes Ativos:**\n\n"
                for a in agents:
                    content += f"- **{a.name}** ({a.specialization}): Reputação {a.reputation_score:.1f}\n"
                response = {"type": "message", "content": content}
                
            # Sub-intent: Findings
            else:
                logs = RiskAgentLog.objects.order_by('-timestamp')[:5]
                if logs.exists():
                    content = "🕵️‍♂️ **Últimas atividades dos Agentes:**\n\n"
                    for log in logs:
                        content += f"- **[{log.agent.name}]** {log.finding_summary} \n"
                    response = {"type": "message", "content": content}
                else:
                    response = {"type": "message", "content": "Nenhuma atividade recente registrada pelos agentes."}

        # Intent: Executive Summary (Mother Intelligence)
        elif "executivo" in query or ("relatorio" in query and "geral" in query) or "mae" in query or "mother" in query:
             summary = self.generate_executive_summary()
             # Format for chat
             content = f"📊 **{summary['title']}**\n\n"
             content += f"**Nível de Risco Global:** {summary['risk_level']}\n\n"
             content += f"**Agentes Ativos:** {summary['active_agents']}\n\n"
             content += "**Insights Principais:**\n"
             for insight in summary['insights']:
                 content += f"{insight}\n"
             
             if summary.get('agent_findings'):
                 content += "\n**Descobertas dos Agentes:**\n"
                 for finding in summary['agent_findings']:
                     content += f"- {finding}\n"
                     
             response = {"type": "message", "content": content}

        # Intent: Summary/Overview
        elif "resumo" in query or "overview" in query or "hoje" in query:
            count = Transaction.objects.filter(timestamp__gte=timezone.now().date()).count()
            alerts = Alert.objects.filter(timestamp__gte=timezone.now().date()).count()
            response = {
                "type": "summary",
                "content": f"Hoje processamos {count} transações. Detectamos {alerts} novos alertas de risco.",
                "data": {"transactions": count, "alerts": alerts}
            }
            
        # Intent: High Risk
        elif "risco" in query or "risk" in query or "alto" in query:
            high_risk = Alert.objects.filter(materiality__gt=0.7).order_by('-timestamp')[:5]
            items = []
            for a in high_risk:
                # Try to parse reasons from description if available
                reason_text = a.alert_type
                if "Factors:" in a.description:
                    parts = a.description.split("Factors:")
                    if len(parts) > 1:
                        reason_text = parts[1].strip()
                
                items.append({
                    "id": a.id, 
                    "vendor": a.vendor, 
                    "amount": a.amount, 
                    "reason": reason_text
                })
                
            response = {
                "type": "list",
                "content": "Aqui estão os 5 maiores riscos detectados recentemente:",
                "data": items
            }

        # Intent: Vendor Search
        elif "fornecedor" in query or "vendor" in query:
            # Extract vendor name (naive implementation)
            words = query.split()
            vendor_name = words[-1] # Take last word as vendor
            txs = Transaction.objects.filter(vendor__icontains=vendor_name).count()
            response = {
                "type": "text",
                "content": f"Encontrei {txs} transações recentes para o fornecedor '{vendor_name}'."
            }

        # Intent: Persona/Self
        elif "eu" in query or "meu" in query or "perfil" in query:
            context = self.build_user_context()
            response = {
                "type": "text",
                "content": f"Você está classificado como '{context['persona']}'. Calibração do sistema: {context['learning_progress']}%."
            }

        # Intent: Smart Suggestions / Rules
        elif "sugest" in query or "regra" in query or "melhor" in query or "otimiz" in query:
            context = self.build_user_context()
            suggestions = []
            
            # Logic: If many false positives on a vendor, suggest a whitelist rule
            false_positive_vendors = AiFeedback.objects.filter(
                user_id=self.user_id, feedback_type='inaccurate'
            ).values('comment').annotate(count=Count('id')).filter(count__gte=1)
            
            for fp in false_positive_vendors:
                # Naive extraction of vendor from comment if possible, or just use generic text
                suggestions.append({
                    "id": f"rule_fp_{fp['count']}",
                    "type": "rule_proposal",
                    "title": "Regra de Exceção",
                    "description": f"Criar regra para ignorar alertas similares aos que você rejeitou recentemente ({fp['count']} vezes).",
                    "action": "create_rule"
                })
                
            if not suggestions:
                suggestions.append({
                    "id": "gen_1",
                    "type": "tip",
                    "title": "Ajuste de Sensibilidade",
                    "description": "Seu perfil indica alta cautela. Podemos aumentar a sensibilidade do modelo para 80%?",
                    "action": "adjust_sensitivity"
                })

            response = {
                "type": "suggestions",
                "content": "Com base no seu histórico recente, tenho estas sugestões de otimização:",
                "data": suggestions
            }

        # Intent: Create/Manage Case
        elif "caso" in query or "case" in query:
            if "cria" in query or "create" in query or "abrir" in query or "novo" in query:
                # Try to extract transaction ID
                match = re.search(r'\b\d+\b', query)
                if match:
                    tx_id = match.group()
                    # Check if case exists
                    existing = AuditCase.objects.filter(transaction_id=tx_id).first()
                    if existing:
                         response = {
                            "type": "text",
                            "content": f"Já existe um caso aberto para a transação {tx_id} (Caso #{existing.id}: {existing.title})."
                        }
                    else:
                        # Create case
                        new_case = AuditCase.objects.create(
                            title=f"Investigação via Chat: Transação {tx_id}",
                            description=f"Caso criado automaticamente via assistente a pedido do usuário. Query original: '{query}'",
                            transaction_id=tx_id,
                            status="New",
                            priority="Medium",
                            created_by=self.user_id or "system"
                        )
                        response = {
                            "type": "text",
                            "content": f"Caso #{new_case.id} criado com sucesso para a transação {tx_id}. Você pode visualizar detalhes na aba 'Caso' do inspetor.",
                            "action": {
                                "type": "open_case",
                                "id": new_case.id,
                                "label": "Abrir Caso"
                            }
                        }
                else:
                     response = {
                        "type": "text",
                        "content": "Para criar um caso, por favor especifique o ID numérico da transação. Exemplo: 'Criar caso para transação 123'."
                    }
            elif "lista" in query or "list" in query or "meus" in query:
                cases = AuditCase.objects.all().order_by('-updated_at')[:5]
                items = [{"id": c.id, "title": c.title, "status": c.status} for c in cases]
                response = {
                    "type": "list",
                    "content": "Aqui estão os casos mais recentes:",
                    "data": items
                }

        # Intent: Automation / Rule Suggestion (Action Agent)
        elif "automat" in query or "regra" in query or "rule" in query or "agente" in query:
             # Suggest creating a risk agent
             response = {
                "type": "card",
                "content": "Com base na sua solicitação, posso criar um Agente de Risco para monitorar padrões similares.",
                "data": {
                    "title": "Sugestão de Automação",
                    "description": "Criar agente para bloquear transações acima de $50k em serviços de consultoria.",
                    "actions": [
                        {
                            "id": "create_agent_consulting_limit",
                            "label": "Criar Agente",
                            "type": "create_risk_agent",
                            "params": {
                                "name": "Bloqueio Consultoria > 50k",
                                "conditions": [{"metric": "amount", "operator": ">", "value": "50000"}, {"metric": "category", "operator": "contains", "value": "Consulting"}],
                                "action": "create_case_high"
                            }
                        }
                    ]
                }
             }
            
        return response

# Legacy wrapper for backward compatibility
def analyze_transaction_risk(transaction):
    # Default to generic if no user_id passed
    ai = AuditAI(user_id=transaction.user_id) 
    return ai.analyze_transaction_risk(transaction)
