import os
from typing import List, Optional
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document

class MemoryManager:
    """
    장기 기억(Vector DB) 관리자
    - 개발 편의를 위해 로컬 파일 기반인 Chroma DB 사용 예시
    - 추후 MongoDBAtlasVectorSearch로 교체 가능
    """
    
    def __init__(self, persist_directory: str = "./chroma_db"):
        print("[Memory] Initializing Vector Store...")
        
        # 1. 임베딩 모델 설정
        # 한국어 문장 유사도 성능이 좋은 모델 (jhgan/ko-sroberta-multitask)
        # 로컬 CPU에서도 빠르게 동작합니다.
        self.embeddings = HuggingFaceEmbeddings(
            model_name="jhgan/ko-sroberta-multitask",
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
        
        # 2. Vector Store 초기화 (Chroma)
        self.vector_store = Chroma(
            collection_name="npc_memories",
            embedding_function=self.embeddings,
            persist_directory=persist_directory
        )
        print(f"[Memory] Vector Store ready at {persist_directory}")

    def add_memory(self, text: str, metadata: dict = None):
        """
        기억(텍스트)을 벡터로 변환하여 저장
        Args:
            text: 저장할 기억 내용 (예: 요약된 일기)
            metadata: 추가 정보 (예: {"npc": "청갈치", "date": "2024-05-20"})
        """
        if metadata is None:
            metadata = {}
            
        doc = Document(page_content=text, metadata=metadata)
        self.vector_store.add_documents([doc])
        print(f"[Memory] Saved: {text[:30]}...")

    def get_retriever(self, k: int = 3):
        """
        LangChain Retriever 반환
        Args:
            k: 검색할 문서 개수
        """
        return self.vector_store.as_retriever(
            search_type="similarity",
            search_kwargs={"k": k}
        )

# 전역 인스턴스
# 사용법: 
# from app.core.memory import memory_manager
# retriever = memory_manager.get_retriever()
memory_manager = MemoryManager()