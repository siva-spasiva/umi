import psutil
import shutil
from typing import Dict, Any

# GPU 모니터링을 위한 라이브러리 (GPU가 없는 환경에서도 에러가 나지 않도록 처리)
try:
    import pynvml
    pynvml.nvmlInit()
    HAS_GPU = True
except Exception:
    HAS_GPU = False

class MonitoringService:
    def get_system_stats(self) -> Dict[str, Any]:
        # 1. CPU & Memory
        cpu_usage = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory()
        disk = shutil.disk_usage("/")

        stats = {
            "cpu": {
                "usage_percent": cpu_usage,
                "count": psutil.cpu_count()
            },
            "memory": {
                "total_gb": round(memory.total / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2),
                "percent": memory.percent
            },
            "disk": {
                "total_gb": round(disk.total / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "percent": round((disk.used / disk.total) * 100, 1)
            },
            "gpu": []
        }

        # 2. GPU Stats (NVIDIA L40 등)
        if HAS_GPU:
            try:
                device_count = pynvml.nvmlDeviceGetCount()
                for i in range(device_count):
                    handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                    name = pynvml.nvmlDeviceGetName(handle)
                    # pynvml 버전에 따라 bytes로 반환될 수 있음
                    if isinstance(name, bytes):
                        name = name.decode("utf-8")
                    
                    mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                    util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                    temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)

                    stats["gpu"].append({
                        "index": i,
                        "name": name,
                        "memory_total_gb": round(mem_info.total / (1024**3), 2),
                        "memory_used_gb": round(mem_info.used / (1024**3), 2),
                        "memory_percent": round((mem_info.used / mem_info.total) * 100, 1),
                        "gpu_utilization": util.gpu,
                        "temperature": temp
                    })
            except Exception as e:
                stats["gpu_error"] = str(e)
        
        return stats

monitoring_service = MonitoringService()