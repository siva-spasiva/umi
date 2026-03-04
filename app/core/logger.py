import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler

class LoggerWriter:
    """stdout/stderr를 로거로 리다이렉트하기 위한 래퍼 클래스"""
    def __init__(self, logger, level):
        self.logger = logger
        self.level = level
        self.buffer = ""

    def write(self, message):
        if message and message.strip(): # 빈 줄 제외
            for line in message.splitlines():
                if line.strip():
                    self.logger.log(self.level, line.rstrip())

    def flush(self):
        pass

def setup_daily_rotating_logger(
    name: str, 
    log_file: str, 
    capture_uvicorn: bool = False,
    redirect_stdout: bool = False
):
    """
    매일 자정에 새로운 로그 파일로 교체되는 로거 설정
    
    Args:
        name: 로거 이름
        log_file: 로그 파일 경로
        capture_uvicorn: Uvicorn 로그 통합 여부 (API 서버용)
        redirect_stdout: print() 출력을 로그 파일로 리다이렉트할지 여부 (GPU 서버용)
    """
    # 로그 디렉토리 생성
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
        
    # 포맷 설정
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Rotating Handler (매일 자정)
    handler = TimedRotatingFileHandler(
        log_file, 
        when="midnight", 
        interval=1, 
        backupCount=30, # 30일치 보관
        encoding="utf-8"
    )
    handler.setFormatter(formatter)
    handler.suffix = "%Y-%m-%d" 
    
    # Root Logger 설정
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)
    
    # Uvicorn 로그 통합 (FastAPI용)
    if capture_uvicorn:
        logging.getLogger("uvicorn.access").addHandler(handler)
        logging.getLogger("uvicorn.error").addHandler(handler)
    
    # stdout(터미널)에도 출력되게 하려면 (리다이렉트 안 할 때만)
    if not redirect_stdout:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    
    # 로거 생성
    logger = logging.getLogger(name)

    # stdout 리다이렉트 (GPU 서버용: print문 캡처)
    if redirect_stdout:
        sys.stdout = LoggerWriter(logger, logging.INFO)
        # stderr는 ERROR 레벨로
        sys.stderr = LoggerWriter(logger, logging.ERROR)
        print(f"[Logger] Standard output redirected to {log_file}")

    return logger
