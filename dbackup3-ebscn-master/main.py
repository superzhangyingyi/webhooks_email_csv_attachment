#!/usr/bin/python
# -*- coding: UTF-8 -*-
import configparser
import json
import logging
import smtplib
import urllib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib import request, parse


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(filename)s[%(lineno)d]%(funcName)s"
    " %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

START_TIME = str(datetime.utcnow() - timedelta(hours=24)).split(' ')[0]
FILENAME='./tp.csv'

html_template = """
<html>
<body>
<table border="1">
  <caption>作业概览</caption>
  {job_overview_table}
</table>

<hr>

<table border="1">
  <caption>存储池</caption>
  {storage_pools_table}
</table>

<hr>

<table border="1">
  <caption>作业历史</caption>
  {job_histories_table}
</table>
</body>
</html>
"""

def transform_size(num):
    step = 1024

    for unit in ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]:
        if num < step:
            return "%.2f%s" % (num, unit)
        num /= step

    return "%.2fEiB" % num


class EBSCN:
    def __init__(
        self,
        base_url,
        api_key,
        mail_host,
        mail_port,
        mail_use_ssl,
        mail_subject,
    ):
        self._base_url = base_url
        self._api_key = api_key
        self._mail_host = mail_host
        self._mail_port = mail_port
        self._mail_use_ssl = mail_use_ssl
        self._mail_subject = mail_subject

    def create_email_server(self):
        if self._mail_use_ssl == "true":
            return smtplib.SMTP_SSL(self._mail_host, self._mail_port)
        return smtplib.SMTP(self._mail_host, self._mail_port)

    def send_request(
        self, path="", headers={}, params={}, data=None, method="GET"
    ):
        url = parse.urljoin(self._base_url, path)

        if params:
            url = "{}?{}".format(url, parse.urlencode(params))

        if data:
            data = json.dumps(data).encode("utf-8")

        logging.info("url: {}".format(url))
        req = request.Request(
            url, headers=headers, data=data, method=method.upper()
        )

        return self.get_response(req)

    def create_headers(self, content_type="application/json"):
        return {"X-api-key": self._api_key, "Content-type": content_type}

    def get_response(self, req, times=1):
        try:
            with request.urlopen(req) as resp:
                status = resp.status
                content = resp.read()

            if req.get_header("Content-type") == "text/csv":
                return status, content.decode("utf-8-sig")
            else:
                return status, json.loads(content.decode("utf-8"))

        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8")
        except Exception as e:
            logging.error(e)
            trytimes = 3
            if times < trytimes:
                times += 1
                return self.get_response(req, times)
            raise Exception("out of max times")

    def get_job_histories(self, department, start_time):
        status, content = self.send_request(
            "/d2/r/v2/job/histories",
            headers=self.create_headers(content_type="text/csv"),
            params={
                "download": "csv",
                "formatter": "pretty",
                "keys": "name,subtype,state,host,resource,instance_type,device,pool_type,username,start_time,end_time,duration,source_size,backup_set_size,backup_set_storage_size,deduplication_compression,backup_speed,transfer_speed,host_uuid",
                "LK_name": "%" + department + "%",
                "GE_start_time": start_time,
                "timezone": 8,
                "scope": "all",
            },
            method="GET",
        )

        if status // 100 == 2:
            return content

        raise Exception("status: {}, content: {}".format(status, content))

    def get_successful_job_histories_total(self, department, start_time):
        status, content = self.send_request(
            "/d2/r/v2/job/histories",
            headers=self.create_headers(),
            params={
                "cmode": "rb_orm_total",
                "state": "completed",
                "LK_name": "%" + department + "%",
                "GE_start_time": start_time,
                "scope": "all",
            },
            method="GET",
        )

        if status // 100 == 2:
            return content["total"]

        raise Exception("status: {}, content: {}".format(status, content))

    def get_failure_job_histories_total(self, department, start_time):
        status, content = self.send_request(
            "/d2/r/v2/job/histories",
            headers=self.create_headers(),
            params={
                "cmode": "rb_orm_total",
                "NE_state": "completed",
                "LK_name": "%" + department + "%",
                "GE_start_time": start_time,
                "scope": "all",
            },
            method="GET",
        )

        if status // 100 == 2:
            return content["total"]

        raise Exception("status: {}, content: {}".format(status, content))

    def get_storage_pools(self):
        status, content = self.send_request(
            "/d2/r/v2/storage/pools",
            headers=self.create_headers(),
            method="GET",
        )

        if status // 100 == 2:
            return content

        raise Exception("status: {}, content: {}".format(status, content))

    def get_storageds(self):
        status, content = self.send_request(
            "/d2/r/v2/storageds",
            headers=self.create_headers(),
            method="GET",
        )

        if status // 100 == 2:
            return content["rows"]

        raise Exception("status: {}, content: {}".format(status, content))

    def get_hosts(self):
        status, content = self.send_request(
            "/d2/r/v2/hosts",
            headers=self.create_headers(),
            params={
                "scope": "all",
            },
            method="GET",
        )

        if status // 100 == 2:
            return content["rows"]

        raise Exception("status: {}, content: {}".format(status, content))

    def create_message(self, department):
        start_time = datetime.utcnow() - timedelta(hours=24)
        job_overview_table=self.get_overview_table(department, start_time)
        storage_pools_table=self.get_storage_pools_table()
        job_histories_table=self.get_job_histories_table(department, start_time)
        f = open(FILENAME, 'w', encoding='utf-8-sig')
        for lst1 in job_overview_table[1]:
            f.write(lst1 + "\n")
        for lst2 in storage_pools_table[1]:
            f.write(lst2 + "\n")
        for lst3 in job_histories_table[1]:
            f.write(lst3 + "\n")
        return html_template.format(
            job_overview_table=job_overview_table[0],
            storage_pools_table=storage_pools_table[0],
            job_histories_table=job_histories_table[0]
        )

    def get_job_histories_table(self, department, start_time):
        hosts = self.get_hosts()
        job_histories_csv = self.get_job_histories(department, start_time)
        job_histories = job_histories_csv.split("\n")
        table_head = job_histories.pop(0).split(",")[0:-1]
        job_histories_table = [
            "\t\t<tr>\n\t\t\t<th>"
            + "</th>\n\t\t\t<th>".join(table_head)
            + "</th>\n\t\t</tr>"
        ]
        job_histories_table_csv = ["\n作业历史", ",".join(table_head)]
        for job in job_histories:
            if job:
                job_row = job.split(",")
                for host in hosts:
                    if host["uuid"] == job_row[-1]:
                        job_row[3] = host["address"]
                        break
                    
                job_histories_table.append(
                    "\t\t<tr>\n\t\t\t<td>"
                    + "</td>\n\t\t\t<td>".join(job_row[0:-1])
                    + "</td>\n\t\t</tr>"
                )
                job_histories_table_csv.append(",".join(job_row[0:-1]))

        return ["\n".join(job_histories_table), job_histories_table_csv]

    def get_storage_pools_table(self):
        storage_pools = self.get_storage_pools()
        storageds = self.get_storageds()
        storage_pools_table_csv = ['\n存储池', "名称,类型,状态,可用,总共"]
        storage_pools_row_csv = """{name},{type},{online},{free_size},{size}"""
        storage_pools_table = [
            """
        <tr>
            <th>名称</th>
            <th>类型</th>
            <th>状态</th>
            <th>可用</th>
            <th>总共</th>
        </tr>
        """
        ]
        storage_pools_row = """
        <tr>
            <td>{name}</td>
            <td>{type}</td>
            <td>{online}</td>
            <td>{free_size}</td>
            <td>{size}</td>
        </tr>
        """
        for pool in storage_pools["rows"]:
            storage = pool["storages"][0]

            for storaged in storageds:
                if storaged["uuid"] == storage["host_uuid"]:
                    online = storaged["online"]
                    break
            try:
                storage_pools_table_csv.append(
                    storage_pools_row_csv.format(
                        name=pool["name"],
                        type=pool["type"],
                        online="在线" if online else "离线",
                        free_size=transform_size(
                            self.get_storage_pool_free_size(storage)
                        ),
                        size=transform_size(storage["extended_attrs"]["size"]),
                    )
                )
                storage_pools_table.append(
                    storage_pools_row.format(
                        name=pool["name"],
                        type=pool["type"],
                        online="在线" if online else "离线",
                        free_size=transform_size(
                            self.get_storage_pool_free_size(storage)
                        ),
                        size=transform_size(storage["extended_attrs"]["size"]),
                    )
                )
            except Exception as e:
                logging.error(e)
        return ["".join(storage_pools_table), storage_pools_table_csv]

    def get_storage_pool_free_size(self, storage):
        try:
            free_size = storage["extended_attrs"]["free_size"]
        except KeyError:
            free_size = (
                storage["extended_attrs"]["size"] - storage["used_bytes"]
            )
        return free_size

    def get_overview_table(self, department, start_time):
        successful_total = self.get_successful_job_histories_total(
            department, start_time
        )
        failure_total = self.get_failure_job_histories_total(
            department, start_time
        )
        total = successful_total + failure_total
        successful_percentage = (
            "{}%".format(round((successful_total / total) * 100, 2))
            if total != 0
            else "-"
        )
        failure_percentage = (
            "{}%".format(round((failure_total / total) * 100, 2))
            if total != 0
            else "-"
        )
        tpstr1 = 'successful,'+str(successful_total)+','+str(successful_percentage)
        tpstr2 = 'failure,'+str(failure_total)+','+str(failure_percentage)
        job_overview_table_csv = ['作业概览', '状态,数量,百分比', tpstr1, tpstr2]
        job_overview_table = """
        <tr>
            <th>状态</th>
            <th>数量</th>
            <th>百分比</th>
        </tr>
        <tr>
            <td>successful</td>
            <td>{successful_total}</td>
            <td>{successful_percentage}</td>
        </tr>
        <tr>
            <td>failure</td>
            <td>{failure_total}</td>
            <td>{failure_percentage}</td>
        </tr>
        """.format(
            successful_total=successful_total,
            successful_percentage=successful_percentage,
            failure_total=failure_total,
            failure_percentage=failure_percentage,
        )
        return [job_overview_table, job_overview_table_csv]

    def send_mail(self, sender, password, receivers, htmlMsg, subject):
        try:
            msg = MIMEMultipart()
            msg["From"] = sender
            msg["To"] = receivers
            if subject:
                msg["Subject"] = subject
            else:
                msg["Subject"] = self._mail_subject
            msg.attach(MIMEText(htmlMsg, "html", "utf-8"))
            part = MIMEApplication(open(FILENAME, 'rb').read())
            part.add_header('Content-Disposition', 'attachment', filename='dbackup_'+START_TIME+'.csv')
            msg.attach(part)
            server = self.create_email_server()
            server.login(sender, password)
            server.sendmail(
                sender,
                receivers.split(";"),
                msg.as_string(),
            )
            server.quit()

            return "已发送邮件到: {}".format(receivers)
        except Exception as e:
            logging.error(e)
            return "邮件发送失败!"

    def run(self, department):
        return self.send_mail(
            department["send_mailbox"],
            department["send_password"],
            department["recv_mailboxs"],
            self.create_message(department["job_history_key_word"]),
            department["mail_subject"],
        )


if __name__ == "__main__":
    CONFIG_PATH = "./config.ini"
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)

    ebscn = EBSCN(
        config["backupd-access"]["base_url"],
        config["backupd-access"]["api_key"],
        config["email"]["host"],
        config["email"]["port"],
        config["email"]["use_ssl"],
        config["email"]["subject"],
    )
    departments = [
        config[section]
        for section in config.sections()
        if section.startswith("department-")
    ]

    with ThreadPoolExecutor() as e:
        for result in e.map(ebscn.run, departments):
            logging.info(result)
