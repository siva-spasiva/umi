from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from app.services.monitoring_service import monitoring_service

router = APIRouter()

@router.get("", summary="서버 리소스 상태 조회 (JSON)")
async def get_server_stats():
    """CPU, RAM, Disk, GPU 상태를 JSON으로 반환합니다."""
    return monitoring_service.get_system_stats()

@router.get("/dashboard", response_class=HTMLResponse, summary="실시간 모니터링 대시보드")
async def monitoring_dashboard():
    """간단한 HTML 대시보드를 반환하여 실시간으로 상태를 확인합니다."""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Umi Server Monitor</title>
        <meta charset="utf-8">
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 20px; background-color: #f0f2f5; color: #333; }
            .container { max-width: 800px; margin: 0 auto; }
            .card { background: white; padding: 20px; margin-bottom: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
            h1 { text-align: center; color: #2c3e50; }
            h2 { margin-top: 0; font-size: 1.2em; border-bottom: 1px solid #eee; padding-bottom: 10px; margin-bottom: 15px; }
            .metric { display: flex; justify-content: space-between; margin-bottom: 8px; align-items: center; }
            .label { font-weight: 600; color: #555; }
            .value { font-family: monospace; font-size: 1.1em; color: #007bff; }
            .bar-bg { background-color: #e9ecef; border-radius: 6px; height: 12px; width: 100%; overflow: hidden; margin-bottom: 15px; }
            .bar { height: 100%; border-radius: 6px; transition: width 0.5s ease; }
            .gpu-card { border-left: 5px solid #28a745; }
            .refresh-info { text-align: center; font-size: 0.8em; color: #888; margin-top: 20px; }
        </style>
        <script>
            async function fetchStats() {
                try {
                    const response = await fetch('/api/v1/monitor');
                    const data = await response.json();
                    
                    // CPU
                    document.getElementById('cpu-val').innerText = data.cpu.usage_percent + '%';
                    updateBar('cpu-bar', data.cpu.usage_percent, data.cpu.usage_percent > 80 ? '#dc3545' : '#007bff');

                    // Memory
                    document.getElementById('mem-val').innerText = data.memory.percent + '% (' + data.memory.available_gb + 'GB free)';
                    updateBar('mem-bar', data.memory.percent, data.memory.percent > 90 ? '#dc3545' : '#ffc107');

                    // GPU
                    const gpuContainer = document.getElementById('gpu-container');
                    gpuContainer.innerHTML = '';
                    if (data.gpu && data.gpu.length > 0) {
                        data.gpu.forEach(gpu => {
                            const color = gpu.memory_percent > 90 ? '#dc3545' : '#28a745';
                            const html = `
                                <div class="card gpu-card">
                                    <h2>GPU ${gpu.index}: ${gpu.name}</h2>
                                    <div class="metric">
                                        <span class="label">GPU Load / Temp</span>
                                        <span class="value">${gpu.gpu_utilization}% / ${gpu.temperature}°C</span>
                                    </div>
                                    <div class="metric">
                                        <span class="label">VRAM Usage</span>
                                        <span class="value">${gpu.memory_used_gb}GB / ${gpu.memory_total_gb}GB</span>
                                    </div>
                                    <div class="bar-bg">
                                        <div class="bar" style="width: ${gpu.memory_percent}%; background-color: ${color};"></div>
                                    </div>
                                </div>
                            `;
                            gpuContainer.innerHTML += html;
                        });
                    } else {
                        gpuContainer.innerHTML = '<div class="card">No GPU Detected</div>';
                    }
                } catch (e) { console.error(e); }
            }

            function updateBar(id, percent, color) {
                const bar = document.getElementById(id);
                bar.style.width = percent + '%';
                bar.style.backgroundColor = color;
            }

            setInterval(fetchStats, 2000); // 2초마다 갱신
            window.onload = fetchStats;
        </script>
    </head>
    <body>
        <div class="container">
            <h1>🖥️ Umi Server Monitor</h1>
            <div class="card">
                <h2>System Resources</h2>
                <div class="metric"><span class="label">CPU Usage</span><span class="value" id="cpu-val">...</span></div>
                <div class="bar-bg"><div id="cpu-bar" class="bar" style="width: 0%;"></div></div>
                
                <div class="metric"><span class="label">Memory Usage</span><span class="value" id="mem-val">...</span></div>
                <div class="bar-bg"><div id="mem-bar" class="bar" style="width: 0%;"></div></div>
            </div>
            <div id="gpu-container"></div>
            <div class="refresh-info">Updates automatically every 2 seconds</div>
        </div>
    </body>
    </html>
    """
    return html_content