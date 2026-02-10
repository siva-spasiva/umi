#!/usr/bin/env python3
"""
모델 캐싱 스크립트

AWS 배포 전에 모델을 미리 다운로드하여 캐시합니다.
이렇게 하면 첫 실행 시 대기 시간을 줄일 수 있습니다.

사용법:
    python cache_models.py
"""

import os
import sys
from transformers import AutoTokenizer, AutoModelForCausalLM


def cache_huggingface_models():
    """HuggingFace 모델 캐싱"""
    
    # 환경 변수에서 모델 이름 가져오기
    model_name = os.environ.get("NPC_LLM_MODEL", "google/gemma-2-2b-it")
    hf_token = os.environ.get("HF_TOKEN")
    
    print("=" * 60)
    print("HuggingFace 모델 캐싱 시작")
    print("=" * 60)
    print(f"모델: {model_name}")
    print(f"토큰: {'설정됨' if hf_token else '없음'}")
    print()
    
    if not hf_token:
        print("⚠️ 경고: HF_TOKEN이 설정되지 않았습니다.")
        print("   일부 모델은 토큰이 필요할 수 있습니다.")
        print()
    
    try:
        # 1. 토크나이저 다운로드
        print(f"[1/2] 토크나이저 다운로드 중...")
        tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            token=hf_token
        )
        print(f"✅ 토크나이저 캐시 완료")
        print()
        
        # 2. 모델 다운로드
        print(f"[2/2] 모델 다운로드 중...")
        print("   (크기가 크면 시간이 걸릴 수 있습니다)")
        
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            token=hf_token,
            torch_dtype="auto",
            low_cpu_mem_usage=True
        )
        print(f"✅ 모델 캐시 완료")
        print()
        
        # 캐시 위치 출력
        cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
        print(f"캐시 위치: {cache_dir}")
        print()
        
        # 캐시 크기 확인
        import subprocess
        try:
            result = subprocess.run(
                ["du", "-sh", cache_dir],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                size = result.stdout.split()[0]
                print(f"캐시 크기: {size}")
        except Exception:
            pass
        
        print()
        print("=" * 60)
        print("✅ 캐싱 완료!")
        print("=" * 60)
        print()
        print("다음 실행 시 모델을 즉시 로드할 수 있습니다.")
        
        return True
        
    except Exception as e:
        print()
        print("=" * 60)
        print("❌ 캐싱 실패")
        print("=" * 60)
        print(f"오류: {e}")
        print()
        
        if "401" in str(e) or "authentication" in str(e).lower():
            print("💡 해결 방법:")
            print("   1. HuggingFace 토큰 확인: https://huggingface.co/settings/tokens")
            print("   2. .env 파일에 HF_TOKEN 설정")
            print("   3. 모델 접근 권한 확인")
        
        return False


def cache_koelectra_model():
    """KoELECTRA 모델 캐싱 (의도 분석용)"""
    
    model_name = "monologg/koelectra-base-v3-discriminator"
    
    print()
    print("=" * 60)
    print("KoELECTRA 모델 캐싱 시작")
    print("=" * 60)
    print(f"모델: {model_name}")
    print()
    
    try:
        from transformers import AutoModel
        
        print("토크나이저 및 모델 다운로드 중...")
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModel.from_pretrained(model_name)
        
        print("✅ KoELECTRA 캐시 완료")
        print()
        
        return True
        
    except Exception as e:
        print(f"❌ KoELECTRA 캐싱 실패: {e}")
        return False


def main():
    """메인 실행 함수"""
    
    print()
    print("🚀 모델 캐싱 스크립트")
    print()
    
    # 환경 변수 확인
    if not os.path.exists(".env"):
        print("⚠️ .env 파일이 없습니다.")
        print("   .env.template을 복사하여 .env를 생성하세요:")
        print("   cp .env.template .env")
        print()
        response = input("계속하시겠습니까? (y/N): ").strip().lower()
        if response != 'y':
            print("중단됨.")
            return 1
    else:
        # .env 파일 로드
        try:
            from dotenv import load_dotenv
            load_dotenv()
            print("✅ .env 파일 로드됨")
            print()
        except ImportError:
            print("⚠️ python-dotenv가 설치되지 않았습니다.")
            print("   pip install python-dotenv")
            print()
    
    # 1. KoELECTRA 캐싱 (의도 분석용)
    koelectra_ok = cache_koelectra_model()
    
    # 2. HuggingFace 모델 캐싱 (대화 생성용)
    hf_ok = cache_huggingface_models()
    
    # 결과 요약
    print()
    print("=" * 60)
    print("📊 캐싱 결과 요약")
    print("=" * 60)
    print(f"KoELECTRA (의도 분석): {'✅ 성공' if koelectra_ok else '❌ 실패'}")
    print(f"HuggingFace (대화 생성): {'✅ 성공' if hf_ok else '❌ 실패'}")
    print()
    
    if koelectra_ok and hf_ok:
        print("✅ 모든 모델이 성공적으로 캐시되었습니다!")
        print()
        print("다음 단계:")
        print("1. 앱을 시작하면 모델이 즉시 로드됩니다")
        print("2. AWS에 배포할 경우, 이 캐시를 AMI로 저장하세요")
        return 0
    else:
        print("⚠️ 일부 모델 캐싱에 실패했습니다.")
        print("   위의 오류 메시지를 확인하세요.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
