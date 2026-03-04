#!/bin/bash
PUBLIC_IP="100.23.225.34"
USER="ubuntu"
KEY_PATH="/Users/young/.ssh/spsb.pem"

echo "Syncing app directory to AWS GPU server..."
rsync -avz -e "ssh -i $KEY_PATH" ./app $USER@$PUBLIC_IP:~/umi/
echo "Sync complete."
