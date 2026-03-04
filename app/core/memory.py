import os
from typing import List, Optional
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document

class _NoopRetriever:
    """Vector DB 비활성화 시 사용하는 더미 retriever."""
    def invoke(self, query: str):
        return []


class MemoryManager:
    """
    장기 기억(Vector DB) 관리자
    - 개발 편의를 위해 로컬 파일 기반인 Chroma DB 사용 예시
    - 추후 MongoDBAtlasVectorSearch로 교체 가능
    """
    
    def __init__(self, persist_directory: str = "./chroma_db"):
        print("[Memory] Initializing Vector Store...")
        self.persist_directory = persist_directory
        self.disabled = os.getenv("UMI_DISABLE_VECTORDB", "").lower() in ("1", "true", "yes")

        # 임베딩/스토어는 지연 초기화
        self.embeddings = None
        
        # Collection Cache
        self._stores = {}

        # Default Collection 이름만 설정
        self.default_collection = "npc_memories"

        if self.disabled:
            print("[Memory] Vector Store disabled by UMI_DISABLE_VECTORDB")
        else:
            print(f"[Memory] Vector Store ready at {persist_directory}")

    def _ensure_embeddings(self):
        """임베딩 모델 지연 초기화."""
        if self.embeddings is not None:
            return
        self.embeddings = HuggingFaceEmbeddings(
            model_name="jhgan/ko-sroberta-multitask",
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )

    def _get_store(self, collection_name: str) -> Chroma:
        """Get or create a Chroma vector store for a collection"""
        if self.disabled:
            raise RuntimeError("Vector store is disabled.")

        self._ensure_embeddings()
        if collection_name not in self._stores:
            self._stores[collection_name] = Chroma(
                collection_name=collection_name,
                embedding_function=self.embeddings,
                persist_directory=self.persist_directory
            )
        return self._stores[collection_name]

    def add_memory(self, text: str, metadata: dict = None, collection_name: str = None):
        """
        기억(텍스트)을 벡터로 변환하여 저장
        Args:
            text: 저장할 기억 내용
            metadata: 추가 정보
            collection_name: 컬렉션 이름 (기본값: npc_memories)
        """
        if metadata is None:
            metadata = {}

        if self.disabled:
            return
        
        col_name = collection_name or self.default_collection
        store = self._get_store(col_name)
            
        doc = Document(page_content=text, metadata=metadata)
        store.add_documents([doc])
        print(f"[Memory] Saved to {col_name}: {text[:30]}...")

    def add_documents(self, documents: List[Document], collection_name: str = None):
        """
        여러 문서를 한 번에 저장
        """
        if self.disabled:
            return
        col_name = collection_name or self.default_collection
        store = self._get_store(col_name)
        store.add_documents(documents)
        print(f"[Memory] Saved {len(documents)} docs to {col_name}")

    def get_retriever(self, k: int = 3, collection_name: str = None):
        """
        LangChain Retriever 반환
        """
        if self.disabled:
            return _NoopRetriever()
        col_name = collection_name or self.default_collection
        store = self._get_store(col_name)
        
        return store.as_retriever(
            search_type="similarity",
            search_kwargs={"k": k}
        )
        
    def count(self, collection_name: str = None) -> int:
        """문서 개수 확인 (간이)"""
        if self.disabled:
            return 0
        # Chroma 객체에 직접 count 메소드가 없으면 _collection.count() 사용해야 함
        # LangChain wrapper에서는 직접 노출 안 될 수 있음.
        # 여기서는 try-except로 처리하거나 생략.
        # 하지만 초기화 여부 체크를 위해 필요.
        try:
            col_name = collection_name or self.default_collection
            store = self._get_store(col_name)
            # Accessing underlying chroma collection
            return store._collection.count()
        except:
            return 0

# 전역 인스턴스
memory_manager = MemoryManager()
