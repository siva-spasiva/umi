import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.llm_engine import llm_engine
from app.core.memory import memory_manager


class _Doc:
    def __init__(self, page_content, metadata):
        self.page_content = page_content
        self.metadata = metadata


class _Retriever:
    def __init__(self, docs):
        self.docs = docs

    def invoke(self, query):
        return self.docs


def main():
    original_get_retriever = memory_manager.get_retriever
    try:
        # 섞여 있는 결과(타 NPC 포함)를 반환하도록 구성
        docs = [
            _Doc("갈치의 오래된 기억", {"npc_id": "galchi", "memory_type": "session_summary"}),
            _Doc("빙어의 핵심 단서", {"npc_id": "bingeo", "memory_type": "session_summary"}),
            _Doc("전광어의 설교 기록", {"npc_id": "gwangeo", "memory_type": "session_summary"}),
        ]
        memory_manager.get_retriever = lambda k=3, collection_name=None: _Retriever(docs)

        context = llm_engine._retrieve_memory_context("bingeo", "최근 단서 알려줘")
        assert context is not None
        assert "빙어의 핵심 단서" in context
        assert "갈치의 오래된 기억" not in context
        assert "전광어의 설교 기록" not in context
        print("✅ 동일 NPC 기억 우선 검색 가드 동작 확인")
    finally:
        memory_manager.get_retriever = original_get_retriever


if __name__ == "__main__":
    main()
