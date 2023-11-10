# dbackup3-ebscn

## Configure
`hr`为示例的部门名，可改为相应的部门名称
```text
[department-hr]
job_history_key_word=hr     # 用于匹配作业名的关键字，填写相应的部门名
# hr-job-timestamp.csv
report_file_prefix=hr
recv_mailboxs=tiger@test.com;cat@test.com;snake@test.com        # 接收者邮箱
send_mailbox=superman2@test.com     # 发送者邮箱
send_password=xxxxxxx       # 发送者密码
mail_subject=hr     # 邮箱主题

[backupd-access]
base_url=http://127.0.0.1:50305     # 迪备访问地址
api_key=aebc8514b2015a6034f8da49a68d192a    # admin用户的API Key

[email]
host=smtp.qq.com    # 邮箱服务地址
port=465    # 邮箱服务端口
use_ssl=true    # 是否使用SSL
subject=一体化备份平台报表   # 邮箱主题
```


## Run
```shell
# 示例： 每天凌晨执行脚本
crontab -e
0 0 * * * cd /workdir/dbacup3-ebscn/ && python3 ./main.py >> ./log.txt 2>&1
```
