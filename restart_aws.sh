#!/bin/bash
PUBLIC_IP="100.23.225.34"
USER="ubuntu"
KEY_PATH="/Users/young/.ssh/spsb.pem"

echo "Restarting GPU server on AWS..."
ssh -i $KEY_PATH $USER@$PUBLIC_IP << 'REMOTE_COMMAND_EOF'
    # Kill existing uvicorn processes running gpu_server
    pkill -f "uvicorn gpu_server:app"
    sleep 2
    
    # Navigate to app directory and start the server using nohup
    cd ~/umi
    nohup /home/ubuntu/miniconda3/envs/umi/bin/uvicorn gpu_server:app --host 0.0.0.0 --port 8001 > gpu_server.log 2>&1 &
    echo "GPU Server restarted."
REMOTE_COMMAND_EOF

echo "Done."
