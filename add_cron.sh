# 새로운 crontab 항목 추가할 명령어
GPU_USAGE_FILE_PATH="/home/vln/90_query_gpu_public/gpu_usage.py"

# 현재 crontab을 백업
crontab -l > mycron
# 01. 10분에 한 번 씩 Teams 메시지로 실시간 사용률 전달
new_cron="*/10 * * * * /usr/bin/python3 $GPU_USAGE_FILE_PATH send_realtime_usage"
echo "$new_cron" >> mycron
# 02. 1분에 한 번 씩 gpu 사용률 저장
new_cron="* * * * * /usr/bin/python3 $GPU_USAGE_FILE_PATH save_realtime_usage"
echo "$new_cron" >> mycron
# 03. 하루에 한번 당일 평균 사용률 저장 -> Teams 
new_cron="59 23 * * * /usr/bin/python3 $GPU_USAGE_FILE_PATH send_daily_usage"
echo "$new_cron" >> mycron
# 04. 분기별 사용률 저장 -> Teams
new_cron="0 0 * * * /usr/bin/python3 $GPU_USAGE_FILE_PATH send_period_average"
echo "$new_cron" >> mycron

crontab mycron

# 임시 파일 삭제
rm mycron